"""DATA-02 regressions for staged, acknowledged Qdrant ingestion."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.application.ingestion.errors import QdrantIngestionAcknowledgementError
from app.config.settings import settings
from app.infrastructure.ingestion.models.chunk_model import Chunk
from app.infrastructure.ingestion.storage.qdrant_sync import QdrantSyncManager
from app.infrastructure.vector.qdrant.qdrant_service import (
    COLLECTION_CHARACTER_LORE,
    COLLECTION_WORLD_LORE,
)


def _chunk(*, page_id: int, page_type: str, chunk_index: int) -> Chunk:
    return Chunk(
        chunk_id=UUID(int=page_id * 10 + chunk_index + 1),
        page_id=page_id,
        text_content=f"Lore chunk {page_id}-{chunk_index}",
        text_hash=f"sha256:{page_id}-{chunk_index}",
        token_count_approx=32,
        chunk_index=chunk_index,
        page_title="Chisa",
        page_type=page_type,
    )


class FakeQdrantService:
    def __init__(self, fail_point_id: str | None = None) -> None:
        self.fail_point_id = fail_point_id
        self.prepared: list[tuple[str, str, int]] = []
        self.upserts: list[tuple[str, str]] = []
        self.delete_calls: list[tuple[str, int]] = []

    async def prepare_versioned_collection(
        self, logical_collection: str, version: str, vector_size: int
    ) -> str:
        self.prepared.append((logical_collection, version, vector_size))
        return f"{logical_collection}__{version}"

    async def upsert_lore(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        payload: dict[str, object],
    ) -> None:
        del vector, payload
        self.upserts.append((collection, point_id))
        if point_id == self.fail_point_id:
            raise RuntimeError("Qdrant timeout")

    async def delete_lore_by_page(self, collection: str, page_id: int) -> None:
        self.delete_calls.append((collection, page_id))


@pytest.mark.asyncio
async def test_staged_batch_never_deletes_active_page_chunks() -> None:
    chunks = [
        _chunk(page_id=10, page_type="CHARACTER", chunk_index=0),
        _chunk(page_id=11, page_type="REGION", chunk_index=0),
    ]
    service = FakeQdrantService()
    manager = QdrantSyncManager(service=service)

    targets = await manager.prepare_staging_targets(chunks, staging_version="data02_test")
    acknowledged = await manager.upsert_chunk_batch(
        [(chunks[0], [0.1, 0.2]), (chunks[1], [0.3, 0.4])],
        target_collections=targets,
    )

    assert acknowledged == 2
    assert targets == {
        COLLECTION_CHARACTER_LORE: "character_lore__data02_test",
        COLLECTION_WORLD_LORE: "world_lore__data02_test",
    }
    assert service.prepared == [
        (COLLECTION_CHARACTER_LORE, "data02_test", settings.QDRANT_EMBEDDING_DIM),
        (COLLECTION_WORLD_LORE, "data02_test", settings.QDRANT_EMBEDDING_DIM),
    ]
    assert service.upserts == [
        ("character_lore__data02_test", str(chunks[0].chunk_id)),
        ("world_lore__data02_test", str(chunks[1].chunk_id)),
    ]
    assert service.delete_calls == []


@pytest.mark.asyncio
async def test_unacknowledged_write_fails_partial_batch_and_retry_reuses_staging_target() -> None:
    first = _chunk(page_id=10, page_type="CHARACTER", chunk_index=0)
    second = _chunk(page_id=10, page_type="CHARACTER", chunk_index=1)
    service = FakeQdrantService(fail_point_id=str(second.chunk_id))
    manager = QdrantSyncManager(service=service)
    targets = {COLLECTION_CHARACTER_LORE: "character_lore__retry_v1"}
    batch = [(first, [0.1, 0.2]), (second, [0.3, 0.4])]

    with pytest.raises(QdrantIngestionAcknowledgementError) as error:
        await manager.upsert_chunk_batch(batch, target_collections=targets)

    assert error.value.acknowledged_count == 1
    assert error.value.failed_point_id == str(second.chunk_id)
    assert service.delete_calls == []

    service.fail_point_id = None
    acknowledged = await manager.upsert_chunk_batch(batch, target_collections=targets)

    assert acknowledged == 2
    assert {collection for collection, _ in service.upserts} == {"character_lore__retry_v1"}


@pytest.mark.asyncio
async def test_active_alias_or_missing_target_is_rejected_before_write() -> None:
    chunk = _chunk(page_id=10, page_type="CHARACTER", chunk_index=0)
    service = FakeQdrantService()
    manager = QdrantSyncManager(service=service)

    with pytest.raises(ValueError, match="Missing staging target"):
        await manager.upsert_chunk_batch([(chunk, [0.1, 0.2])], target_collections={})
    with pytest.raises(ValueError, match="active Qdrant alias"):
        await manager.upsert_chunk_batch(
            [(chunk, [0.1, 0.2])],
            target_collections={COLLECTION_CHARACTER_LORE: "character_lore__active"},
        )

    assert service.upserts == []
    assert service.delete_calls == []
