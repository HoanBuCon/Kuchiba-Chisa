"""FR-ING-007 release receipt contract regressions."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.domain.models.corpus_release import (
    CorpusQualityReport,
    CorpusRelease,
    CorpusReleaseStatus,
)
from app.domain.models.lore_collections import LoreCollection


def _release(**overrides: object) -> CorpusRelease:
    values: dict[str, object] = {
        "job_id": uuid.uuid4(),
        "source_id": uuid.uuid4(),
        "logical_collection": LoreCollection.CHARACTER,
        "staging_collection": "character_lore__v20260905",
        "corpus_version": "v20260905",
        "parent_count": 3,
        "vector_count": 7,
        "parent_manifest_checksum": "a" * 64,
        "vector_manifest_checksum": "b" * 64,
    }
    values.update(overrides)
    return CorpusRelease.model_validate(values)


def test_staged_release_binds_physical_target_logical_route_and_version() -> None:
    release = _release()

    assert release.status is CorpusReleaseStatus.STAGED
    assert release.logical_collection is LoreCollection.CHARACTER
    assert release.corpus_version == "v20260905"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("logical_collection", LoreCollection.WORLD),
        ("corpus_version", "v20260906"),
        ("vector_manifest_checksum", "not-a-checksum"),
    ],
)
def test_release_rejects_mismatched_or_unverifiable_staging_manifest(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        _release(**{field: value})


def _quality_report(release: CorpusRelease, **overrides: object) -> CorpusQualityReport:
    values: dict[str, object] = {
        "release_id": release.release_id,
        "evaluator_version": "golden-evaluator-v1",
        "dataset_version": "lore-golden-v1",
        "sample_size": 100,
        "confidence_interval": 0.03,
        "faithfulness": 0.90,
        "answer_relevance": 0.85,
        "context_recall": 0.85,
        "context_precision": 0.75,
        "citation_correctness": 0.95,
        "retrieval_hit_at_5": 0.90,
        "retrieval_mrr_at_10": 0.80,
        "critical_unsupported_claims": 0,
        "cross_tenant_leakage_count": 0,
        "prompt_leakage_count": 0,
        "human_audit_completed": True,
        "security_slice_passed": True,
    }
    values.update(overrides)
    return CorpusQualityReport.model_validate(values)


def test_release_requires_all_quality_and_security_slices_before_publish() -> None:
    release = _release()

    quality_passed = release.mark_quality_passed(_quality_report(release))
    promotion_requested = quality_passed.mark_promotion_requested(
        previous_active_collection="character_lore__v20260904"
    )
    published = promotion_requested.mark_published(
        previous_active_collection="character_lore__v20260904"
    )

    assert published.status is CorpusReleaseStatus.PUBLISHED
    assert published.published_at is not None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("faithfulness", 0.89),
        ("citation_correctness", 0.94),
        ("cross_tenant_leakage_count", 1),
        ("prompt_leakage_count", 1),
        ("human_audit_completed", False),
    ],
)
def test_release_rejects_quality_report_that_fails_any_required_gate(
    field: str, value: object
) -> None:
    release = _release()

    with pytest.raises(ValueError, match="quality report does not meet"):
        release.mark_quality_passed(_quality_report(release, **{field: value}))
