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
from pydantic import BaseModel, ConfigDict, Field
from app.config.settings import settings
from app.infrastructure.logging.logger import get_logger
from app.domain.entities.memory import MemoryTier, MemoryPayload

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

# Production Pipeline collections
COLLECTION_CHARACTER_LORE = "character_lore"
COLLECTION_WORLD_LORE = "world_lore"
COLLECTION_STORY_LORE = "story_lore"
COLLECTION_MEMORIES = "memories"

ALL_COLLECTIONS = [
    COLLECTION_EMOTIONAL_MEMORIES,
    COLLECTION_CONVERSATION_SUMMARIES,
    COLLECTION_PERSONA_EMBEDDINGS,
    COLLECTION_USER_FACTS,
    COLLECTION_CHARACTER_LORE,
    COLLECTION_WORLD_LORE,
    COLLECTION_STORY_LORE,
    COLLECTION_MEMORIES,
]


# ─── Qdrant Service ───────────────────────────────────────────────────────────
from app.domain.interfaces.vector_store import IVectorStore

class QdrantService(IVectorStore):
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
        try:
            info = await self._client.get_collection(name)
            existing_dim = None
            vectors_config = info.config.params.vectors
            if hasattr(vectors_config, "size"):
                existing_dim = vectors_config.size
            elif hasattr(vectors_config, "vectors") and hasattr(vectors_config.vectors, "size"):
                existing_dim = vectors_config.vectors.size
            elif isinstance(vectors_config, dict) and len(vectors_config) > 0:
                first_val = list(vectors_config.values())[0]
                existing_dim = getattr(first_val, "size", None)
            
            if existing_dim is not None and existing_dim != vector_size:
                log.warning("Qdrant collection dimension mismatch, recreating", collection=name, expected=vector_size, found=existing_dim)
                await self._client.delete_collection(name)
            else:
                log.info("Collection already exists with correct dimensions, skipping", collection=name)
                return
        except Exception:
            # Collection does not exist or error reading config; proceed to create
            pass

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

    # ── Vector Upsert & Prune ──────────────────────────────────────────────
    async def prune_user_memories(self, collection: str, user_id: str, cap: int = 200) -> None:
        """
        VPS Optimization: Enforce a hard cap of 200 LTM entries per user.
        If exceeded, deletes the lowest importance memories (excluding critical tier).
        """
        user_filter = Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        )
        count_result = await self._client.count(
            collection_name=collection,
            count_filter=user_filter,
            exact=True
        )
        
        if count_result.count > cap:
            num_to_delete = count_result.count - cap
            # Fetch all for the user to sort in memory (since max is roughly ~200, this is extremely fast)
            points, _ = await self._client.scroll(
                collection_name=collection,
                scroll_filter=user_filter,
                limit=cap + 50,
                with_payload=True
            )
            
            # Filter out critical tier
            prunable = [p for p in points if p.payload and p.payload.get("memory_tier") != MemoryTier.CRITICAL.value]
            # Sort by importance ascending (lowest first)
            prunable.sort(key=lambda x: x.payload.get("importance_score", 1.0))
            
            if prunable and num_to_delete > 0:
                to_delete = prunable[:num_to_delete]
                ids_to_delete = [p.id for p in to_delete]
                await self.delete_points(collection, ids_to_delete)
                log.info("Pruned LTM entries for user mapping to VPS limits", user_id=user_id, pruned_count=len(ids_to_delete))

    async def upsert_memory(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        payload: MemoryPayload,
    ) -> None:
        """
        Upsert a single memory point.
        Payload MUST include 'user_id' for isolation enforcement.
        """
        structured = PointStruct(
            id=point_id, 
            vector=vector, 
            payload=payload.model_dump()
        )
        await self._client.upsert(collection_name=collection, points=[structured], wait=True)
        
        # Enforce multi-user bounds immediately after insert
        await self.prune_user_memories(collection, user_id=payload.user_id, cap=200)

    # ── Vector Search with User Isolation ─────────────────────────
    async def search_by_user(
        self,
        collection: str,
        query_vector: list[float],
        user_id: str,
        limit: int = 10,
        score_threshold: float = 0.65,
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

    async def delete_by_user(self, collection: str, user_id: str) -> None:
        from qdrant_client.http.models import FilterSelector
        user_filter = Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        )
        await self._client.delete(
            collection_name=collection,
            points_selector=FilterSelector(filter=user_filter),
            wait=True,
        )

    # ── Lore Search (global — no user isolation) ───────────────────
    async def search_lore(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 4,
        score_threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        Searches lore collection without user_id filter.
        Lore is global shared character knowledge.
        """
        results = await self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [
            {"id": r.id, "score": r.score, "payload": r.payload or {}}
            for r in results
        ]

    async def upsert_lore(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        text_content: str,
        section: str = "general",
        payload: dict = None,
    ) -> None:
        """Upsert lore chunk — no user_id required."""
        from qdrant_client.models import PointStruct as PS
        upsert_payload = {
            "text_content": text_content,
            "section": section,
        }
        if payload:
            upsert_payload.update(payload)
        await self._client.upsert(
            collection_name=collection,
            points=[PS(id=point_id, vector=vector, payload=upsert_payload)],
            wait=True,
        )

    # ── Disconnect ─────────────────────────────────────────────────
    async def disconnect(self) -> None:
        await self._client.close()
        log.info("Qdrant client disconnected")


# ── Module-level singleton ───────────────────────────────────────────
qdrant_service = QdrantService()
