"""
Qdrant Vector Sync Manager — Batch Upsert & Atomic Page Deletion (§1.1 & §10 Stage 9).

Position in Pipeline:
    Chunk + Embedding Vector
              ↓
    QdrantSyncManager (Atomic delete by page_id -> Batch upsert vectors)
              ↓
    Qdrant Collection (character_lore, world_lore, story_lore)

Key Responsibilities:
    1. Collection routing: Maps PageTypeEnum -> logical Qdrant collection.
    2. Staged writes: Writes only to supplied versioned physical collections.
    3. Acknowledgement: Fails on every unacknowledged Qdrant write.
    4. Payload construction: Prepares LorePayload-compatible payload dictionaries.
    5. Orphan Cleanup: Uses an explicit deletion operation only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import structlog

from app.application.ingestion.errors import QdrantIngestionAcknowledgementError
from app.config.settings import settings
from app.infrastructure.ingestion.models.chunk_model import Chunk
from app.infrastructure.vector.qdrant.qdrant_service import (
    COLLECTION_CHARACTER_LORE,
    COLLECTION_STORY_LORE,
    COLLECTION_WORLD_LORE,
    qdrant_service,
    versioned_collection_name,
)

logger = structlog.get_logger(__name__)


def map_page_type_to_collection(page_type: str) -> str:
    """
    Map a page type classification to its target Qdrant collection.

    Args:
        page_type: PageTypeEnum string value (CHARACTER, WEAPON, QUEST, etc.).

    Returns:
        Qdrant collection name (character_lore, world_lore, story_lore).
    """
    pt_upper = page_type.upper().strip()

    if pt_upper == "CHARACTER":
        return COLLECTION_CHARACTER_LORE
    elif pt_upper in ("QUEST", "DIALOGUE", "TIMELINE"):
        return COLLECTION_STORY_LORE
    else:
        # WEAPON, ECHO, BOSS, REGION, FACTION, ITEM, MECHANIC, TUTORIAL, GENERIC
        return COLLECTION_WORLD_LORE


class QdrantSyncManager:
    """Manage staged, acknowledged vector upserts and explicit page deletion."""

    def __init__(self, service: Any | None = None):
        """
        Initialize QdrantSyncManager.

        Args:
            service: Optional QdrantService instance (defaults to global qdrant_service).
        """
        self.service = service or qdrant_service

    async def delete_page_chunks(
        self,
        page_id: int,
        collections: Sequence[str] | None = None,
    ) -> None:
        """
        Explicitly delete all chunks for page_id across collections.

        Standard corpus ingestion must not call this method. New corpus data is
        written to a physical staging collection and becomes visible only after
        separately authorized alias promotion passes its quality gate.

        Args:
            page_id: Target page_id.
            collections: Optional list of collections to delete from.
        """
        cols = collections or [
            COLLECTION_CHARACTER_LORE,
            COLLECTION_WORLD_LORE,
            COLLECTION_STORY_LORE,
        ]
        for col in cols:
            try:
                await self.service.delete_lore_by_page(col, page_id)
                logger.debug("qdrant_page_chunks_deleted", page_id=page_id, collection=col)
            except Exception as exc:
                logger.warning(
                    "qdrant_page_delete_error", page_id=page_id, collection=col, error=str(exc)
                )

    async def prepare_staging_targets(
        self,
        chunks: Sequence[Chunk],
        *,
        staging_version: str,
    ) -> dict[str, str]:
        """Create only the physical targets needed for a versioned corpus run.

        Creation is idempotent and never changes an active alias. Promotion is
        intentionally a separate, authorized operation after quality checks.
        """
        if not staging_version:
            raise ValueError("A non-empty staging version is required for Qdrant ingestion")

        logical_collections = {map_page_type_to_collection(chunk.page_type) for chunk in chunks}
        return {
            logical_collection: await self.service.prepare_versioned_collection(
                logical_collection,
                staging_version,
                settings.QDRANT_EMBEDDING_DIM,
            )
            for logical_collection in sorted(logical_collections)
        }

    @staticmethod
    def _require_staging_target(logical_collection: str, target_collection: str) -> None:
        """Reject active aliases and arbitrary physical collection names."""
        prefix = f"{logical_collection}__"
        if not target_collection.startswith(prefix):
            raise ValueError(
                f"Staging target {target_collection!r} is not a version of "
                f"{logical_collection!r}"
            )
        version = target_collection.removeprefix(prefix)
        if version == "active":
            raise ValueError("An active Qdrant alias cannot be used as an ingestion target")
        if versioned_collection_name(logical_collection, version) != target_collection:
            raise ValueError("Invalid physical Qdrant staging target")

    async def upsert_chunk_batch(
        self,
        chunks_with_vectors: list[tuple[Chunk, list[float]]],
        *,
        target_collections: Mapping[str, str],
    ) -> int:
        """
        Upsert all chunks into explicitly supplied physical staging collections.

        A return value is emitted only when every point has been acknowledged
        by Qdrant. On partial failure the caller receives a typed exception and
        must retry the same staging version; the active alias is untouched.

        Args:
            chunks_with_vectors: List of (Chunk, vector) tuples.
            target_collections: Logical lore collection -> physical versioned
                collection. Active aliases and base collection names are rejected.

        Returns:
            Number of points successfully upserted.
        """
        if not chunks_with_vectors:
            return 0

        upsert_count = 0

        for chunk, vector in chunks_with_vectors:
            logical_collection = map_page_type_to_collection(chunk.page_type)
            try:
                target_collection = target_collections[logical_collection]
            except KeyError as exc:
                raise ValueError(
                    f"Missing staging target for {logical_collection!r}"
                ) from exc
            self._require_staging_target(logical_collection, target_collection)

            # Build payload dict compatible with Qdrant & LorePayload
            import uuid
            sec_ref = chunk.section_id or str(chunk.page_id)
            parent_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"parent:{sec_ref}"))

            payload: dict[str, Any] = {
                "parent_id": parent_uuid,
                "page_id": chunk.page_id,
                "section_id": chunk.section_id or "",
                "source_file": f"{chunk.page_title.lower().replace(' ', '_')}.md",
                "revision_id": chunk.revision_id,
                "chunk_index": chunk.chunk_index,
                "chunk_start_offset": chunk.chunk_start_offset,
                "chunk_end_offset": chunk.chunk_end_offset,
                "text_content": chunk.text_content,
                "heading_path": chunk.heading_path,
                "section_depth": chunk.section_depth,
                "canonical_name": chunk.canonical_name,
                "entity_type": chunk.entity_type,
                "entities": chunk.entities,
                "region": chunk.region,
                "faction": chunk.faction,
                "element": chunk.element,
                "game_version": chunk.game_version,
                "page_type": chunk.page_type,
                "source_type": chunk.source_type,
                "schema_version": chunk.schema_version,
            }

            point_id = str(chunk.chunk_id)
            try:
                await self.service.upsert_lore(target_collection, point_id, vector, payload)
                upsert_count += 1
            except Exception as exc:
                logger.error(
                    "qdrant_upsert_unacknowledged",
                    collection=target_collection,
                    acknowledged_count=upsert_count,
                    chunk_id=point_id,
                    error_type=type(exc).__name__,
                )
                raise QdrantIngestionAcknowledgementError(
                    target_collection=target_collection,
                    failed_point_id=point_id,
                    acknowledged_count=upsert_count,
                ) from exc

        logger.info("qdrant_batch_upsert_complete", total_chunks=upsert_count)
        return upsert_count

    async def sync_orphan_deletions(self, orphan_page_ids: list[int]) -> int:
        """
        Purge all chunks from Qdrant for deleted wiki pages across all collections.

        Args:
            orphan_page_ids: List of page IDs to purge.

        Returns:
            Number of orphan pages purged.
        """
        if not orphan_page_ids:
            return 0

        purged = 0
        for p_id in orphan_page_ids:
            await self.delete_page_chunks(p_id)
            purged += 1

        logger.info("qdrant_orphan_purge_complete", count=purged)
        return purged
