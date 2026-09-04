"""ING-01 regression tests for the canonical application ingestion DAG."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.application.ingestion.errors import IngestionStageError
from app.application.ingestion.orchestrator import (
    IngestionOrchestrator,
    IngestionRunRequest,
)
from app.domain.entities.lore import LoreParent
from app.domain.entities.parser_models import ParsedPage, WikiDocument
from app.domain.entities.wiki import DownloadedPage
from app.domain.interfaces.pipeline import PipelineMetrics, PipelineResult
from app.domain.models.evidence import EvidenceAccess

SOURCE_ID = uuid.UUID("c7ad47e2-41a1-5a88-8a88-bc3c0b9c0638")


class _RecordingStage:
    def __init__(self, output: Any, *, failed_items: int = 0) -> None:
        self.output = output
        self.failed_items = failed_items
        self.calls: list[tuple[uuid.UUID, Any]] = []

    async def execute(self, job_id: uuid.UUID, input_data: Any) -> PipelineResult[Any]:
        self.calls.append((job_id, input_data))
        return PipelineResult(
            output=self.output,
            metrics=PipelineMetrics(
                duration_seconds=0.01,
                items_processed=len(self.output) if isinstance(self.output, list) else 1,
                items_failed=self.failed_items,
                items_skipped=0,
            ),
        )


class _JobRepository:
    def __init__(self) -> None:
        self.job_id = uuid.uuid4()
        self.status_updates: list[tuple[uuid.UUID, str, str | None]] = []
        self.events: list[tuple[uuid.UUID, str, dict[str, Any]]] = []

    async def create_job(self, _: str, __: str) -> uuid.UUID:
        return self.job_id

    async def update_job_status(
        self, job_id: uuid.UUID, status: str, error: str | None = None
    ) -> None:
        self.status_updates.append((job_id, status, error))

    async def log_event(
        self, job_id: uuid.UUID, event_type: str, details: dict[str, Any]
    ) -> None:
        self.events.append((job_id, event_type, details))


class _ParentRepository:
    def __init__(self) -> None:
        self.parents: list[Any] = []

    async def save_parent(self, parent: Any) -> None:
        self.parents.append(parent)


class _ReleaseRepository:
    def __init__(self) -> None:
        self.releases: list[Any] = []
        self.audit_events: list[Any] = []

    async def save_release(self, release: Any) -> None:
        self.releases.append(release)

    async def record_audit(self, event: Any) -> None:
        self.audit_events.append(event)


def _orchestrator(
    *, parser_failures: int = 0
) -> tuple[
    IngestionOrchestrator,
    _JobRepository,
    _ParentRepository,
    _ReleaseRepository,
    dict[str, _RecordingStage],
]:
    downloaded = DownloadedPage(page_id=1, title="Test", revision_id=1, file_path="test.wiki")
    parsed = ParsedPage(
        page_id=1,
        title="Test",
        revision_id=1,
        document=WikiDocument(
            metadata={},
            sections=[],
            links=[],
            templates=[],
            categories=[],
            infobox={},
            confidence=1.0,
        ),
    )
    stages = {
        "download": _RecordingStage([downloaded]),
        "parse": _RecordingStage([parsed], failed_items=parser_failures),
        "parents": _RecordingStage([]),
        "chunks": _RecordingStage([]),
        "entities": _RecordingStage([]),
        "metadata": _RecordingStage([]),
        "validation": _RecordingStage([]),
        "incremental": _RecordingStage([]),
        "embedding": _RecordingStage([]),
        "upsert": _RecordingStage([]),
    }
    jobs = _JobRepository()
    parents = _ParentRepository()
    releases = _ReleaseRepository()
    return (
        IngestionOrchestrator(
            downloader=stages["download"],
            parser=stages["parse"],
            parent_builder=stages["parents"],
            semantic_chunk_builder=stages["chunks"],
            entity_resolver=stages["entities"],
            metadata_enricher=stages["metadata"],
            validator=stages["validation"],
            incremental_router=stages["incremental"],
            batch_embedding=stages["embedding"],
            qdrant_upsert=stages["upsert"],
            parent_repository=parents,
            release_repository=releases,
            job_repository=jobs,
            source_access=EvidenceAccess(scope="public"),
        ),
        jobs,
        parents,
        releases,
        stages,
    )


@pytest.mark.asyncio
async def test_orchestrator_runs_one_ordered_dag_and_acknowledges_only_staging_target() -> None:
    orchestrator, jobs, parents, releases, stages = _orchestrator()
    parent = LoreParent(
        id=uuid.uuid4(),
        page_id=1,
        page_title="Test",
        heading="Lead",
        markdown="Approved staging content.",
        source_file="test.wiki",
        revision_id=1,
        corpus_version="v20260904",
        source_id=SOURCE_ID,
    )
    stages["parents"].output = [parent]

    result = await orchestrator.run(
        IngestionRunRequest(
            staging_collection="character_lore__v20260904",
            source_id=SOURCE_ID,
            download_limit=5,
        )
    )

    assert result.job_id == jobs.job_id
    assert result.release_id == releases.releases[0].release_id
    assert result.parent_documents == 1
    assert result.acknowledged_vectors == 0
    assert parents.parents == [parent]
    assert [update[1] for update in jobs.status_updates] == ["RUNNING", "SUCCEEDED"]
    assert [event[1] for event in jobs.events] == [
        "ParentsPersisted",
        "IngestionAcknowledged",
    ]
    assert releases.releases[0].status.value == "staged"
    assert releases.audit_events[0].action.value == "staged"
    assert stages["parents"].calls[0][1].corpus_version == "v20260904"
    assert stages["parents"].calls[0][1].source_id == SOURCE_ID
    assert stages["parents"].calls[0][1].access == EvidenceAccess(scope="public")
    assert stages["incremental"].calls[0][1].full_version_rebuild is True
    assert stages["upsert"].calls[0][1].staging_collection == "character_lore__v20260904"


@pytest.mark.asyncio
async def test_orchestrator_fails_closed_and_records_only_error_type() -> None:
    orchestrator, jobs, parents, releases, stages = _orchestrator(parser_failures=1)

    with pytest.raises(IngestionStageError, match="parse"):
        await orchestrator.run(
            IngestionRunRequest(staging_collection="world_lore__v20260904", source_id=SOURCE_ID)
        )

    assert parents.parents == []
    assert releases.releases == []
    assert stages["parents"].calls == []
    assert jobs.status_updates[-1][1:] == ("FAILED", "IngestionStageError")
    failed_event = jobs.events[-1]
    assert failed_event[1] == "IngestionFailed"
    assert failed_event[2] == {"error_type": "IngestionStageError"}


@pytest.mark.asyncio
async def test_orchestrator_rejects_parent_from_another_source_before_persistence() -> None:
    orchestrator, jobs, parents, releases, stages = _orchestrator()
    stages["parents"].output = [
        LoreParent(
            id=uuid.uuid4(),
            page_id=1,
            page_title="Test",
            heading="Lead",
            markdown="Wrong source.",
            source_file="test.wiki",
            revision_id=1,
            corpus_version="v20260904",
            source_id=uuid.uuid4(),
        )
    ]

    with pytest.raises(IngestionStageError, match="parent_manifest"):
        await orchestrator.run(
            IngestionRunRequest(
                staging_collection="character_lore__v20260904", source_id=SOURCE_ID
            )
        )

    assert parents.parents == []
    assert releases.releases == []
    assert jobs.status_updates[-1][1:] == ("FAILED", "IngestionStageError")


@pytest.mark.asyncio
async def test_orchestrator_does_not_persist_parents_when_qdrant_is_unacknowledged() -> None:
    orchestrator, jobs, parents, releases, stages = _orchestrator()
    stages["parents"].output = [
        LoreParent(
            id=uuid.uuid4(),
            page_id=1,
            page_title="Test",
            heading="Lead",
            markdown="Staged but unacknowledged content.",
            source_file="test.wiki",
            revision_id=1,
            corpus_version="v20260904",
            source_id=SOURCE_ID,
        )
    ]
    stages["upsert"].failed_items = 1

    with pytest.raises(IngestionStageError, match="qdrant_upsert"):
        await orchestrator.run(
            IngestionRunRequest(
                staging_collection="character_lore__v20260904", source_id=SOURCE_ID
            )
        )

    assert parents.parents == []
    assert releases.releases == []
    assert "ParentsPersisted" not in [event[1] for event in jobs.events]
    assert jobs.status_updates[-1][1:] == ("FAILED", "IngestionStageError")


def test_orchestrator_rejects_active_alias_as_write_target() -> None:
    with pytest.raises(ValueError, match="non-active valid corpus version"):
        IngestionRunRequest(staging_collection="character_lore__active", source_id=SOURCE_ID)


def test_orchestrator_rejects_non_lore_or_unknown_staging_collections() -> None:
    with pytest.raises(ValueError, match="not a configured lore collection"):
        IngestionRunRequest(staging_collection="memories__v20260904", source_id=SOURCE_ID)
    with pytest.raises(ValueError, match="not a configured lore collection"):
        IngestionRunRequest(staging_collection="other_lore__v20260904", source_id=SOURCE_ID)
