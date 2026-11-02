"""Merge units into chunks measured in real model tokens (ING-004, E1)."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from itertools import groupby

from app.domain.ingestion.units import Collection, Unit

SENTENCE_END = re.compile(r"(?<=[.!?…。！？])\s+")
# The namespace only has to be fixed: point ids are uuid5(evidence id) (ADR-0002).
POINT_NAMESPACE = uuid.UUID("6f0c4c5e-6d62-4f8e-9c1e-2b1f8f0d7a11")

TokenCounter = Callable[[str], int]


@dataclass(frozen=True)
class ChunkPolicy:
    target_tokens: int = 350
    max_tokens: int = 450
    min_tokens: int = 120
    overlap_turns: int = 1
    passage_prefix: str = "passage: "


@dataclass(frozen=True)
class Chunk:
    evidence_id: str
    point_id: str
    page_id: int
    title: str
    family: str | None
    collection: Collection
    kind: str
    section: tuple[str, ...]
    text: str
    embedding_text: str
    tokens: int


def embedding_text(unit: Unit, text: str, policy: ChunkPolicy) -> str:
    """e5 passage protocol with title and section so a chunk is understandable alone (KNW-005)."""
    section = " > ".join(unit.section)
    header = f"{unit.title}\n{section}\n" if section else f"{unit.title}\n"
    return f"{policy.passage_prefix}{header}{text}"


class Chunker:
    def __init__(self, count_tokens: TokenCounter, policy: ChunkPolicy) -> None:
        self._count = count_tokens
        self._policy = policy

    def chunk(self, units: Sequence[Unit]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for _, group in groupby(units, key=lambda u: (u.page_id, u.group)):
            members = list(group)
            texts = self._turn_windows(members) if members[0].is_turn else self._merge(members)
            chunks.extend(self._build(members[0], text) for text in texts)
        return _with_evidence_ids(chunks)

    def _tokens(self, unit: Unit, text: str) -> int:
        return self._count(embedding_text(unit, text, self._policy))

    def _fits(self, unit: Unit, text: str, limit: int) -> bool:
        return self._tokens(unit, text) <= limit

    def _merge(self, members: list[Unit]) -> list[str]:
        """Greedy fill to the target; a lone over-long unit is split by sentence."""
        pieces = [piece for unit in members for piece in self._fit_unit(unit)]
        merged: list[str] = []
        for piece in pieces:
            candidate = f"{merged[-1]}\n{piece}" if merged else piece
            if merged and self._fits(members[0], candidate, self._policy.target_tokens):
                merged[-1] = candidate
            else:
                merged.append(piece)
        return self._absorb_small_tail(members[0], merged)

    def _absorb_small_tail(self, unit: Unit, merged: list[str]) -> list[str]:
        """A tail below the minimum joins its predecessor when the result still fits."""
        if len(merged) > 1 and self._tokens(unit, merged[-1]) < self._policy.min_tokens:
            candidate = f"{merged[-2]}\n{merged[-1]}"
            if self._fits(unit, candidate, self._policy.max_tokens):
                return [*merged[:-2], candidate]
        return merged

    def _fit_unit(self, unit: Unit) -> list[str]:
        if self._fits(unit, unit.text, self._policy.max_tokens):
            return [unit.text]
        return list(self._split_sentences(unit, unit.text))

    def _split_sentences(self, unit: Unit, text: str) -> Iterator[str]:
        current = ""
        for sentence in SENTENCE_END.split(text):
            candidate = f"{current} {sentence}".strip()
            if current and not self._fits(unit, candidate, self._policy.target_tokens):
                yield current
                candidate = sentence
            if not self._fits(unit, candidate, self._policy.max_tokens):
                yield from self._split_words(unit, candidate)
                candidate = ""
            current = candidate
        if current:
            yield current

    def _split_words(self, unit: Unit, text: str) -> Iterator[str]:
        """Last resort for a single sentence longer than the model limit."""
        words, current = text.split(" "), ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and not self._fits(unit, candidate, self._policy.max_tokens):
                yield current
                candidate = word
            current = candidate
        if current:
            yield current

    def _turn_windows(self, members: list[Unit]) -> list[str]:
        """Windows over turns: cut at scene starts once big enough, else slide with overlap (E1)."""
        head = members[0]
        windows: list[list[str]] = [[]]
        scene = head.scene
        for unit in members:
            starts_scene, scene = unit.scene != scene, unit.scene
            for turn in self._fit_unit(unit):
                window = windows[-1]
                if (
                    starts_scene
                    and self._tokens(head, "\n".join(window)) >= self._policy.min_tokens
                ):
                    windows.append([turn])
                elif window and not self._fits(
                    head, "\n".join([*window, turn]), self._policy.target_tokens
                ):
                    windows.append(self._carry_over(head, window, turn))
                else:
                    window.append(turn)
                starts_scene = False
        return self._absorb_small_tail(head, ["\n".join(window) for window in windows if window])

    def _carry_over(self, unit: Unit, window: list[str], turn: str) -> list[str]:
        overlap = window[-self._policy.overlap_turns :] if self._policy.overlap_turns else []
        carried = [*overlap, turn]
        return carried if self._fits(unit, "\n".join(carried), self._policy.max_tokens) else [turn]

    def _build(self, unit: Unit, text: str) -> Chunk:
        embedded = embedding_text(unit, text, self._policy)
        return Chunk(
            evidence_id="",
            point_id="",
            page_id=unit.page_id,
            title=unit.title,
            family=unit.family,
            collection=unit.collection,
            kind=unit.kind,
            section=unit.section,
            text=text,
            embedding_text=embedded,
            tokens=self._count(embedded),
        )


def evidence_id(page_id: int, text: str) -> str:
    """Stable while the chunk text is unchanged, so caches and old citations keep working."""
    return f"wiki:{page_id}:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


def _with_evidence_ids(chunks: list[Chunk]) -> list[Chunk]:
    seen: dict[str, int] = {}
    result = []
    for chunk in chunks:
        base = evidence_id(chunk.page_id, chunk.text)
        seen[base] = seen.get(base, 0) + 1
        identifier = base if seen[base] == 1 else f"{base}:{seen[base]}"
        point = str(uuid.uuid5(POINT_NAMESPACE, identifier))
        result.append(replace(chunk, evidence_id=identifier, point_id=point))
    return result
