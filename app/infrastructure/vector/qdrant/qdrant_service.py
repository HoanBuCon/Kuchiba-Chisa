from __future__ import annotations
from typing import Any, Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    Filter,
    FieldCondition,
    HnswConfigDiff,
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

COLLECTION_CHARACTER_LORE = "character_lore"
COLLECTION_WORLD_LORE = "world_lore"
COLLECTION_STORY_LORE = "story_lore"
COLLECTION_MEMORIES = "memories"
COLLECTION_GUILD_MEMORIES = "guild_memories"
COLLECTION_IMAGE_MEMORIES = "image_memories"

ALL_COLLECTIONS = [
    COLLECTION_CHARACTER_LORE,
    COLLECTION_WORLD_LORE,
    COLLECTION_STORY_LORE,
    COLLECTION_MEMORIES,
    COLLECTION_GUILD_MEMORIES,
    COLLECTION_IMAGE_MEMORIES,
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
            vectors_config = info.config.params.vectors
            existing_dim: int | None
            if isinstance(vectors_config, VectorParams):
                existing_dim = vectors_config.size
            elif isinstance(vectors_config, dict) and len(vectors_config) > 0:
                first_val = list(vectors_config.values())[0]
                existing_dim = first_val.size
            else:
                existing_dim = None
            
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
            vectors_config=VectorParams(size=vector_size, distance=distance, on_disk=True),
            hnsw_config=HnswConfigDiff(on_disk=True),
            optimizers_config=OptimizersConfigDiff(indexing_threshold=20000),
            on_disk_payload=True,
        )
        log.info("Qdrant collection created", collection=name, size=vector_size)

        # Optimize payload indexes for Entity-Centric Retrieval
        if name in ["lore", "character_lore", "world_lore", "story_lore"]:
            try:
                from qdrant_client.http.models import PayloadSchemaType
                for field in ["entities", "region", "faction", "canonical_name"]:
                    await self._client.create_payload_index(
                        collection_name=name,
                        field_name=field,
                        field_schema=PayloadSchemaType.KEYWORD,
                        wait=True
                    )
                log.info("Qdrant payload indexes created", collection=name)
            except Exception as e:
                log.error("Failed to create payload indexes", collection=name, error=str(e))

    async def ensure_payload_indexes(self) -> None:
        """Ensures all lore and memory collections have keyword indexes for fast entity/metadata filtering."""
        from qdrant_client.http.models import PayloadSchemaType
        lore_cols = [COLLECTION_CHARACTER_LORE, COLLECTION_WORLD_LORE, COLLECTION_STORY_LORE]
        fields = ["entities", "region", "faction", "canonical_name"]
        for col in lore_cols:
            if await self.collection_exists(col):
                for f in fields:
                    try:
                        await self._client.create_payload_index(
                            collection_name=col,
                            field_name=f,
                            field_schema=PayloadSchemaType.KEYWORD,
                            wait=False
                        )
                    except Exception:
                        pass

        # Ensure memories collection has indexes on user_id and conversation_id for fast isolation
        if await self.collection_exists(COLLECTION_MEMORIES):
            for f in ["user_id", "conversation_id", "memory_type"]:
                try:
                    await self._client.create_payload_index(
                        collection_name=COLLECTION_MEMORIES,
                        field_name=f,
                        field_schema=PayloadSchemaType.KEYWORD,
                        wait=False
                    )
                except Exception:
                    pass

        # Ensure guild_memories collection has indexes on guild_id, memory_type, and expires_at
        if await self.collection_exists(COLLECTION_GUILD_MEMORIES):
            for f in ["guild_id", "channel_id", "memory_type"]:
                try:
                    await self._client.create_payload_index(
                        collection_name=COLLECTION_GUILD_MEMORIES,
                        field_name=f,
                        field_schema=PayloadSchemaType.KEYWORD,
                        wait=False
                    )
                except Exception:
                    pass
            try:
                from qdrant_client.http.models import PayloadSchemaType as PST
                await self._client.create_payload_index(
                    collection_name=COLLECTION_GUILD_MEMORIES,
                    field_name="expires_at",
                    field_schema=PST.INTEGER,
                    wait=False
                )
            except Exception:
                pass

        # Ensure image_memories collection has indexes on user_id, guild_id, image_id, tags, created_at
        if await self.collection_exists(COLLECTION_IMAGE_MEMORIES):
            for f in ["user_id", "guild_id", "image_id", "tags"]:
                try:
                    await self._client.create_payload_index(
                        collection_name=COLLECTION_IMAGE_MEMORIES,
                        field_name=f,
                        field_schema=PayloadSchemaType.KEYWORD,
                        wait=False
                    )
                except Exception:
                    pass
            try:
                from qdrant_client.http.models import PayloadSchemaType as PST
                await self._client.create_payload_index(
                    collection_name=COLLECTION_IMAGE_MEMORIES,
                    field_name="created_at",
                    field_schema=PST.INTEGER,
                    wait=False
                )
            except Exception:
                pass
        log.info("Qdrant payload indexes ensured across all collections ✓")

    async def initialize_all_collections(self) -> None:
        """
        Placeholder: Creates all required collections on startup.
        Vector size pulled from settings (default: 1536 for text-embedding-3-small).
        """
        dim = settings.QDRANT_EMBEDDING_DIM
        for collection in ALL_COLLECTIONS:
            await self.create_collection(collection, vector_size=dim)
        await self.ensure_payload_indexes()
        log.info("All Qdrant collections initialized", count=len(ALL_COLLECTIONS))

    # ── Vector Upsert & Prune ──────────────────────────────────────────────
    async def prune_user_memories(
        self,
        collection: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        cap: int = 200
    ) -> None:
        """
        VPS Optimization: Enforce a hard cap of 200 LTM entries per conversation/user.
        If exceeded, deletes the lowest importance memories (excluding critical tier).
        """
        must_conditions = [
            FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))
        ]
        if conversation_id:
            must_conditions.append(
                FieldCondition(key="conversation_id", match=MatchValue(value=str(conversation_id)))
            )

        filter_condition = Filter(must=must_conditions)
        count_result = await self._client.count(
            collection_name=collection,
            count_filter=filter_condition,
            exact=True
        )
        
        if count_result.count > cap:
            num_to_delete = count_result.count - cap
            # Fetch all for the conversation to sort in memory
            points, _ = await self._client.scroll(
                collection_name=collection,
                scroll_filter=filter_condition,
                limit=cap + 50,
                with_payload=True
            )
            
            # Filter out critical tier
            prunable = [p for p in points if p.payload and p.payload.get("memory_tier") != MemoryTier.CRITICAL.value]
            # Sort by importance ascending (lowest first)
            prunable.sort(key=lambda point: (point.payload or {}).get("importance_score", 1.0))
            
            if prunable and num_to_delete > 0:
                to_delete = prunable[:num_to_delete]
                ids_to_delete = [p.id for p in to_delete]
                await self.delete_points(collection, ids_to_delete)
                log.info("Pruned LTM entries mapping to bounds", user_id=user_id, conversation_id=conversation_id, pruned_count=len(ids_to_delete))

    async def upsert_memory(
        self,
        collection: str,
        point_id: str,
        vector: list[float],
        payload: MemoryPayload,
    ) -> None:
        """
        Upsert a single memory point.
        Payload MUST include 'user_id' and optional 'conversation_id' for isolation enforcement.
        """
        structured = PointStruct(
            id=point_id, 
            vector=vector, 
            payload=payload.model_dump()
        )
        await self._client.upsert(collection_name=collection, points=[structured], wait=True)
        
        # Enforce bounds per conversation immediately after insert
        await self.prune_user_memories(
            collection,
            user_id=payload.user_id,
            conversation_id=payload.conversation_id,
            cap=200
        )

    # ── Vector Search with User/Conversation Isolation ────────────
    async def search_by_user(
        self,
        collection: str,
        query_vector: list[float],
        user_id: str,
        conversation_id: Optional[str] = None,
        limit: int = 10,
        score_threshold: float = 0.65,
    ) -> list[dict[str, Any]]:
        """
        CRITICAL: All searches MUST use this method to enforce user/conversation isolation.
        Direct search() calls without user_id filter are not permitted outside of this service.
        """
        must_conditions = [
            FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))
        ]
        if conversation_id:
            must_conditions.append(
                FieldCondition(key="conversation_id", match=MatchValue(value=str(conversation_id)))
            )

        user_filter = Filter(must=must_conditions)

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

    async def search_guild_memories(
        self,
        collection: str,
        query_vector: list[float],
        guild_id: str,
        channel_id: Optional[str] = None,
        limit: int = 10,
        score_threshold: float = 0.60,
        exclude_expired: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Searches guild_memories collection scoped by guild_id.
        Optionally excludes memories where expires_at < current_timestamp.
        """
        must_conditions = [
            FieldCondition(key="guild_id", match=MatchValue(value=str(guild_id)))
        ]
        
        if exclude_expired:
            import time
            now_sec = int(time.time())
            from qdrant_client.http.models import Range
            must_not_conditions = [
                FieldCondition(key="expires_at", range=Range(lt=now_sec))
            ]
            guild_filter = Filter(must=must_conditions, must_not=must_not_conditions)
        else:
            guild_filter = Filter(must=must_conditions)

        results = await self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=guild_filter,
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

    async def delete_by_guild(self, collection: str, guild_id: str) -> None:
        from qdrant_client.http.models import FilterSelector
        guild_filter = Filter(
            must=[FieldCondition(key="guild_id", match=MatchValue(value=str(guild_id)))]
        )
        await self._client.delete(
            collection_name=collection,
            points_selector=FilterSelector(filter=guild_filter),
            wait=True,
        )

    async def delete_lore_by_page(self, collection: str, page_id: int) -> None:
        from qdrant_client.http.models import FilterSelector
        page_filter = Filter(
            must=[FieldCondition(key="page_id", match=MatchValue(value=page_id))]
        )
        await self._client.delete(
            collection_name=collection,
            points_selector=FilterSelector(filter=page_filter),
            wait=True,
        )

    # ── Lore Search (global — no user isolation) ───────────────────
    async def search_lore(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 4,
        score_threshold: float = 0.3,
        entities_filter: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """
        Searches lore collection without user_id filter.
        Lore is global shared character knowledge.
        Applies payload boosting if entities_filter is provided.
        """
        from qdrant_client.http.models import MatchAny
        query_filter = None
        if entities_filter:
            query_filter = Filter(
                should=[
                    FieldCondition(key="entities", match=MatchAny(any=entities_filter))
                ]
            )
            
        results = await self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        
        # Fallback to global vector search if entity filter eliminated results
        if not results and query_filter is not None:
            results = await self._client.search(
                collection_name=collection,
                query_vector=query_vector,
                query_filter=None,
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
        payload: Any,
    ) -> None:
        """Upsert lore chunk using LorePayload V2."""
        from qdrant_client.models import PointStruct as PS
        
        # Assume payload is already a Pydantic model (LorePayload) or a dict
        if hasattr(payload, "model_dump"):
            upsert_payload = payload.model_dump()
        else:
            upsert_payload = payload
            
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
