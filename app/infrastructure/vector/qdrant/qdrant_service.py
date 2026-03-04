from __future__ import annotations

from typing import Any, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
    OptimizersConfigDiff,
    PointStruct,
    VectorParams,
)

from app.config.settings import settings
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

# ─── Qdrant Async Client ──────────────────────────────────────────────────────

_qdrant_client: Optional[AsyncQdrantClient] = None


def get_qdrant_client() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=30,
        )
    return _qdrant_client


# ─── Collection Name Constants ────────────────────────────────────────────────

COLLECTION_EMOTIONAL_MEMORIES = "emotional_memories"
COLLECTION_CONVERSATION_SUMMARIES = "conversation_summaries"
COLLECTION_PERSONA_EMBEDDINGS = "persona_embeddings"
COLLECTION_USER_FACTS = "user_facts"

ALL_COLLECTIONS = [
    COLLECTION_EMOTIONAL_MEMORIES,
    COLLECTION_CONVERSATION_SUMMARIES,
    COLLECTION_PERSONA_EMBEDDINGS,
    COLLECTION_USER_FACTS,
]


# ─── Qdrant Service ───────────────────────────────────────────────────────────

class QdrantService:
    """
    Async Qdrant service for all vector operations.
    CRITICAL: All searches enforce user_id filtering for strict user isolation.
    """

    def __init__(self) -> None:
        self._client = get_qdrant_client()

    # ── Health ─────────────────────────────────────────────────────
    async def health_check(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception as e:
            log.error("Qdrant health check failed", error=str(e))
            return False

    # ── Collection Management ──────────────────────────────────────
    async def collection_exists(self, name: str) -> bool:
        try:
            await self._client.get_collection(name)
            return True
        except Exception:
            return False

    async def create_collection(
        self,
        name: str,
        vector_size: int,
        distance: Distance = Distance.COSINE,
    ) -> None:
        if await self.collection_exists(name):
            log.info("Collection already exists, skipping", collection=name)
            return

        await self._client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=vector_size, distance=distance),
            optimizers_config=OptimizersConfigDiff(indexing_threshold=20000),
        )
        log.info("Qdrant collection created", collection=name, size=vector_size)

    async def initialize_all_collections(self) -> None:
        """
        Placeholder: Creates all required collections on startup.
        Vector size pulled from settings (default: 1536 for text-embedding-3-small).
        """
        dim = settings.QDRANT_EMBEDDING_DIM
        for collection in ALL_COLLECTIONS:
            await self.create_collection(collection, vector_size=dim)
        log.info("All Qdrant collections initialized", count=len(ALL_COLLECTIONS))

    # ── Vector Upsert ──────────────────────────────────────────────
    async def upsert(
        self,
        collection: str,
        points: list[dict[str, Any]],
    ) -> None:
        """
        Upsert a list of points. Each point must have 'id', 'vector', and 'payload'.
        Payload MUST include 'user_id' for isolation enforcement.
        """
        structured = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points
        ]
        await self._client.upsert(collection_name=collection, points=structured, wait=True)

    # ── Vector Search with User Isolation ─────────────────────────
    async def search_by_user(
        self,
        collection: str,
        query_vector: list[float],
        user_id: str,
        limit: int = 10,
        score_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """
        CRITICAL: All searches MUST use this method to enforce user isolation.
        Direct search() calls without user_id filter are not permitted outside of this service.
        """
        user_filter = Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        )

        results = await self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=user_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

        return [
            {"id": r.id, "score": r.score, "payload": r.payload or {}}
            for r in results
        ]

    # ── Delete ─────────────────────────────────────────────────────
    async def delete_points(self, collection: str, ids: list[str | int]) -> None:
        from qdrant_client.http.models import PointIdsList
        await self._client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=ids),
            wait=True,
        )

    # ── Disconnect ─────────────────────────────────────────────────
    async def disconnect(self) -> None:
        await self._client.close()
        log.info("Qdrant client disconnected")


# ── Module-level singleton ───────────────────────────────────────────
qdrant_service = QdrantService()
