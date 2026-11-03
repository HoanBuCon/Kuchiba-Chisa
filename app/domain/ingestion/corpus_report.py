"""What the Corpus Explorer shows: diff, quarantine and distributions of a release (ING-017)."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.knowledge import AliasKind, KnowledgeBase, has_corpus_text
from app.domain.ingestion.page_checks import Verdict
from app.domain.interfaces.silver import SilverEntry

TOKEN_BUCKET = 50
SAMPLE_PER_FAMILY = 3


@dataclass(frozen=True)
class PageChange:
    page_id: int
    title: str
    added_chunks: int
    removed_chunks: int


@dataclass(frozen=True)
class CorpusDiff:
    added: tuple[PageChange, ...] = ()
    changed: tuple[PageChange, ...] = ()
    removed: tuple[PageChange, ...] = ()

    @property
    def page_ids(self) -> frozenset[int]:
        return frozenset(c.page_id for c in (*self.added, *self.changed))


@dataclass(frozen=True)
class FlaggedPage:
    page_id: int
    title: str
    family: str
    verdict: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class FamilyDistribution:
    family: str
    chunks: int
    pages: int
    median_tokens: int
    # Lower bound of each token bucket -> chunk count.
    histogram: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeSummary:
    entities: int
    structured_only: int
    aliases: int
    inferred_aliases: int
    inferred_with_evidence: int
    glossary: int
    quests: int


def _by_page(chunks: Iterable[Chunk]) -> dict[int, list[Chunk]]:
    pages: dict[int, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        pages[chunk.page_id].append(chunk)
    return pages


def _title(chunks: Sequence[Chunk]) -> str:
    return chunks[0].title if chunks else ""


def diff_corpus(current: Iterable[Chunk], previous: Iterable[Chunk]) -> CorpusDiff:
    """Compared by evidence ID, which only changes when the text changes (ING-015)."""
    now, before = _by_page(current), _by_page(previous)
    added: list[PageChange] = []
    changed: list[PageChange] = []
    for page_id, chunks in sorted(now.items()):
        ids = {chunk.evidence_id for chunk in chunks}
        old = {chunk.evidence_id for chunk in before.get(page_id, [])}
        if ids == old:
            continue
        change = PageChange(page_id, _title(chunks), len(ids - old), len(old - ids))
        (changed if page_id in before else added).append(change)
    removed = [
        PageChange(page_id, _title(chunks), 0, len(chunks))
        for page_id, chunks in sorted(before.items())
        if page_id not in now
    ]
    return CorpusDiff(tuple(added), tuple(changed), tuple(removed))


def flagged_pages(
    entries: Mapping[int, SilverEntry], titles: Mapping[int, tuple[str, str]]
) -> tuple[FlaggedPage, ...]:
    """`titles` maps a page ID to (title, family); routine accepted pages are left out."""
    review = {Verdict.QUARANTINE, Verdict.HOLD}
    rows = [
        FlaggedPage(page_id, *titles.get(page_id, ("", "")), entry.verdict.value, entry.reasons)
        for page_id, entry in sorted(entries.items())
        if entry.verdict in review
    ]
    return tuple(sorted(rows, key=lambda row: (row.reasons, row.family, row.page_id)))


def _median(values: Sequence[int]) -> int:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0


def distributions(chunks: Iterable[Chunk]) -> tuple[FamilyDistribution, ...]:
    families: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        families[chunk.family or "none"].append(chunk)
    return tuple(
        FamilyDistribution(
            family=family,
            chunks=len(rows),
            pages=len({row.page_id for row in rows}),
            median_tokens=_median([row.tokens for row in rows]),
            histogram=dict(
                sorted(Counter(row.tokens // TOKEN_BUCKET * TOKEN_BUCKET for row in rows).items())
            ),
        )
        for family, rows in sorted(families.items())
    )


def knowledge_summary(knowledge: KnowledgeBase) -> KnowledgeSummary:
    inferred = [alias for alias in knowledge.aliases if alias.kind == AliasKind.INFERRED]
    return KnowledgeSummary(
        entities=len(knowledge.entities),
        structured_only=sum(not has_corpus_text(e) for e in knowledge.entities),
        aliases=len(knowledge.aliases),
        inferred_aliases=len(inferred),
        inferred_with_evidence=sum(bool(alias.evidence) for alias in inferred),
        glossary=len(knowledge.glossary),
        quests=len(knowledge.quests),
    )


def pages_to_inspect(
    diff: CorpusDiff, flagged: Iterable[FlaggedPage], chunks: Iterable[Chunk]
) -> tuple[int, ...]:
    """Everything that needs eyes, plus a fixed sample so an unchanged family is still seen."""
    selected = set(diff.page_ids) | {row.page_id for row in flagged}
    by_family: dict[str, set[int]] = defaultdict(set)
    for chunk in chunks:
        by_family[chunk.family or "none"].add(chunk.page_id)
    for pages in by_family.values():
        selected.update(sorted(pages)[:SAMPLE_PER_FAMILY])
    return tuple(sorted(selected))
