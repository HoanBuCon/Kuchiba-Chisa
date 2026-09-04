"""FR-ING-007/008 regressions for quality-gated corpus publication."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.application.ingestion.corpus_release_lifecycle import (
    CorpusReleaseConsistencyError,
    CorpusReleaseLifecycleService,
)
from app.application.security.authorization import AuthorizationError
from app.domain.interfaces.corpus_publisher import CorpusPublication
from app.domain.models.corpus_manifest import ParentCorpusManifest
from app.domain.models.corpus_release import CorpusQualityReport, CorpusRelease, CorpusReleaseStatus
from app.domain.models.lore_collections import LoreCollection
from app.domain.value_objects.principal import PrincipalContext


def _release(**overrides: object) -> CorpusRelease:
    values: dict[str, object] = {
        "release_id": uuid.uuid4(),
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


def _report(release: CorpusRelease, **overrides: object) -> CorpusQualityReport:
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


class _ReleaseRepository:
    def __init__(self, releases: list[CorpusRelease]) -> None:
        self.releases = {release.release_id: release for release in releases}
        self.reports: dict[uuid.UUID, CorpusQualityReport] = {}
        self.audit_events: list[object] = []
        self.commit_count = 0

    async def save_release(self, release: CorpusRelease) -> None:
        self.releases[release.release_id] = release

    async def get_release(self, release_id: uuid.UUID) -> CorpusRelease | None:
        return self.releases.get(release_id)

    async def get_release_by_staging_collection(
        self, staging_collection: str
    ) -> CorpusRelease | None:
        return next(
            (
                release
                for release in self.releases.values()
                if release.staging_collection == staging_collection
            ),
            None,
        )

    async def save_quality_report(self, report: CorpusQualityReport) -> None:
        self.reports[report.release_id] = report

    async def get_quality_report(self, release_id: uuid.UUID) -> CorpusQualityReport | None:
        return self.reports.get(release_id)

    async def record_audit(self, event: object) -> None:
        self.audit_events.append(event)

    async def commit(self) -> None:
        self.commit_count += 1


class _SourceRepository:
    def __init__(self, source_id: uuid.UUID, owner_id: str = "curator-a") -> None:
        self.source_id = source_id
        self.owner_id = owner_id

    async def get_source(self, source_id: uuid.UUID) -> SimpleNamespace | None:
        if source_id != self.source_id:
            return None
        return SimpleNamespace(owner_id=self.owner_id)


class _ParentRepository:
    def __init__(self, manifest: ParentCorpusManifest) -> None:
        self.manifest = manifest

    async def get_corpus_manifest(self, **_: object) -> ParentCorpusManifest:
        return self.manifest


class _Publisher:
    def __init__(self, previous: str = "character_lore__v20260904") -> None:
        self.previous = previous
        self.promoted: list[CorpusRelease] = []
        self.active = previous

    async def promote(self, release: CorpusRelease) -> CorpusPublication:
        self.promoted.append(release)
        previous = self.active
        self.active = release.staging_collection
        return CorpusPublication(
            previous_active_collection=previous,
            active_collection=release.staging_collection,
        )

    async def active_target(self, _: str) -> str | None:
        return self.active


def _principal(*, subject_id: str = "curator-a", scopes: frozenset[str]) -> PrincipalContext:
    return PrincipalContext(
        subject_id=subject_id,
        tenant_id=None,
        channel_id=None,
        source="web",
        kind="user",
        scopes=scopes,
    )


def _service(
    release: CorpusRelease,
    *,
    owner_id: str = "curator-a",
    manifest: ParentCorpusManifest | None = None,
    releases: list[CorpusRelease] | None = None,
) -> tuple[CorpusReleaseLifecycleService, _ReleaseRepository, _Publisher]:
    repository = _ReleaseRepository(releases or [release])
    publisher = _Publisher()
    service = CorpusReleaseLifecycleService(
        release_repository=repository,
        source_repository=_SourceRepository(release.source_id, owner_id),
        parent_repository=_ParentRepository(
            manifest
            or ParentCorpusManifest(parent_count=3, checksum="a" * 64)
        ),
        publisher=publisher,
    )
    return service, repository, publisher


@pytest.mark.asyncio
async def test_publish_requires_persisted_passing_quality_and_matching_parent_manifest() -> None:
    release = _release()
    service, repository, publisher = _service(release)
    quality_passed = await service.record_quality_report(_report(release))

    published = await service.publish(
        _principal(scopes=frozenset({"ingestion:release:publish"})), release.release_id
    )

    assert quality_passed.status is CorpusReleaseStatus.QUALITY_PASSED
    assert published.status is CorpusReleaseStatus.PUBLISHED
    assert publisher.promoted[0].status is CorpusReleaseStatus.PROMOTION_REQUESTED
    assert repository.audit_events[-1].action.value == "published"
    assert repository.commit_count == 3


@pytest.mark.asyncio
async def test_publish_rejects_missing_quality_receipt_before_alias_mutation() -> None:
    release = _release()
    service, _, publisher = _service(release)

    with pytest.raises(CorpusReleaseConsistencyError, match="has not passed"):
        await service.publish(
            _principal(scopes=frozenset({"ingestion:release:publish"})), release.release_id
        )

    assert publisher.promoted == []


@pytest.mark.asyncio
async def test_failed_quality_report_is_durable_auditable_and_cannot_publish() -> None:
    release = _release()
    service, repository, publisher = _service(release)

    result = await service.record_quality_report(_report(release, faithfulness=0.89))

    assert result.status is CorpusReleaseStatus.STAGED
    assert repository.reports[release.release_id].faithfulness == 0.89
    assert repository.audit_events[-1].action.value == "failed"
    assert repository.commit_count == 1
    with pytest.raises(CorpusReleaseConsistencyError, match="has not passed"):
        await service.publish(
            _principal(scopes=frozenset({"ingestion:release:publish"})), release.release_id
        )
    assert publisher.promoted == []


@pytest.mark.asyncio
async def test_failed_quality_re_evaluation_reuses_the_current_report_receipt() -> None:
    release = _release()
    service, repository, _ = _service(release)
    first = _report(release, faithfulness=0.89)
    await service.record_quality_report(first)

    await service.record_quality_report(_report(release, faithfulness=0.88))

    assert repository.reports[release.release_id].report_id == first.report_id
    assert repository.reports[release.release_id].faithfulness == 0.88
    assert repository.audit_events[-1].action.value == "failed"


@pytest.mark.asyncio
async def test_quality_report_cannot_replace_a_passing_release_receipt() -> None:
    release = _release()
    service, _, _ = _service(release)
    await service.record_quality_report(_report(release))

    with pytest.raises(CorpusReleaseConsistencyError, match="only be recorded"):
        await service.record_quality_report(_report(release, faithfulness=0.89))


@pytest.mark.asyncio
async def test_publish_rejects_parent_manifest_mismatch_before_alias_mutation() -> None:
    release = _release()
    service, _, publisher = _service(
        release,
        manifest=ParentCorpusManifest(parent_count=2, checksum="a" * 64),
    )
    await service.record_quality_report(_report(release))

    with pytest.raises(CorpusReleaseConsistencyError, match="parent store manifest"):
        await service.publish(
            _principal(scopes=frozenset({"ingestion:release:publish"})), release.release_id
        )

    assert publisher.promoted == []


@pytest.mark.asyncio
async def test_cross_owner_curator_cannot_publish_another_sources_release() -> None:
    release = _release()
    service, _, publisher = _service(release, owner_id="curator-a")
    await service.record_quality_report(_report(release))

    with pytest.raises(AuthorizationError):
        await service.publish(
            _principal(
                subject_id="curator-b", scopes=frozenset({"ingestion:release:publish"})
            ),
            release.release_id,
        )

    assert publisher.promoted == []


@pytest.mark.asyncio
async def test_rollback_repromotes_retained_receipt_after_parent_manifest_verification() -> None:
    current = _release()
    prior = _release(
        staging_collection="character_lore__v20260904",
        corpus_version="v20260904",
        source_id=current.source_id,
        status=CorpusReleaseStatus.PUBLISHED,
        published_at=datetime.now(UTC),
    )
    service, repository, publisher = _service(current, releases=[current, prior])
    await service.record_quality_report(_report(current))
    published = await service.publish(
        _principal(scopes=frozenset({"ingestion:release:publish"})), current.release_id
    )

    rolled_back = await service.rollback(
        _principal(scopes=frozenset({"ingestion:release:rollback"})), published.release_id
    )

    assert rolled_back.status is CorpusReleaseStatus.ROLLED_BACK
    assert publisher.promoted[-1] == prior
    assert repository.commit_count == 5


@pytest.mark.asyncio
async def test_reconcile_finalizes_committed_intent_when_alias_was_already_swapped() -> None:
    requested = _release(
        status=CorpusReleaseStatus.PROMOTION_REQUESTED,
        previous_active_collection="character_lore__v20260904",
    )
    service, repository, publisher = _service(requested)
    publisher.active = requested.staging_collection

    reconciled = await service.reconcile(
        _principal(scopes=frozenset({"ingestion:release:publish"})), requested.release_id
    )

    assert reconciled.status is CorpusReleaseStatus.PUBLISHED
    assert repository.audit_events[-1].action.value == "published"
    assert publisher.promoted == []


@pytest.mark.asyncio
async def test_reconcile_restores_quality_state_when_alias_never_changed() -> None:
    requested = _release(
        status=CorpusReleaseStatus.PROMOTION_REQUESTED,
        previous_active_collection="character_lore__v20260904",
    )
    service, repository, publisher = _service(requested)
    publisher.active = "character_lore__v20260904"

    reconciled = await service.reconcile(
        _principal(scopes=frozenset({"ingestion:release:publish"})), requested.release_id
    )

    assert reconciled.status is CorpusReleaseStatus.QUALITY_PASSED
    assert repository.audit_events[-1].action.value == "failed"
    assert publisher.promoted == []


@pytest.mark.asyncio
async def test_reconcile_finalizes_rollback_when_retained_target_is_active() -> None:
    requested = _release(
        status=CorpusReleaseStatus.ROLLBACK_REQUESTED,
        published_at=datetime.now(UTC),
        previous_active_collection="character_lore__v20260904",
    )
    service, repository, publisher = _service(requested)
    publisher.active = "character_lore__v20260904"

    reconciled = await service.reconcile(
        _principal(scopes=frozenset({"ingestion:release:rollback"})), requested.release_id
    )

    assert reconciled.status is CorpusReleaseStatus.ROLLED_BACK
    assert repository.audit_events[-1].action.value == "rolled_back"
    assert publisher.promoted == []


@pytest.mark.asyncio
async def test_reconcile_restores_published_state_when_rollback_never_changed_alias() -> None:
    requested = _release(
        status=CorpusReleaseStatus.ROLLBACK_REQUESTED,
        published_at=datetime.now(UTC),
        previous_active_collection="character_lore__v20260904",
    )
    service, repository, publisher = _service(requested)
    publisher.active = requested.staging_collection

    reconciled = await service.reconcile(
        _principal(scopes=frozenset({"ingestion:release:rollback"})), requested.release_id
    )

    assert reconciled.status is CorpusReleaseStatus.PUBLISHED
    assert repository.audit_events[-1].action.value == "failed"
    assert publisher.promoted == []
