"""Gold stage: assemble every page's accepted silver into one chunked corpus (ING-004, ING-011)."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.domain.ingestion.chunking import (
    SENTENCE_END,
    Chunk,
    Chunker,
    ChunkPolicy,
    TokenCounter,
)
from app.domain.ingestion.dedup import OwnerPolicy, deduplicate, drop_duplicate_bodies, fingerprint
from app.domain.ingestion.documents import CanonicalDocument
from app.domain.ingestion.knowledge import build_knowledge, enrich_chunks, knowledge_counts
from app.domain.ingestion.pages import PageState
from app.domain.ingestion.units import Unit, document_units
from app.domain.interfaces.gold import IGoldStore
from app.domain.interfaces.silver import ISilverLedger, ISilverStore
from app.domain.interfaces.wiki_ingestion import IWikiInventory

_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class GoldSettings:
    assembler_version: str
    config_hash: str
    tokenizer_model: str
    chunk_policy: ChunkPolicy
    owner_policy: OwnerPolicy
    tiny_chunk_tokens: int
    tokenizer_sha256: str = ""


@dataclass(frozen=True)
class GoldReport:
    corpus_version: str
    path: str
    quality: dict[str, int]


def corpus_fingerprint(chunks: Sequence[Chunk]) -> str:
    """Equal for two runs with the same content, whatever their dates, so a no-op is visible."""
    digest = hashlib.sha256()
    for evidence, text in sorted((chunk.evidence_id, chunk.text) for chunk in chunks):
        digest.update(f"{evidence}\0{text}\0".encode())
    return digest.hexdigest()


def _collapsed(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def uncovered_units(units: Sequence[Unit], chunks: Sequence[Chunk]) -> list[Unit]:
    """Coverage invariant (ING-004): every kept unit's text survives chunking unchanged."""
    by_page: dict[int, list[str]] = defaultdict(list)
    for chunk in chunks:
        by_page[chunk.page_id].append(chunk.text)
    corpus = {page: _collapsed(" ".join(texts)) for page, texts in by_page.items()}
    return [unit for unit in units if not _is_covered(unit.text, corpus.get(unit.page_id, ""))]


def _is_covered(text: str, corpus: str) -> bool:
    """Long turns are cut with overlap, so they may only appear whole sentence by sentence."""
    if _collapsed(text) in corpus:
        return True
    return all(_sentence_covered(_collapsed(s), corpus) for s in SENTENCE_END.split(text))


def _sentence_covered(sentence: str, corpus: str) -> bool:
    # A sentence over the model limit is the one case cut between words.
    return sentence in corpus or all(word in corpus for word in sentence.split(" "))


def quality_report(
    chunks: Sequence[Chunk], policy: ChunkPolicy, tiny_tokens: int
) -> dict[str, int]:
    """Numbers the data gate reads: size limits and exact duplicates (ING-004, ING-011)."""
    bodies = Counter(fingerprint(chunk.text) for chunk in chunks)
    return {
        "chunks": len(chunks),
        "max_tokens": max((chunk.tokens for chunk in chunks), default=0),
        "over_limit": sum(chunk.tokens > policy.max_tokens for chunk in chunks),
        "under_minimum": sum(chunk.tokens < policy.min_tokens for chunk in chunks),
        "tiny": sum(chunk.tokens < tiny_tokens for chunk in chunks),
        "duplicate_bodies": sum(count - 1 for count in bodies.values()),
    }


class GoldStage:
    def __init__(
        self,
        inventory: IWikiInventory,
        silver: ISilverStore,
        ledger: ISilverLedger,
        gold: IGoldStore,
        count_tokens: TokenCounter,
        settings: GoldSettings,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inventory = inventory
        self._silver = silver
        self._ledger = ledger
        self._gold = gold
        self._chunker = Chunker(count_tokens, settings.chunk_policy)
        self._settings = settings
        self._clock = clock

    async def run(self) -> GoldReport:
        states = await self._inventory.load()
        documents, missing = await self._effective_documents(states)
        units = [unit for document in documents for unit in document_units(document)]
        deduped = deduplicate(units, self._settings.owner_policy)
        chunked = self._chunker.chunk(deduped.units)
        uncovered = uncovered_units(deduped.units, chunked)
        knowledge = build_knowledge(documents, states)
        chunks = enrich_chunks(
            drop_duplicate_bodies(chunked, self._settings.owner_policy), knowledge
        )
        quality = {
            **quality_report(chunks, self._settings.chunk_policy, self._settings.tiny_chunk_tokens),
            "pages": len(documents),
            "pages_without_silver": missing,
            "units_removed_as_duplicates": len(units) - len(deduped.units),
            "uncovered_units": len(uncovered),
        }
        version = self._gold.next_version(self._clock().date())
        manifest = self._manifest(version, documents, chunks, quality)
        manifest["counts"]["knowledge"] = knowledge_counts(knowledge)
        path = self._gold.write(version, chunks, deduped.duplicate_of, knowledge, manifest)
        return GoldReport(version, path, quality)

    async def _effective_documents(
        self, states: Mapping[int, PageState]
    ) -> tuple[list[CanonicalDocument], int]:
        """Use each page's last-known-good; a page that never passed its checks stays out."""
        entries = await self._ledger.load()
        documents, missing = [], 0
        for page_id in sorted(states):
            if not states[page_id].in_text_scope:
                continue
            entry = entries.get(page_id)
            if entry is None or entry.lkg_path is None:
                missing += 1
            else:
                documents.append(self._silver.load(entry.lkg_path))
        return documents, missing

    def _manifest(
        self,
        version: str,
        documents: Sequence[CanonicalDocument],
        chunks: Sequence[Chunk],
        quality: Mapping[str, int],
    ) -> dict[str, Any]:
        settings = self._settings
        return {
            "corpus_version": version,
            "created_at": self._clock().isoformat(),
            "components": {
                "assembler": settings.assembler_version,
                "config_hash": settings.config_hash,
                "cleaners": sorted({document.cleaner_version for document in documents}),
                "tokenizer": settings.tokenizer_model,
                "tokenizer_sha256": settings.tokenizer_sha256,
                "passage_prefix": settings.chunk_policy.passage_prefix,
            },
            "source_snapshot": {str(d.page_id): d.revid for d in documents},
            "counts": {
                "collection": dict(Counter(chunk.collection.value for chunk in chunks)),
                "family": dict(Counter(chunk.family or "" for chunk in chunks)),
                "kind": dict(Counter(chunk.kind for chunk in chunks)),
            },
            "logical_sha256": corpus_fingerprint(chunks),
            "quality": dict(quality),
        }
