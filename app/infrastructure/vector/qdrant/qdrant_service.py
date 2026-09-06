from __future__ import annotations

import asyncio
import re
import time
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
    Modifier,
    OptimizersConfigDiff,
    PointStruct,
    Range,
    SparseVectorParams,
    VectorParams,
)

from app.config.settings import settings
from app.domain.entities.memory import MemoryPayload, MemoryTier
from app.domain.interfaces.corpus_publisher import CorpusPublication
from app.domain.models.corpus_manifest import LoreManifestRow, lore_manifest_checksum
from app.domain.models.corpus_release import CorpusRelease
from app.domain.models.corpus_safety_exception import CorpusSafetyProvenance
from app.domain.models.evidence import EvidenceAccess
from app.domain.services.guardrails import CorpusSafetyGate
from app.domain.tuning.rag import RAGTuning
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.vector.qdrant.sparse_encoder import SparseTextEncoder

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


@dataclass(frozen=True)
class AliasPromotionCandidate:
    """One independently verified physical corpus candidate for an alias swap."""

    target_collection: str
    expected_point_count: int
    expected_corpus_version: str | None = None
    expected_manifest_checksum: str | None = None


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

    def __init__(
        self,
        client: AsyncQdrantClient | None = None,
        corpus_safety_gate: CorpusSafetyGate | None = None,
    ) -> None:
        self._client = client or get_qdrant_client()
        self._sparse_encoder = SparseTextEncoder()
        self._corpus_safety_gate = corpus_safety_gate or CorpusSafetyGate()

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

    @staticmethod
    def _is_lore_collection(name: str) -> bool:
        logical_name = name.split("__", 1)[0]
        return logical_name in {
            COLLECTION_CHARACTER_LORE,
            COLLECTION_WORLD_LORE,
            COLLECTION_STORY_LORE,
        }

    @staticmethod
    def _supports_sparse_vectors(info: Any) -> bool:
        sparse_config = getattr(info.config.params, "sparse_vectors", None)
        return isinstance(sparse_config, dict) and "bm25" in sparse_config

    @staticmethod
    def _valid_lore_acl_filter() -> Filter:
        """Return the accepted ACL-shape union for a publishable lore collection."""
        from qdrant_client.http.models import IsEmptyCondition, PayloadField

        empty_subject = IsEmptyCondition(is_empty=PayloadField(key="access_subject_id"))
        empty_tenant = IsEmptyCondition(is_empty=PayloadField(key="access_tenant_id"))
        empty_channel = IsEmptyCondition(is_empty=PayloadField(key="access_channel_id"))
        return Filter(
            should=[
                Filter(
                    must=[
                        FieldCondition(
                            key="access_scope", match=MatchValue(value="public")
                        ),
                        empty_subject,
                        empty_tenant,
                        empty_channel,
                    ]
                ),
                Filter(
                    must=[
                        FieldCondition(key="access_scope", match=MatchValue(value="user"))
                    ],
                    must_not=[empty_subject],
                ),
                Filter(
                    must=[
                        FieldCondition(key="access_scope", match=MatchValue(value="tenant"))
                    ],
                    must_not=[empty_tenant],
                ),
            ]
        )

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

        lore_collection = self._is_lore_collection(name)
        vectors_config: VectorParams | dict[str, VectorParams]
        vectors_config = (
            {"dense": VectorParams(size=vector_size, distance=distance, on_disk=True)}
            if lore_collection
            else VectorParams(size=vector_size, distance=distance, on_disk=True)
        )
        await self._client.create_collection(
            collection_name=name,
            vectors_config=vectors_config,
            sparse_vectors_config=(
                {"bm25": SparseVectorParams(modifier=Modifier.IDF)}
                if lore_collection
                else None
            ),
            hnsw_config=HnswConfigDiff(on_disk=True),
            optimizers_config=OptimizersConfigDiff(indexing_threshold=20000),
            on_disk_payload=True,
        )
        log.info("Qdrant collection created", collection=name, size=vector_size)

        # Optimize payload indexes for Entity-Centric Retrieval
        if lore_collection:
            try:
                from qdrant_client.http.models import PayloadSchemaType
                for field in [
                    "entities",
                    "region",
                    "faction",
                    "canonical_name",
                    "access_scope",
                    "access_subject_id",
                    "access_tenant_id",
                    "access_channel_id",
                ]:
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
        expected_corpus_version: str,
        expected_manifest_checksum: str,
        expected_dimension: int | None = None,
    ) -> AliasPromotionResult:
        """Atomically point a runtime alias at a verified, versioned collection.

        The previous physical collection is retained. This operation never deletes or
        recreates an active collection, so its returned previous target is a rollback
        candidate.
        """
        results = await self.promote_active_aliases(
            {
                logical_collection: AliasPromotionCandidate(
                    target_collection=target_collection,
                    expected_point_count=expected_point_count,
                    expected_corpus_version=expected_corpus_version,
                    expected_manifest_checksum=expected_manifest_checksum,
                )
            },
            expected_dimension=expected_dimension,
        )
        return results[logical_collection]

    async def promote(self, release: CorpusRelease) -> CorpusPublication:
        """Implement the corpus publisher port with a verified atomic alias swap."""
        previous_active_collection = await self.active_alias_target(
            release.logical_collection.value
        )
        if previous_active_collection is None:
            raise CollectionAliasPromotionError(
                "cannot promote a corpus without a retained active rollback target"
            )
        promotion = await self.promote_active_alias(
            logical_collection=release.logical_collection.value,
            target_collection=release.staging_collection,
            expected_point_count=release.vector_count,
            expected_corpus_version=release.corpus_version,
            expected_manifest_checksum=release.vector_manifest_checksum,
        )
        return CorpusPublication(
            previous_active_collection=promotion.previous_collection,
            active_collection=promotion.target_collection,
        )

    async def active_target(self, logical_collection: str) -> str | None:
        """Implement the publisher port's read-only alias inspection."""
        return await self.active_alias_target(logical_collection)

    async def promote_active_aliases(
        self,
        candidates: dict[str, AliasPromotionCandidate],
        *,
        expected_dimension: int | None = None,
    ) -> dict[str, AliasPromotionResult]:
        """Atomically swap one or more aliases after validating every candidate.

        The method performs all validation before the single Qdrant alias update.
        If a candidate is malformed, count-mismatched, or ACL-incomplete, no
        runtime alias changes.  Previous physical collections are retained for
        one-operation rollback through this same method.
        """
        if not candidates:
            raise ValueError("at least one alias promotion candidate is required")

        expected_dim = expected_dimension or settings.QDRANT_EMBEDDING_DIM
        validated_counts: dict[str, int] = {}
        for logical_collection, candidate in candidates.items():
            validated_counts[logical_collection] = await self._validate_promotion_candidate(
                logical_collection=logical_collection,
                target_collection=candidate.target_collection,
                expected_point_count=candidate.expected_point_count,
                expected_dimension=expected_dim,
                expected_corpus_version=candidate.expected_corpus_version,
                expected_manifest_checksum=candidate.expected_manifest_checksum,
            )

        aliases = await self._client.get_aliases()
        active_targets = {
            alias.alias_name: alias.collection_name for alias in aliases.aliases
        }
        operations: list[CreateAliasOperation | DeleteAliasOperation] = []
        results: dict[str, AliasPromotionResult] = {}
        for logical_collection, candidate in candidates.items():
            alias_name = active_collection_alias(logical_collection)
            previous_collection = active_targets.get(alias_name)
            actual_count = validated_counts[logical_collection]
            results[logical_collection] = AliasPromotionResult(
                logical_collection=logical_collection,
                alias_name=alias_name,
                target_collection=candidate.target_collection,
                previous_collection=previous_collection,
                expected_point_count=candidate.expected_point_count,
                actual_point_count=actual_count,
            )
            if previous_collection == candidate.target_collection:
                continue
            if previous_collection is not None:
                operations.append(
                    DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias_name))
                )
            operations.append(
                CreateAliasOperation(
                    create_alias=CreateAlias(
                        collection_name=candidate.target_collection,
                        alias_name=alias_name,
                    )
                )
            )

        if operations:
            await self._client.update_collection_aliases(
                change_aliases_operations=operations
            )
        for result in results.values():
            log.info(
                "Qdrant active alias promoted",
                logical_collection=result.logical_collection,
                alias_name=result.alias_name,
                target_collection=result.target_collection,
                previous_collection=result.previous_collection,
                point_count=result.actual_point_count,
            )
        return results

    async def _validate_promotion_candidate(
        self,
        *,
        logical_collection: str,
        target_collection: str,
        expected_point_count: int,
        expected_dimension: int,
        expected_corpus_version: str | None,
        expected_manifest_checksum: str | None,
    ) -> int:
        if expected_point_count < 0:
            raise ValueError("expected_point_count must be non-negative")
        self._require_versioned_target(logical_collection, target_collection)
        try:
            target_info = await self._client.get_collection(target_collection)
        except Exception as exc:
            raise CollectionAliasPromotionError(
                f"Candidate collection {target_collection!r} is unavailable"
            ) from exc

        actual_dimension = self._dimension_from_collection_info(target_info)
        if actual_dimension != expected_dimension:
            raise CollectionDimensionMismatchError(
                f"Candidate collection {target_collection!r} has dimension {actual_dimension}; "
                f"expected {expected_dimension}"
            )
        if not self._supports_sparse_vectors(target_info):
            raise CollectionAliasPromotionError(
                f"Candidate collection {target_collection!r} has no required sparse BM25 index"
            )
        count_result = await self._client.count(collection_name=target_collection, exact=True)
        actual_point_count = count_result.count
        if actual_point_count != expected_point_count:
            raise CollectionAliasPromotionError(
                f"Candidate collection {target_collection!r} has {actual_point_count} points; "
                f"expected {expected_point_count}"
            )
        valid_acl_count = await self._client.count(
            collection_name=target_collection,
            count_filter=self._valid_lore_acl_filter(),
            exact=True,
        )
        if valid_acl_count.count != expected_point_count:
            raise CollectionAliasPromotionError(
                f"Candidate collection {target_collection!r} has incomplete ACL labels"
            )
        self._validate_manifest_request(
            candidate_version=target_collection.removeprefix(f"{logical_collection}__"),
            expected_corpus_version=expected_corpus_version,
            expected_manifest_checksum=expected_manifest_checksum,
        )
        if expected_manifest_checksum is not None:
            if expected_corpus_version is None:
                raise CollectionAliasPromotionError(
                    "candidate manifest verification requires a corpus version"
                )
            actual_manifest_checksum = await self.staged_lore_manifest_checksum(
                collection=target_collection,
                corpus_version=expected_corpus_version,
                expected_point_count=expected_point_count,
            )
            if actual_manifest_checksum != expected_manifest_checksum.lower():
                raise CollectionAliasPromotionError(
                    f"Candidate collection {target_collection!r} has a manifest checksum mismatch"
                )
        return actual_point_count

    @staticmethod
    def _validate_manifest_request(
        *,
        candidate_version: str,
        expected_corpus_version: str | None,
        expected_manifest_checksum: str | None,
    ) -> None:
        """Require a complete, version-bound checksum request for every promotion."""
        if expected_corpus_version != candidate_version:
            raise CollectionAliasPromotionError(
                "candidate corpus version does not match its physical collection name"
            )
        if expected_manifest_checksum is None or re.fullmatch(
            r"[0-9a-f]{64}", expected_manifest_checksum.lower()
        ) is None:
            raise CollectionAliasPromotionError(
                "candidate manifest checksum must be a SHA-256 hexadecimal digest"
            )

    async def staged_lore_manifest_checksum(
        self,
        *,
        collection: str,
        corpus_version: str,
        expected_point_count: int,
    ) -> str:
        """Hash the actual staged Qdrant records before an alias can be promoted.

        The digest covers immutable point identity, text hash, parent, source,
        corpus version, and ACL. It is calculated from Qdrant rather than a
        caller-provided count so a partially written or wrongly labelled index
        cannot be promoted merely by supplying a matching metadata document.
        """
        rows: list[LoreManifestRow] = []
        offset: Any = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=collection,
                scroll_filter=None,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                payload = record.payload
                if not isinstance(payload, dict):
                    raise CollectionAliasPromotionError(
                        f"Candidate collection {collection!r} has a record without payload"
                    )
                rows.append(
                    self._manifest_row(
                        point_id=str(record.id),
                        payload=payload,
                        corpus_version=corpus_version,
                    )
                )
            if offset is None:
                break

        if len(rows) != expected_point_count:
            raise CollectionAliasPromotionError(
                f"Candidate collection {collection!r} has {len(rows)} manifest records; "
                f"expected {expected_point_count}"
            )
        return lore_manifest_checksum(rows)

    @staticmethod
    def _manifest_row(
        *, point_id: str, payload: dict[str, Any], corpus_version: str
    ) -> LoreManifestRow:
        """Validate one payload and return its canonical checksum row."""
        chunk_hash = payload.get("chunk_hash")
        parent_id = payload.get("parent_id")
        source_id = payload.get("source_id")
        payload_version = payload.get("corpus_version")
        if (
            not isinstance(chunk_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", chunk_hash.lower()) is None
            or not isinstance(parent_id, str)
            or not parent_id
            or not isinstance(source_id, str)
            or not source_id
            or payload_version != corpus_version
        ):
            raise CollectionAliasPromotionError(
                "candidate payload is missing a versioned source, parent, or chunk checksum"
            )
        try:
            access = EvidenceAccess(
                scope=payload.get("access_scope"),
                subject_id=payload.get("access_subject_id"),
                tenant_id=payload.get("access_tenant_id"),
                channel_id=payload.get("access_channel_id"),
            )
        except ValueError as exc:
            raise CollectionAliasPromotionError("candidate payload has invalid ACL labels") from exc
        return LoreManifestRow(
            point_id=point_id,
            chunk_hash=chunk_hash,
            parent_id=parent_id,
            source_id=source_id,
            corpus_version=corpus_version,
            access=access,
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
        Optionally excludes memories where expires_at is at or before the current timestamp.
        """
        must_conditions = [
            FieldCondition(key="guild_id", match=MatchValue(value=str(guild_id)))
        ]
        
        if exclude_expired:
            now_sec = int(time.time())
            must_not_conditions = [
                FieldCondition(key="expires_at", range=Range(lte=now_sec))
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
        query_text: str = "",
        limit: int = 4,
        score_threshold: float = 0.3,
        entities_filter: Optional[list[str]] = None,
        requester_subject_id: str | None = None,
        requester_tenant_id: str | None = None,
        requester_channel_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search only evidence whose persisted ACL admits the trusted requester.

        Records without an ACL label are intentionally excluded.  This makes a
        partially migrated or malformed corpus unavailable rather than exposing
        it as public lore.
        """
        from qdrant_client.http.models import IsEmptyCondition, MatchAny, PayloadField

        public_access = Filter(
            must=[FieldCondition(key="access_scope", match=MatchValue(value="public"))]
        )
        access_conditions: list[Filter] = [public_access]
        if requester_subject_id:
            access_conditions.append(
                Filter(
                    must=[
                        FieldCondition(key="access_scope", match=MatchValue(value="user")),
                        FieldCondition(
                            key="access_subject_id",
                            match=MatchValue(value=requester_subject_id),
                        ),
                    ]
                )
            )
        if requester_tenant_id:
            tenant_base = [
                FieldCondition(key="access_scope", match=MatchValue(value="tenant")),
                FieldCondition(
                    key="access_tenant_id",
                    match=MatchValue(value=requester_tenant_id),
                ),
            ]
            access_conditions.append(
                Filter(
                    must=[
                        *tenant_base,
                        IsEmptyCondition(is_empty=PayloadField(key="access_channel_id")),
                    ]
                )
            )
            if requester_channel_id:
                access_conditions.append(
                    Filter(
                        must=[
                            *tenant_base,
                            FieldCondition(
                                key="access_channel_id",
                                match=MatchValue(value=requester_channel_id),
                            ),
                        ]
                    )
                )

        access_filter = Filter(should=access_conditions)
        query_filter = access_filter
        if entities_filter:
            query_filter = Filter(
                must=[access_filter],
                should=[
                    FieldCondition(key="entities", match=MatchAny(any=entities_filter))
                ]
            )
            
        active_collection = self._active_collection_name(collection)
        try:
            info = await self._client.get_collection(active_collection)
            hybrid_enabled = bool(query_text.strip()) and self._supports_sparse_vectors(info)
        except Exception:
            hybrid_enabled = False

        results = await self._search_lore_candidates(
            collection_name=active_collection,
            query_vector=query_vector,
            query_text=query_text,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            hybrid_enabled=hybrid_enabled,
        )

        if not results and entities_filter:
            results = await self._search_lore_candidates(
                collection_name=active_collection,
                query_vector=query_vector,
                query_text=query_text,
                query_filter=access_filter,
                limit=limit,
                score_threshold=score_threshold,
                hybrid_enabled=hybrid_enabled,
            )
        return results

    async def _search_lore_candidates(
        self,
        *,
        collection_name: str,
        query_vector: list[float],
        query_text: str,
        query_filter: Filter | None,
        limit: int,
        score_threshold: float,
        hybrid_enabled: bool,
    ) -> list[dict[str, Any]]:
        if not hybrid_enabled:
            results = await self._client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
            return [
                {
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload or {},
                    "retrieval_mode": "dense_legacy",
                }
                for result in results
            ]

        dense_task = asyncio.create_task(
            asyncio.wait_for(
                self._client.query_points(
                collection_name=collection_name,
                query=query_vector,
                using="dense",
                query_filter=query_filter,
                limit=limit * RAGTuning.HYBRID_CANDIDATE_MULTIPLIER,
                with_payload=True,
                score_threshold=score_threshold,
                ),
                timeout=RAGTuning.HYBRID_RETRIEVAL_TIMEOUT_SECONDS,
            )
        )
        sparse_task = asyncio.create_task(
            asyncio.wait_for(
                self._client.query_points(
                collection_name=collection_name,
                query=self._sparse_encoder.encode(query_text),
                using="bm25",
                query_filter=query_filter,
                limit=limit * RAGTuning.HYBRID_CANDIDATE_MULTIPLIER,
                with_payload=True,
                ),
                timeout=RAGTuning.HYBRID_RETRIEVAL_TIMEOUT_SECONDS,
            )
        )
        dense_result, sparse_result = await asyncio.gather(
            dense_task, sparse_task, return_exceptions=True
        )
        dense_points = (
            getattr(dense_result, "points", [])
            if not isinstance(dense_result, Exception)
            else []
        )
        sparse_points = (
            getattr(sparse_result, "points", [])
            if not isinstance(sparse_result, Exception)
            else []
        )
        if not dense_points and not sparse_points:
            if isinstance(dense_result, Exception) and isinstance(sparse_result, Exception):
                raise RuntimeError("dense and sparse lore retrieval both failed") from dense_result
            return []
        mode = "hybrid_rrf"
        if isinstance(dense_result, Exception):
            mode = "sparse_degraded"
        elif isinstance(sparse_result, Exception):
            mode = "dense_degraded"
        return self._calibrated_rrf(dense_points, sparse_points, limit=limit, mode=mode)

    @staticmethod
    def _calibrated_rrf(
        dense_points: list[Any], sparse_points: list[Any], *, limit: int, mode: str
    ) -> list[dict[str, Any]]:
        """Fuse independently ranked dense and BM25 lists with calibrated reciprocal rank."""

        combined: dict[str, dict[str, Any]] = {}
        for source, weight, points in (
            ("dense", RAGTuning.HYBRID_DENSE_WEIGHT, dense_points),
            ("sparse", RAGTuning.HYBRID_SPARSE_WEIGHT, sparse_points),
        ):
            for rank, point in enumerate(points, start=1):
                point_id = str(point.id)
                candidate = combined.setdefault(
                    point_id,
                    {
                        "id": point.id,
                        "payload": point.payload or {},
                        "score": 0.0,
                        "dense_score": None,
                        "sparse_score": None,
                        "dense_rank": None,
                        "sparse_rank": None,
                    },
                )
                candidate["score"] += weight / (RAGTuning.HYBRID_RRF_K + rank)
                candidate[f"{source}_score"] = float(point.score)
                candidate[f"{source}_rank"] = rank
        ranked = sorted(combined.values(), key=lambda candidate: candidate["score"], reverse=True)
        for candidate in ranked:
            candidate["retrieval_mode"] = mode
        return ranked[:limit]

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
        if not isinstance(upsert_payload, dict):
            raise TypeError("Lore payload must be a mapping")
        corpus_version = upsert_payload.get("corpus_version")
        source_id = upsert_payload.get("source_id")
        revision_id = upsert_payload.get("revision_id")
        provenance = (
            CorpusSafetyProvenance(
                source_id=str(source_id),
                corpus_version=str(corpus_version),
                page_id=int(upsert_payload["page_id"]),
                revision_id=int(revision_id),
                chunk_id=point_id,
            )
            if source_id is not None
            and corpus_version is not None
            and revision_id is not None
            else None
        )
        self._corpus_safety_gate.require_safe(
            text=str(upsert_payload.get("text_content", "")),
            source_id=f"qdrant:{collection}:point:{point_id}",
            checksum=str(upsert_payload.get("chunk_hash", "unknown")),
            provenance=provenance,
        )

        target_collection = self._active_collection_name(collection)
        try:
            collection_info = await self._client.get_collection(target_collection)
            sparse_enabled = self._supports_sparse_vectors(collection_info)
        except Exception:
            sparse_enabled = False
        point_vector: list[float] | dict[str, Any] = vector
        if sparse_enabled:
            point_vector = {
                "dense": vector,
                "bm25": self._sparse_encoder.encode(str(upsert_payload.get("text_content", ""))),
            }
        await self._client.upsert(
            collection_name=target_collection,
            points=[PS(id=point_id, vector=point_vector, payload=upsert_payload)],
            wait=True,
        )

    # ── Disconnect ─────────────────────────────────────────────────
    async def disconnect(self) -> None:
        await self._client.close()
        log.info("Qdrant client disconnected")


# ── Module-level singleton ───────────────────────────────────────────
qdrant_service = QdrantService()
