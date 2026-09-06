"""Regression tests for audited RAG-06 v2 human-review finalization."""

from __future__ import annotations

import copy
import json

from scripts.finalize_rag06_human_review import (
    REVIEW_JSON,
    calculate_metrics,
    frozen_content_fingerprint,
    record_human_approval,
    validate_finalized_artifact,
)


def _pending_artifact() -> dict:
    return json.loads(REVIEW_JSON.read_text(encoding="utf-8"))


def test_human_approval_preserves_frozen_content_and_resolves_all_cases() -> None:
    pending = _pending_artifact()
    frozen_before = frozen_content_fingerprint(pending)

    approved = record_human_approval(
        copy.deepcopy(pending),
        reviewed_at="2026-09-06T18:35:18+07:00",
    )
    validation = validate_finalized_artifact(approved, frozen_before=frozen_before)

    assert validation["status"] == "PASS"
    assert validation["frozen_content_unchanged"] is True
    assert validation["human_reviewed_cases"] == 38
    assert validation["pending_human_reviews"] == 0


def test_metrics_preserve_partial_relevance_and_false_abstentions() -> None:
    approved = record_human_approval(
        _pending_artifact(),
        reviewed_at="2026-09-06T18:35:18+07:00",
    )

    metrics = calculate_metrics(approved)

    assert metrics["faithfulness"]["value"] == 1.0
    assert metrics["answer_relevance"]["successes"] == 31
    assert metrics["answer_relevance"]["sample_size"] == 36
    assert metrics["partial_relevance_cases"] == ["rw-037", "rw-060", "rw-066"]
    assert metrics["citation_correctness"]["value"] == 1.0
    assert metrics["abstention_precision"]["successes"] == 2
    assert metrics["abstention_precision"]["sample_size"] == 2
    assert metrics["false_abstention_case_ids"] == ["rw-003", "rw-044"]


def test_frozen_fingerprint_detects_output_or_evidence_mutation() -> None:
    artifact = _pending_artifact()
    original = frozen_content_fingerprint(artifact)

    artifact["cases"][0]["generation"]["delivered_answer"] = "tampered"

    assert frozen_content_fingerprint(artifact) != original
