"""
Image Memory Retriever for Kuchiba Chisa.
Location: app/domain/services/rag/retriever_image_memory.py
"""

from __future__ import annotations
import os
import time
import asyncio
from typing import List, Dict, Any, Optional
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, PointIdsList

from app.domain.entities.image_memory import RetrievedImageMemory
from app.domain.interfaces.vector_store import IVectorStore
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.vector.qdrant.qdrant_service import COLLECTION_IMAGE_MEMORIES

log = get_logger(__name__)


class ImageMemoryRetriever:
    """
    Retrieves and ranks multimodal visual memories from Qdrant 'image_memories'.
    Enforces strict user isolation, guild privacy filtering, and self-healing orphan cleanup.
    """

    def __init__(self, vector_store: IVectorStore) -> None:
        self.vector_store = vector_store

    async def _delete_orphan_points(self, qdrant_client: Any, point_ids: List[str]) -> None:
        """Deletes dangling/orphan points from Qdrant collection 'image_memories'."""
        try:
            await qdrant_client.delete(
                collection_name=COLLECTION_IMAGE_MEMORIES,
                points_selector=PointIdsList(points=point_ids),
            )
            log.info("Successfully pruned orphan image memory points from Qdrant", count=len(point_ids))
        except Exception as err:
            log.warning("Failed to prune orphan image memory points", error=str(err))

    async def retrieve_image_memories(
        self,
        query_vector: List[float],
        user_id: str,
        guild_id: Optional[str] = None,
        is_community: bool = False,
        limit: int = 5,
        score_threshold: float = 0.68,
    ) -> List[RetrievedImageMemory]:
        """
        Retrieves matching visual memories from Qdrant.
        Filters by user_id in DM, or guild_id/user_id in Community channels.
        Automatically verifies physical file existence and self-heals pruned files.
        """
        if not query_vector:
            return []

        qdrant_client = getattr(self.vector_store, "_client", None)
        if not qdrant_client:
            log.warning("Qdrant client not available for image memory retrieval")
            return []

        # Construct privacy filter
        must_conditions = []
        if not is_community or not guild_id:
            # Direct DM: Strictly isolate by user_id
            must_conditions.append(
                FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))
            )
        else:
            # Community Guild: Match photos in the same guild or uploaded by the user
            must_conditions.append(
                FieldCondition(key="guild_id", match=MatchValue(value=str(guild_id)))
            )

        search_filter = Filter(must=must_conditions)

        try:
            results = await qdrant_client.search(
                collection_name=COLLECTION_IMAGE_MEMORIES,
                query_vector=query_vector,
                query_filter=search_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
        except Exception as e:
            log.error("Failed to query image memories from Qdrant", user_id=user_id, error=str(e))
            return []

        if not results:
            log.info("No matching image memories found", user_id=user_id, threshold=score_threshold)
            return []

        retrieved: List[RetrievedImageMemory] = []
        orphan_point_ids: List[str] = []

        for hit in results:
            payload = hit.payload or {}
            local_path = payload.get("local_path")

            # Self-Healing Check: If image was stored locally but file was pruned by LRU quota / deleted
            if local_path and not os.path.exists(local_path):
                log.warning("Pruned/Orphan image memory detected, skipping and queuing for self-healing deletion", image_id=payload.get("image_id"), local_path=local_path)
                orphan_point_ids.append(str(hit.id))
                continue

            retrieved.append(
                RetrievedImageMemory(
                    image_id=str(payload.get("image_id", hit.id)),
                    url=payload.get("url", ""),
                    thumbnail_url=payload.get("thumbnail_url"),
                    local_path=local_path,
                    visual_caption=payload.get("visual_caption", ""),
                    tags=payload.get("tags", []),
                    user_id=payload.get("user_id", str(user_id)),
                    guild_id=payload.get("guild_id"),
                    score=round(float(hit.score), 4),
                    created_at=int(payload.get("created_at", time.time())),
                )
            )

        # Asynchronously clean up orphan points from Qdrant in background
        if orphan_point_ids and qdrant_client:
            asyncio.create_task(
                self._delete_orphan_points(qdrant_client, orphan_point_ids)
            )

        # Sort by similarity score descending
        retrieved.sort(key=lambda x: x.score, reverse=True)
        log.info(
            "Retrieved image memories successfully",
            count=len(retrieved),
            top_score=retrieved[0].score if retrieved else None,
            user_id=user_id,
        )
        return retrieved
