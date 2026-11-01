"""Silver layer: a wiki page cleaned into typed blocks plus side outputs (ING-003, ADR-0002 L2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class BlockKind(StrEnum):
    PROSE = "prose"
    QUOTE = "quote"
    LIST = "list"
    TABLE = "table"
    # A titled passage such as a character story or archive entry (th title, td text).
    STORY = "story"
    # Key-value rows outside the infobox, e.g. "Resonance Power: Eye of Unraveling".
    FACTS = "facts"
    DIALOGUE = "dialogue"


class TurnKind(StrEnum):
    LINE = "line"
    NARRATION = "narration"
    CHOICE = "choice"


@dataclass(frozen=True)
class DialogueTurn:
    kind: TurnKind
    text: str
    speaker: str | None = None
    # Nesting depth of choice branches; 0 is the main line.
    depth: int = 0

    def render(self) -> str:
        indent = "  " * self.depth
        if self.kind is TurnKind.CHOICE:
            return f"{indent}> {self.text}"
        if self.speaker:
            return f"{indent}{self.speaker}: {self.text}"
        return f"{indent}{self.text}"


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    section: tuple[str, ...]
    text: str
    title: str | None = None
    turns: tuple[DialogueTurn, ...] = ()
    # Variant label such as a voiceline unlock condition or a Rover gender tab (E5).
    variant: str | None = None


@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    definition: str


@dataclass(frozen=True)
class CanonicalDocument:
    page_id: int
    title: str
    revid: int
    family: str | None
    cleaner_version: str
    blocks: tuple[Block, ...]
    infoboxes: tuple[dict, ...] = ()
    glossary: tuple[GlossaryEntry, ...] = ()
    links: tuple[str, ...] = ()
    removed: dict[str, int] = field(default_factory=dict)

    @property
    def text_length(self) -> int:
        return sum(len(block.text) for block in self.blocks)
