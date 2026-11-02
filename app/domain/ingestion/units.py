"""Split silver documents into the smallest retrievable units for chunking (ING-004)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

from app.domain.ingestion.documents import Block, BlockKind, CanonicalDocument, TurnKind

PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
PROFILE = "profile"
# Thinner infoboxes ("type: Lore") say nothing retrievable; their fields stay in the entity store.
MIN_PROFILE_FIELDS = 3
_LINE_KINDS = {BlockKind.LIST, BlockKind.TABLE, BlockKind.FACTS}


class Collection(StrEnum):
    CANON = "lore_canon"
    DIALOGUE = "lore_dialogue"


@dataclass(frozen=True)
class Unit:
    """Units sharing `group` may be merged into one chunk; nothing merges across groups."""

    page_id: int
    title: str
    family: str | None
    collection: Collection
    kind: str
    section: tuple[str, ...]
    group: str
    text: str
    # Dialogue turns overlap between windows; everything else is atomic.
    is_turn: bool = False
    # Preferred cut points inside a dialogue block (E1); 0 outside dialogue.
    scene: int = 0


def _label(block: Block) -> str | None:
    """Story and voiceline titles lead their text, so short entries can share one chunk."""
    if block.title:
        return f"{block.title} ({block.variant})" if block.variant else block.title
    return f"({block.variant})" if block.variant else None


def _has_words(text: str) -> bool:
    return any(character.isalnum() for character in text)


def _pieces(block: Block) -> list[str]:
    raw = block.text.split("\n") if block.kind in _LINE_KINDS else PARAGRAPH_BREAK.split(block.text)
    return [piece.strip() for piece in raw if _has_words(piece)]


def _block_units(document: CanonicalDocument, index: int, block: Block) -> Iterator[Unit]:
    if block.kind is BlockKind.DIALOGUE:
        yield from _dialogue_units(document, block, index)
        return
    # Adjacent blocks of one section merge, so the group is the section, not the block.
    group = f"canon:{' > '.join(block.section)}"
    pieces = _pieces(block)
    label = _label(block)
    if label and pieces:
        separator = "\n" if block.title else " "
        pieces[0] = f"{label}{separator}{pieces[0]}"
    for piece in pieces:
        yield _unit(document, block.kind.value, block.section, group, piece)


def _dialogue_units(document: CanonicalDocument, block: Block, index: int) -> Iterator[Unit]:
    """A top-level narration line (a quest step or scene cue) starts a new scene."""
    scene = 0
    for turn in block.turns:
        if turn.kind is TurnKind.NARRATION and turn.depth == 0:
            scene += 1
        yield Unit(
            page_id=document.page_id,
            title=document.title,
            family=document.family,
            collection=Collection.DIALOGUE,
            kind=block.kind.value,
            section=block.section,
            group=f"dialogue:{index}",
            text=turn.render(),
            is_turn=True,
            scene=scene,
        )


def _unit(
    document: CanonicalDocument, kind: str, section: tuple[str, ...], group: str, text: str
) -> Unit:
    return Unit(
        document.page_id,
        document.title,
        document.family,
        Collection.CANON,
        kind,
        section,
        group,
        text,
    )


def profile_unit(document: CanonicalDocument) -> Unit | None:
    """One profile card per page built from its infobox fields, never one chunk per field."""
    fields = []
    for box in document.infoboxes:
        for key, value in box.items():
            parts = [part.strip() for part in value.split("\n") if part.strip()]
            if parts:
                fields.append(f"{key}: {', '.join(parts)}")
    if len(fields) < MIN_PROFILE_FIELDS:
        return None
    # The page name makes each card identifiable and keeps look-alike infoboxes distinct.
    text = "\n".join([document.title, *fields])
    return _unit(document, PROFILE, ("Profile",), "profile", text)


def document_units(document: CanonicalDocument) -> list[Unit]:
    profile = profile_unit(document)
    units = [profile] if profile else []
    for index, block in enumerate(document.blocks):
        units.extend(_block_units(document, index, block))
    return units
