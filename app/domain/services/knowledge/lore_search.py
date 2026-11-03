"""`search_lore`: a fixed path from question to reranked canon evidence (ADV-004, ADV-010)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.domain.ingestion.entity_linking import EntityLinker
from app.domain.ingestion.text_normalization import normalize_text
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.reranker import ICrossEncoderReranker, RerankerUnavailableError
from app.domain.models.evidence import (
    Evidence,
    EvidenceAccess,
    EvidenceProvenance,
    EvidenceScore,
)

QUERY_PREFIX = "query: "


class QueryTranslationError(RuntimeError):
    """The translator could not answer; retrieval continues with the original question."""


class IQueryTranslator(Protocol):
    async def to_english(self, question: str) -> str: ...


@dataclass(frozen=True)
class LoreHit:
    evidence_id: str
    page_id: int
    title: str
    text: str
    section_path: tuple[str, ...]
    corpus_version: str
    source_kind: str
    score: float
    offset: int = 0
    url: str = ""
    license: str = ""
    revid: int = 0


class ILoreIndex(Protocol):
    async def search(
        self,
        text: str,
        vector: Sequence[float],
        *,
        own_titles: Sequence[str],
        mentioned: Sequence[str],
        limit: int,
    ) -> list[LoreHit]: ...


@dataclass(frozen=True)
class LoreSearchSettings:
    candidates: int = 50
    rerank_candidates: int = 15
    top_k: int = 8


@dataclass(frozen=True)
class LoreSearchResult:
    evidence: tuple[Evidence, ...]
    query: str
    entities: tuple[str, ...]
    # Machine-readable reasons a step fell back, for metrics and ADV-009 degraded replies.
    degraded: tuple[str, ...] = field(default=())


def rerank_document(hit: LoreHit) -> str:
    return f"{hit.title}\n{' > '.join(hit.section_path)}\n{hit.text}"


def to_evidence(hit: LoreHit, score: float) -> Evidence:
    return Evidence(
        evidence_id=hit.evidence_id,
        kind="lore",
        text=hit.text,
        provenance=EvidenceProvenance(
            source_id=hit.url or str(hit.page_id),
            source_type=hit.source_kind,
            collection=f"lore_{hit.source_kind}",
            source_version=hit.corpus_version,
            page_id=hit.page_id,
            section_id=" > ".join(hit.section_path) or None,
            chunk_index=hit.offset,
        ),
        access=EvidenceAccess(scope="public"),
        score=EvidenceScore(final=score, components={"fusion": hit.score}),
    )


class LoreSearchService:
    def __init__(
        self,
        index: ILoreIndex,
        embedder: IEmbeddingProvider,
        translator: IQueryTranslator,
        linker: EntityLinker,
        rerankers: Sequence[ICrossEncoderReranker],
        settings: LoreSearchSettings | None = None,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._translator = translator
        self._linker = linker
        self._rerankers = tuple(rerankers)
        self._settings = settings or LoreSearchSettings()

    async def search(self, question: str) -> LoreSearchResult:
        original = normalize_text(question)
        degraded: list[str] = []
        query = await self._english(original, degraded)
        # Aliases are bilingual, so either wording may be the one that names the entity.
        entities = tuple(dict.fromkeys((*self._linker.link(query), *self._linker.link(original))))
        vector = await self._embedder.embed_text(query, prefix=QUERY_PREFIX)
        hits = await self._index.search(
            query,
            vector,
            own_titles=self._linker.own_pages(entities) if entities else (),
            mentioned=entities,
            limit=self._settings.candidates,
        )
        ranked = await self._reranked(query, hits, degraded)
        evidence = tuple(to_evidence(hit, score) for hit, score in ranked[: self._settings.top_k])
        return LoreSearchResult(evidence, query, entities, tuple(degraded))

    async def _english(self, question: str, degraded: list[str]) -> str:
        try:
            return normalize_text(await self._translator.to_english(question)) or question
        except QueryTranslationError:
            degraded.append("translation_failed")
            return question

    async def _reranked(
        self, query: str, hits: list[LoreHit], degraded: list[str]
    ) -> list[tuple[LoreHit, float]]:
        head = hits[: self._settings.rerank_candidates]
        documents = [rerank_document(hit) for hit in head]
        for reranker in self._rerankers:
            try:
                scores = await reranker.rerank(query, documents) if head else []
            except RerankerUnavailableError as error:
                degraded.append(f"rerank_{reranker.provider_name}_{error.failure_kind.value}")
                continue
            order = sorted(range(len(head)), key=lambda index: -scores[index])
            tail = hits[len(head) :]
            return [(head[i], scores[i]) for i in order] + [(hit, hit.score) for hit in tail]
        # Fusion order stays meaningful, so losing every reranker lowers quality but not safety.
        degraded.append("rerank_skipped")
        return [(hit, hit.score) for hit in hits]
