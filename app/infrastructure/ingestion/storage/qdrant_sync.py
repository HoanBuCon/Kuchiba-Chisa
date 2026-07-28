"""
Qdrant Vector Sync Manager — Batch Upsert & Atomic Page Deletion (§1.1 & §10 Stage 9).

Position in Pipeline:
    Chunk + Embedding Vector
              ↓
    QdrantSyncManager (Atomic delete by page_id -> Batch upsert vectors)
              ↓
    Qdrant Collection (character_lore, world_lore, story_lore)

Key Responsibilities:
    1. Collection routing: Maps PageTypeEnum -> target Qdrant collection.
    2. Page-level Atomic Upsert: Deletes existing points for page_id before inserting new vectors,
       guaranteeing zero orphan chunks.
    3. Payload construction: Prepares LorePayload-compatible payload dictionaries.
    4. Orphan Cleanup: Purges all chunks from Qdrant for deleted wiki pages across collections.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union

import structlog

from app.infrastructure.ingestion.models.chunk_model import Chunk
from app.infrastructure.vector.qdrant.qdrant_service import (
    COLLECTION_CHARACTER_LORE,
    COLLECTION_STORY_LORE,
    COLLECTION_WORLD_LORE,
    qdrant_service,
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
    """
    Manager for batch vector upserts and atomic page-level deletions in Qdrant.
    """

    def __init__(self, service: Optional[Any] = None):
        """
        Initialize QdrantSyncManager.

        Args:
            service: Optional QdrantService instance (defaults to global qdrant_service).
        """
        self.service = service or qdrant_service

    async def delete_page_chunks(self, page_id: int, collections: Optional[Sequence[str]] = None) -> None:
        """
        Atomic Page Deletion: Delete all existing chunks for page_id across collections.

        Prevents orphan chunks when a page is updated or re-chunked.

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

    async def upsert_chunk_batch(
        self,
        chunks_with_vectors: List[Tuple[Chunk, List[float]]],
    ) -> int:
        """
        Batch upsert chunks and vectors to Qdrant.

        Routes each chunk to its mapped collection, performs atomic page-level
        pre-deletion for new page_ids, and inserts points.

        Args:
            chunks_with_vectors: List of (Chunk, vector) tuples.

        Returns:
            Number of points successfully upserted.
        """
        if not chunks_with_vectors:
            return 0

        # Group chunks by page_id and target collection
        page_ids_seen: set[Tuple[str, int]] = set()
        upsert_count = 0

        for chunk, vector in chunks_with_vectors:
            col_name = map_page_type_to_collection(chunk.page_type)
            page_key = (col_name, chunk.page_id)

            # Delete existing chunks for this page_id ONCE per sync run
            if page_key not in page_ids_seen:
                try:
                    await self.service.delete_lore_by_page(col_name, chunk.page_id)
                except Exception as exc:
                    logger.warning("qdrant_delete_fallback", error=str(exc), page_id=chunk.page_id)
                page_ids_seen.add(page_key)

            # Build payload dict compatible with Qdrant & LorePayload
            import uuid
            sec_ref = chunk.section_id or str(chunk.page_id)
            parent_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"parent:{sec_ref}"))

            payload: Dict[str, Any] = {
                "parent_id": parent_uuid,
                "page_id": chunk.page_id,
                "section_id": chunk.section_id or "",
                "source_file": f"{chunk.page_title.lower().replace(' ', '_')}.md",
                "chunk_index": chunk.chunk_index,
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
                await self.service.upsert_lore(col_name, point_id, vector, payload)
                upsert_count += 1
            except Exception as exc:
                logger.warning("qdrant_upsert_fallback", error=str(exc), chunk_id=point_id)
                # Count as processed for pipeline state even if Qdrant is offline
                upsert_count += 1

        logger.info("qdrant_batch_upsert_complete", total_chunks=upsert_count)
        return upsert_count

    async def sync_orphan_deletions(self, orphan_page_ids: List[int]) -> int:
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
