"""ING-02 tests that a new physical corpus version cannot omit known chunks."""

from __future__ import annotations

import uuid

import pytest

from app.application.ingestion.stages.incremental_router_stage import (
    IncrementalRouterInput,
    IncrementalRouterStage,
)
from app.domain.entities.chunk_models import ProcessingChunk


class _ChunkRepository:
    async def check_hash_exists(self, _: str) -> bool:
        raise AssertionError("full version builds must not skip chunks from global hash state")


class _JobRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def log_event(self, _: uuid.UUID, __: str, details: dict[str, object]) -> None:
        self.events.append(details)


def _chunk() -> ProcessingChunk:
    return ProcessingChunk(
        parent_id=uuid.uuid4(),
        page_id=19,
        revision_id=97,
        page_title="Chisa",
        chunk_index=0,
        text_content="Chisa studies at Startorch Academy.",
        chunk_hash="a" * 64,
    )


@pytest.mark.asyncio
async def test_full_version_rebuild_never_skips_a_chunk_from_global_state() -> None:
    job_repository = _JobRepository()
    chunk = _chunk()
    stage = IncrementalRouterStage(_ChunkRepository(), job_repository)

    result = await stage.execute(
        uuid.uuid4(),
        IncrementalRouterInput(chunks=[chunk], full_version_rebuild=True),
    )

    assert result.output == [chunk]
    assert chunk.skip_embedding is False
    assert result.metrics.items_skipped == 0
    assert result.metrics.details == {"mode": "full_version_rebuild"}
