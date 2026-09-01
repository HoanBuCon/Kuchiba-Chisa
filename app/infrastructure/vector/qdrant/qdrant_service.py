from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    Distance,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    MatchValue,
    OptimizersConfigDiff,
    PointStruct,
    VectorParams,
)

from app.config.settings import settings
from app.domain.entities.memory import MemoryPayload, MemoryTier
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

ACTIVE_COLLECTION_ALIASES = {
    collection: f"{collection}__active" for collection in ALL_COLLECTIONS
}
_VERSION_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class QdrantCollectionLifecycleError(RuntimeError):
    """Base error for a safe, explicit Qdrant collection lifecycle operation."""


class CollectionDimensionMismatchError(QdrantCollectionLifecycleError):
    """Raised instead of replacing a collection with an incompatible vector size."""


class CollectionAliasPromotionError(QdrantCollectionLifecycleError):
    """Raised when a candidate collection cannot safely become active."""


@dataclass(frozen=True)
class CollectionReadiness:
    logical_collection: str
    active_name: str
    expected_dimension: int
    actual_dimension: int | None
    ready: bool
    reason: str | None = None


@dataclass(frozen=True)
class AliasPromotionResult:
    logical_collection: str
    alias_name: str
    target_collection: str
    previous_collection: str | None
    expected_point_count: int
    actual_point_count: int


def active_collection_alias(collection: str) -> str:
    """Return the only runtime-readable alias for a managed logical collection."""
    try:
        return ACTIVE_COLLECTION_ALIASES[collection]
    except KeyError as exc:
        raise ValueError(f"Unknown managed Qdrant collection: {collection}") from exc


def versioned_collection_name(collection: str, version: str) -> str:
    """Build a constrained physical collection name from a logical collection and version."""
    if collection not in ACTIVE_COLLECTION_ALIASES:
        raise ValueError(f"Unknown managed Qdrant collection: {collection}")
    if not _VERSION_COMPONENT.fullmatch(version):
        raise ValueError("Qdrant collection version must match [a-z0-9][a-z0-9_-]{0,63}")
    return f"{collection}__{version}"


# ─── Qdrant Service ───────────────────────────────────────────────────────────
from app.domain.interfaces.vector_store import IVectorStore


class QdrantService(IVectorStore):
    """
    Async Qdrant service for all vector operations.
    CRITICAL: All searches enforce user_id filtering for strict user isolation.
    """

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        self._client = client or get_qdrant_client()

    @staticmethod
    def _dimension_from_collection_info(info: Any) -> int | None:
        vectors_config = info.config.params.vectors
        if isinstance(vectors_config, VectorParams):
            return vectors_config.size
        if isinstance(vectors_config, dict) and vectors_config:
            first_vector = next(iter(vectors_config.values()))
            return getattr(first_vector, "size", None)
        return None

    @staticmethod
    def _require_versioned_target(logical_collection: str, target_collection: str) -> None:
        expected_prefix = f"{logical_collection}__"
        if not target_collection.startswith(expected_prefix):
            raise CollectionAliasPromotionError(
                f"Target {target_collection!r} is not a version of {logical_collection!r}"
            )
        version = target_collection.removeprefix(expected_prefix)
        versioned_collection_name(logical_collection, version)

    @staticmethod
    def _active_collection_name(collection: str) -> str:
        return ACTIVE_COLLECTION_ALIASES.get(collection, collection)

    # ── Health ─────────────────────────────────────────────────────
    async def health_check(self, *, require_active_collections: bool = False) -> bool:
        try:
            await self._client.get_collections()
            if not require_active_collections:
                return True
            readiness = await self.validate_active_collections()
            return all(result.ready for result in readiness.values())
        except Exception as e:
            log.error("Qdrant health check failed", error=str(e))
            return False

    # ── Collection Management ──────────────────────────────────────
    async def collection_exists(self, name: str) -> bool:
        try:
            await self._client.get_collection(self._active_collection_name(name))
            return True
        except Exception:
            return False

    async def validate_active_collections(
        self, expected_dimension: int | None = None
    ) -> dict[str, CollectionReadiness]:
        """Validate runtime aliases without creating, deleting, or modifying collections."""
        expected = expected_dimension or settings.QDRANT_EMBEDDING_DIM
        readiness: dict[str, CollectionReadiness] = {}
        for logical_collection in ALL_COLLECTIONS:
            active_name = active_collection_alias(logical_collection)
            try:
                info = await self._client.get_collection(active_name)
            except Exception as exc:
                readiness[logical_collection] = CollectionReadiness(
                    logical_collection=logical_collection,
                    active_name=active_name,
                    expected_dimension=expected,
                    actual_dimension=None,
                    ready=False,
                    reason=f"active alias unavailable: {type(exc).__name__}",
                )
                continue

            actual = self._dimension_from_collection_info(info)
            if actual != expected:
                readiness[logical_collection] = CollectionReadiness(
                    logical_collection=logical_collection,
                    active_name=active_name,
                    expected_dimension=expected,
                    actual_dimension=actual,
                    ready=False,
                    reason="vector dimension mismatch",
                )
                continue

            readiness[logical_collection] = CollectionReadiness(
                logical_collection=logical_collection,
                active_name=active_name,
                expected_dimension=expected,
                actual_dimension=actual,
                ready=True,
            )
        return readiness

    async def create_collection(
        self,
        name: str,
        vector_size: int,
        distance: Distance = Distance.COSINE,
    ) -> None:
        try:
            info = await self._client.get_collection(name)
        except UnexpectedResponse as exc:
            if exc.status_code != 404:
                raise QdrantCollectionLifecycleError(
                    f"Unable to inspect collection {name!r} before creation"
                ) from exc
        else:
            existing_dim = self._dimension_from_collection_info(info)
            if existing_dim != vector_size:
                raise CollectionDimensionMismatchError(
                    f"Collection {name!r} has dimension {existing_dim}; expected {vector_size}. "
                    "Create a versioned collection and promote its alias explicitly."
                )
            log.info("Collection already exists with correct dimensions, skipping", collection=name)
            return

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

    async def prepare_versioned_collection(
        self,
        logical_collection: str,
        version: str,
        vector_size: int,
    ) -> str:
        """Create a new physical collection; it is not active until alias promotion succeeds."""
        target_collection = versioned_collection_name(logical_collection, version)
        await self.create_collection(target_collection, vector_size=vector_size)
        return target_collection

    async def active_alias_target(self, logical_collection: str) -> str | None:
        """Return the current physical collection behind a runtime alias, if present."""
        alias_name = active_collection_alias(logical_collection)
        aliases = await self._client.get_aliases()
        for alias in aliases.aliases:
            if alias.alias_name == alias_name:
                return alias.collection_name
        return None

    async def promote_active_alias(
        self,
        logical_collection: str,
        target_collection: str,
        expected_point_count: int,
        expected_dimension: int | None = None,
    ) -> AliasPromotionResult:
        """Atomically point a runtime alias at a verified, versioned collection.

        The previous physical collection is retained. This operation never deletes or
        recreates an active collection, so its returned previous target is a rollback
        candidate.
        """
        if expected_point_count < 0:
            raise ValueError("expected_point_count must be non-negative")
        self._require_versioned_target(logical_collection, target_collection)
        expected_dim = expected_dimension or settings.QDRANT_EMBEDDING_DIM

        try:
            target_info = await self._client.get_collection(target_collection)
        except Exception as exc:
            raise CollectionAliasPromotionError(
                f"Candidate collection {target_collection!r} is unavailable"
            ) from exc

        actual_dimension = self._dimension_from_collection_info(target_info)
        if actual_dimension != expected_dim:
            raise CollectionDimensionMismatchError(
                f"Candidate collection {target_collection!r} has dimension {actual_dimension}; "
                f"expected {expected_dim}"
            )

        count_result = await self._client.count(
            collection_name=target_collection,
            exact=True,
        )
        actual_point_count = count_result.count
        if actual_point_count != expected_point_count:
            raise CollectionAliasPromotionError(
                f"Candidate collection {target_collection!r} has {actual_point_count} points; "
                f"expected {expected_point_count}"
            )

        alias_name = active_collection_alias(logical_collection)
        previous_collection = await self.active_alias_target(logical_collection)
        if previous_collection == target_collection:
            return AliasPromotionResult(
                logical_collection=logical_collection,
                alias_name=alias_name,
                target_collection=target_collection,
                previous_collection=previous_collection,
                expected_point_count=expected_point_count,
                actual_point_count=actual_point_count,
            )

        operations: list[CreateAliasOperation | DeleteAliasOperation] = []
        if previous_collection is not None:
            operations.append(
                DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias_name))
            )
        operations.append(
            CreateAliasOperation(
                create_alias=CreateAlias(
                    collection_name=target_collection,
                    alias_name=alias_name,
                )
            )
        )
        await self._client.update_collection_aliases(change_aliases_operations=operations)
        log.info(
            "Qdrant active alias promoted",
            logical_collection=logical_collection,
            alias_name=alias_name,
            target_collection=target_collection,
            previous_collection=previous_collection,
            point_count=actual_point_count,
        )
        return AliasPromotionResult(
            logical_collection=logical_collection,
            alias_name=alias_name,
            target_collection=target_collection,
            previous_collection=previous_collection,
            expected_point_count=expected_point_count,
            actual_point_count=actual_point_count,
        )

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
                            collection_name=self._active_collection_name(col),
                            field_name=f,
                            field_schema=PayloadSchemaType.KEYWORD,
                            wait=False
                        )
                    except Exception as exc:
                        log.debug(
                            "Qdrant payload index already exists or could not be created",
                            collection=self._active_collection_name(col),
                            field=f,
                            error=str(exc),
                        )

        # Ensure memories collection has indexes on user_id and conversation_id for fast isolation
        if await self.collection_exists(COLLECTION_MEMORIES):
            for f in ["user_id", "conversation_id", "memory_type"]:
                try:
                    await self._client.create_payload_index(
                        collection_name=self._active_collection_name(COLLECTION_MEMORIES),
                        field_name=f,
                        field_schema=PayloadSchemaType.KEYWORD,
                        wait=False
                    )
                except Exception as exc:
                    log.debug(
                        "Qdrant payload index already exists or could not be created",
                        collection=self._active_collection_name(COLLECTION_MEMORIES),
                        field=f,
                        error=str(exc),
                    )

        # Ensure guild_memories collection has indexes on guild_id, memory_type, and expires_at
        if await self.collection_exists(COLLECTION_GUILD_MEMORIES):
            for f in ["guild_id", "channel_id", "memory_type"]:
                try:
                    await self._client.create_payload_index(
                        collection_name=self._active_collection_name(COLLECTION_GUILD_MEMORIES),
                        field_name=f,
                        field_schema=PayloadSchemaType.KEYWORD,
                        wait=False
                    )
                except Exception as exc:
                    log.debug(
                        "Qdrant payload index already exists or could not be created",
                        collection=self._active_collection_name(COLLECTION_GUILD_MEMORIES),
                        field=f,
                        error=str(exc),
                    )
            try:
                from qdrant_client.http.models import PayloadSchemaType as PST
                await self._client.create_payload_index(
                    collection_name=self._active_collection_name(COLLECTION_GUILD_MEMORIES),
                    field_name="expires_at",
                    field_schema=PST.INTEGER,
                    wait=False
                )
            except Exception as exc:
                log.debug(
                    "Qdrant payload index already exists or could not be created",
                    collection=self._active_collection_name(COLLECTION_GUILD_MEMORIES),
                    field="expires_at",
                    error=str(exc),
                )

        # Ensure image_memories collection has indexes on user_id, guild_id, image_id, tags, created_at
        if await self.collection_exists(COLLECTION_IMAGE_MEMORIES):
            for f in ["user_id", "guild_id", "image_id", "tags"]:
                try:
                    await self._client.create_payload_index(
                        collection_name=self._active_collection_name(COLLECTION_IMAGE_MEMORIES),
                        field_name=f,
                        field_schema=PayloadSchemaType.KEYWORD,
                        wait=False
                    )
                except Exception as exc:
                    log.debug(
                        "Qdrant payload index already exists or could not be created",
                        collection=self._active_collection_name(COLLECTION_IMAGE_MEMORIES),
                        field=f,
                        error=str(exc),
                    )
            try:
                from qdrant_client.http.models import PayloadSchemaType as PST
                await self._client.create_payload_index(
                    collection_name=self._active_collection_name(COLLECTION_IMAGE_MEMORIES),
                    field_name="created_at",
                    field_schema=PST.INTEGER,
                    wait=False
                )
            except Exception as exc:
                log.debug(
                    "Qdrant payload index already exists or could not be created",
                    collection=self._active_collection_name(COLLECTION_IMAGE_MEMORIES),
                    field="created_at",
                    error=str(exc),
                )
        log.info("Qdrant payload indexes ensured across all collections ✓")

    async def initialize_all_collections(self) -> None:
        """
        Legacy explicit provisioning helper.

        It is intentionally not called by application startup. Production collection
        changes must use prepare_versioned_collection() and promote_active_alias().
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
        active_collection = self._active_collection_name(collection)
        count_result = await self._client.count(
            collection_name=active_collection,
            count_filter=filter_condition,
            exact=True
        )
        
        if count_result.count > cap:
            num_to_delete = count_result.count - cap
            # Fetch all for the conversation to sort in memory
            points, _ = await self._client.scroll(
                collection_name=active_collection,
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
        await self._client.upsert(
            collection_name=self._active_collection_name(collection),
            points=[structured],
            wait=True,
        )
        
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
            collection_name=self._active_collection_name(collection),
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
            collection_name=self._active_collection_name(collection),
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
            collection_name=self._active_collection_name(collection),
            points_selector=PointIdsList(points=ids),
            wait=True,
        )

    async def delete_by_user(self, collection: str, user_id: str) -> None:
        from qdrant_client.http.models import FilterSelector
        user_filter = Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        )
        await self._client.delete(
            collection_name=self._active_collection_name(collection),
            points_selector=FilterSelector(filter=user_filter),
            wait=True,
        )

    async def delete_by_guild(self, collection: str, guild_id: str) -> None:
        from qdrant_client.http.models import FilterSelector
        guild_filter = Filter(
            must=[FieldCondition(key="guild_id", match=MatchValue(value=str(guild_id)))]
        )
        await self._client.delete(
            collection_name=self._active_collection_name(collection),
            points_selector=FilterSelector(filter=guild_filter),
            wait=True,
        )

    async def delete_lore_by_page(self, collection: str, page_id: int) -> None:
        from qdrant_client.http.models import FilterSelector
        page_filter = Filter(
            must=[FieldCondition(key="page_id", match=MatchValue(value=page_id))]
        )
        await self._client.delete(
            collection_name=self._active_collection_name(collection),
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
            collection_name=self._active_collection_name(collection),
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        
        # Fallback to global vector search if entity filter eliminated results
        if not results and query_filter is not None:
            results = await self._client.search(
                collection_name=self._active_collection_name(collection),
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
            collection_name=self._active_collection_name(collection),
            points=[PS(id=point_id, vector=vector, payload=upsert_payload)],
            wait=True,
        )

    # ── Disconnect ─────────────────────────────────────────────────
    async def disconnect(self) -> None:
        await self._client.close()
        log.info("Qdrant client disconnected")


# ── Module-level singleton ───────────────────────────────────────────
qdrant_service = QdrantService()
