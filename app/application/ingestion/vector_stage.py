"""Embed a gold corpus through the vector cache and load it into staging (KNW-003, KNW-005, D11)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.knowledge import knowledge_counts
from app.domain.ingestion.units import Collection
from app.domain.interfaces.gold import IGoldStore, IKnowledgeStore
from app.domain.interfaces.vectors import (
    IPassageEmbedder,
    IStagingIndex,
    IVectorCache,
    StagingError,
    StagingPoint,
)

SOURCE_KIND = "wiki"
ACCESS_SCOPE = "public"


@dataclass(frozen=True)
class VectorSettings:
    embed_batch: int = 4
    # Saved this often so a crash only repeats the last few passages.
    flush_every: int = 256
    upsert_batch: int = 256


@dataclass(frozen=True)
class EmbedReport:
    corpus_version: str
    chunks: int
    cached: int
    embedded: int


@dataclass(frozen=True)
class StagingReport:
    corpus_version: str
    collections: dict[str, int]
    knowledge: dict[str, int]


def vector_key(model_id: str, chunk: Chunk) -> str:
    """Unchanged text under the same model is never embedded twice, across any release."""
    source = f"{model_id}\0{chunk.embedding_text}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def staging_collection(collection: Collection, version: str) -> str:
    # Qdrant names stay portable with only letters, digits and underscores.
    safe = version.replace(".", "_").replace("-", "_")
    return f"{collection.value}__{safe}"


def point_payload(chunk: Chunk, version: str) -> dict[str, Any]:
    return {
        "evidence_id": chunk.evidence_id,
        "corpus_version": version,
        "source_kind": SOURCE_KIND,
        "access_scope": ACCESS_SCOPE,
        "page_id": chunk.page_id,
        "title": chunk.title,
        "page_type": chunk.family,
        "entity_type": chunk.family,
        "kind": chunk.kind,
        "section_path": list(chunk.section),
        "entities": list(chunk.entities),
        "nation": chunk.nation,
        "game_version": chunk.game_version,
        "text": chunk.text,
        "tokens": chunk.tokens,
    }


def _batches(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class VectorStage:
    def __init__(
        self,
        gold: IGoldStore,
        embedder: IPassageEmbedder,
        cache: IVectorCache,
        index: IStagingIndex,
        knowledge_store: IKnowledgeStore,
        settings: VectorSettings,
    ) -> None:
        self._gold = gold
        self._embedder = embedder
        self._cache = cache
        self._index = index
        self._knowledge_store = knowledge_store
        self._settings = settings

    async def embed(self, version: str) -> EmbedReport:
        chunks = self._gold.read_chunks(version)
        keys = {chunk.evidence_id: vector_key(self._embedder.model_id, chunk) for chunk in chunks}
        cached = self._cache.load(keys.values())
        missing = {
            keys[c.evidence_id]: c.embedding_text
            for c in chunks
            if keys[c.evidence_id] not in cached
        }
        await self._embed_missing(missing)
        return EmbedReport(version, len(chunks), len(chunks) - len(missing), len(missing))

    async def _embed_missing(self, missing: dict[str, str]) -> None:
        pending: dict[str, Sequence[float]] = {}
        for batch in _batches(list(missing.items()), self._settings.embed_batch):
            vectors = await self._embedder.embed_passages([text for _, text in batch])
            pending.update((key, vector) for (key, _), vector in zip(batch, vectors, strict=True))
            if len(pending) >= self._settings.flush_every:
                self._cache.save(pending)
                pending = {}
        if pending:
            self._cache.save(pending)

    async def load(self, version: str, *, replace: bool = False) -> StagingReport:
        """Needs no embedding: every vector must already be in the cache."""
        chunks = self._gold.read_chunks(version)
        keys = {chunk.evidence_id: vector_key(self._embedder.model_id, chunk) for chunk in chunks}
        vectors = self._cache.load(keys.values())
        counts: dict[str, int] = {}
        for collection in Collection:
            members = [chunk for chunk in chunks if chunk.collection is collection]
            name = staging_collection(collection, version)
            await self._index.create(name, self._embedder.dimension, replace=replace)
            for batch in _batches(members, self._settings.upsert_batch):
                points = [self._point(c, vectors[keys[c.evidence_id]], version) for c in batch]
                await self._index.upsert(name, points)
            await self._index.verify(name, len(members))
            counts[name] = len(members)
        return StagingReport(version, counts, await self._load_knowledge(version))

    async def _load_knowledge(self, version: str) -> dict[str, int]:
        """Counts are read back, so a partial write cannot pass as a staged release (S7)."""
        knowledge = self._gold.read_knowledge(version)
        await self._knowledge_store.publish(version, knowledge)
        stored = await self._knowledge_store.count(version)
        if stored != knowledge_counts(knowledge):
            raise StagingError(f"knowledge rows {stored} do not match the corpus")
        return stored

    @staticmethod
    def _point(chunk: Chunk, vector: Sequence[float], version: str) -> StagingPoint:
        return StagingPoint(chunk.point_id, vector, chunk.text, point_payload(chunk, version))
