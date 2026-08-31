import uuid

import pytest

from app.application.ingestion.stages.qdrant_upsert_stage import (
    QdrantUpsertInput,
    QdrantUpsertStage,
)
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.entities.lore import LorePayload


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted_pages: list[tuple[str, int]] = []
        self.upserted: list[tuple[str, str, list[float], dict[str, object]]] = []

    async def delete_lore_by_page(self, collection: str, page_id: int) -> None:
        self.deleted_pages.append((collection, page_id))

    async def upsert_lore(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        payload: dict[str, object],
    ) -> None:
        self.upserted.append((collection, point_id, vector, payload))


class FakePipelineJobRepository:
    def __init__(self) -> None:
        self.events: list[tuple[uuid.UUID, str, dict[str, object]]] = []

    async def log_event(
        self, job_id: uuid.UUID, event_type: str, payload: dict[str, object]
    ) -> None:
        self.events.append((job_id, event_type, payload))


def make_chunk(*, vector: list[float] | None, payload: LorePayload | None) -> ProcessingChunk:
    return ProcessingChunk(
        parent_id=uuid.uuid4(),
        page_id=42,
        revision_id=1,
        page_title="Chisa",
        chunk_index=0,
        text_content="Test lore",
        chunk_hash="chunk-hash",
        vector=vector,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_upsert_stage_only_writes_complete_embedded_chunks() -> None:
    payload = LorePayload(
        parent_id=str(uuid.uuid4()),
        page_id=42,
        source_file="chisa.md",
        text_content="Test lore",
    )
    store = FakeVectorStore()
    jobs = FakePipelineJobRepository()
    stage = QdrantUpsertStage(store, jobs)
    valid_chunk = make_chunk(vector=[0.1, 0.2], payload=payload)
    missing_payload = make_chunk(vector=[0.3, 0.4], payload=None)
    missing_vector = make_chunk(vector=None, payload=payload)

    result = await stage.execute(
        uuid.uuid4(),
        QdrantUpsertInput(chunks=[valid_chunk, missing_payload, missing_vector]),
    )

    assert store.deleted_pages == [("character_lore", 42)]
    assert len(store.upserted) == 1
    assert store.upserted[0][1] == str(valid_chunk.chunk_id)
    assert result.metrics.items_processed == 1
    assert result.metrics.items_skipped == 2
    assert jobs.events[0][1] == "QdrantUpsertComplete"
