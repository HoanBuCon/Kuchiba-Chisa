"""
Image Memory Retriever for Kuchiba Chisa.
Location: app/domain/services/rag/retriever_image_memory.py
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from functools import partial
from typing import Any

from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    HasIdCondition,
    MatchValue,
    Range,
)

from app.domain.entities.image_memory import RetrievedImageMemory
from app.domain.interfaces.vector_store import IVectorStore
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.vector.qdrant.qdrant_service import COLLECTION_IMAGE_MEMORIES
from app.shared.utils.maintenance_tasks import MaintenanceTaskSupervisor

log = get_logger(__name__)


class ImageMemoryRetriever:
    """
    Retrieves and ranks multimodal visual memories from Qdrant 'image_memories'.
    Enforces strict user isolation, guild privacy filtering, and self-healing orphan cleanup.
    """

    def __init__(self, vector_store: IVectorStore) -> None:
        self.vector_store = vector_store

    async def _delete_orphan_point(
        self,
        qdrant_client: Any,
        *,
        point_id: str,
        expected_payload_fingerprint: str,
        expected_local_path: str,
        expected_image_id: str,
    ) -> None:
        """Delete only the exact point version that was observed as an orphan."""
        records = await qdrant_client.retrieve(
            collection_name=COLLECTION_IMAGE_MEMORIES,
            ids=[point_id],
            with_payload=True,
        )
        record = next((item for item in records if str(item.id) == point_id), None)
        if record is None:
            return
        current_payload = record.payload or {}
        if _payload_fingerprint(point_id, current_payload) != expected_payload_fingerprint:
            log.info("Skipped stale orphan cleanup after image-memory point changed")
            return
        if os.path.exists(expected_local_path):
            log.info("Skipped stale orphan cleanup after local image was restored")
            return

        # Payload predicates provide a final server-side identity check in addition
        # to the immutable payload fingerprint revalidation above.
        await qdrant_client.delete(
            collection_name=COLLECTION_IMAGE_MEMORIES,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        HasIdCondition(has_id=[point_id]),
                        FieldCondition(
                            key="local_path", match=MatchValue(value=expected_local_path)
                        ),
                        FieldCondition(
                            key="image_id", match=MatchValue(value=expected_image_id)
                        ),
                    ]
                )
            ),
            wait=True,
        )
        log.info("Successfully pruned one orphan image-memory point")

    async def retrieve_image_memories(
        self,
        query_vector: list[float],
        user_id: str,
        guild_id: str | None = None,
        is_community: bool = False,
        limit: int = 5,
        score_threshold: float = 0.68,
    ) -> list[RetrievedImageMemory]:
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

        # Exclude expired values in Qdrant rather than letting them consume the
        # limited top-k result window. Missing ``expires_at`` remains eligible.
        search_filter = Filter(
            must=must_conditions,
            must_not=[
                FieldCondition(
                    key="expires_at",
                    range=Range(lte=int(time.time())),
                )
            ],
        )

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

        retrieved: list[RetrievedImageMemory] = []
        orphan_candidates: list[tuple[str, str, str, str]] = []

        for hit in results:
            payload = hit.payload or {}
            expires_at = payload.get("expires_at")
            if isinstance(expires_at, int) and expires_at <= int(time.time()):
                continue
            local_path = payload.get("local_path")

            # Self-Healing Check: If image was stored locally but file was pruned by LRU quota / deleted
            if isinstance(local_path, str) and local_path and not os.path.exists(local_path):
                log.warning("Pruned/Orphan image memory detected, skipping and queuing for self-healing deletion", image_id=payload.get("image_id"), local_path=local_path)
                point_id = str(hit.id)
                orphan_candidates.append(
                    (
                        point_id,
                        _payload_fingerprint(point_id, payload),
                        local_path,
                        str(payload.get("image_id", point_id)),
                    )
                )
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

        for point_id, fingerprint, local_path, image_id in orphan_candidates:
            MaintenanceTaskSupervisor.schedule(
                key=f"image-memory-orphan:{point_id}",
                operation=partial(
                    self._delete_orphan_point,
                    qdrant_client,
                    point_id=point_id,
                    expected_payload_fingerprint=fingerprint,
                    expected_local_path=local_path,
                    expected_image_id=image_id,
                ),
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


def _payload_fingerprint(point_id: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"point_id": point_id, "payload": payload},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
