"""Deterministic routing: which structured lookups a question can use, with no LLM (ADV-002)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from app.domain.ingestion.entity_linking import fold_for_matching
from app.domain.ingestion.knowledge import AliasKind, KnowledgeBase

# The cue must ask for quests themselves: "which NPC ... in that quest" is not a list.
ASKS_QUESTS = re.compile(
    r"\b(which|what|list|all|name|liet ke|nhung|cac)\W+(?:\w+\W+){0,2}"
    r"(?:quests?|missions?|nhiem vu)\b"
    r"|\b(?:quests?|nhiem vu)(?:\W+\w+){0,2}\W+nao\b"
)
# Likewise for lists of Resonators.
ASKS_RESONATORS = re.compile(
    r"\b(which|what|list|all|name|liet ke|nhung|cac)\W+(?:\w+\W+){0,1}resonators?\b"
    r"|\bresonators?\W+nao\b.*\b(?:va|and|hoac|or|o|tai|from|sinh|thuoc)\b"
)
CHAPTER = re.compile(r"\bchapter ([ivx]+)(?:\W+(prologue|segue|epilogue|act [ivx]+))?\b")
NAMED_CHAPTER = re.compile(r"\bchapter (\d+|[ivx]+)\b")
ROMAN_NUMERALS = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x")
RESONATOR_TYPE = "resonator"
# Fields whose values name a category worth listing by, not a free-text description.
LISTABLE_FIELDS = ("attribute", "weapon", "birthplace", "class", "gender")
MIN_VALUE_LENGTH = 4
PERSON_TYPES = frozenset({RESONATOR_TYPE, "faction"})


@dataclass(frozen=True)
class QuestionRoute:
    profiles: tuple[str, ...] = ()
    quest_location: str | None = None
    quest_chapter: str | None = None
    quest_character: str | None = None
    entity_fields: dict[str, str] = field(default_factory=dict)
    # The question names a chapter no quest belongs to, so nothing can answer it.
    unknown_chapter: bool = False

    @property
    def lists_quests(self) -> bool:
        return bool(self.quest_location or self.quest_chapter or self.quest_character)


def _word_in(needle: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(needle)}\b", text) is not None


def _as_roman(numeral: str) -> str:
    """A number past the table stays a number, which no known chapter equals."""
    if numeral.isdigit() and 1 <= int(numeral) <= len(ROMAN_NUMERALS):
        return ROMAN_NUMERALS[int(numeral) - 1]
    return numeral


def _chapter_label(match: re.Match[str]) -> str:
    base = f"Chapter {match[1].upper()}"
    return f"{base}: {match[2].title()}" if match[2] else base


class QuestionRouter:
    def __init__(self, knowledge: KnowledgeBase) -> None:
        self._places = self._place_names(knowledge)
        self._people = frozenset(
            entity.title for entity in knowledge.entities if entity.entity_type in PERSON_TYPES
        )
        self._values = self._field_values(knowledge)
        self._chapters = frozenset(
            numeral
            for quest in knowledge.quests
            for numeral in NAMED_CHAPTER.findall(
                fold_for_matching(quest.fields.get("chapter") or "")
            )
        )

    @staticmethod
    def _place_names(knowledge: KnowledgeBase) -> Mapping[str, str]:
        """Folded name -> the name lookups accept, for places a question may mention."""
        names = [edge.parent for edge in knowledge.locations]
        names += [alias.alias for alias in knowledge.aliases if alias.kind == AliasKind.INFERRED]
        return {fold_for_matching(name): name for name in names if len(name) >= MIN_VALUE_LENGTH}

    @staticmethod
    def _field_values(knowledge: KnowledgeBase) -> Mapping[str, tuple[str, str]]:
        """Folded value -> (field, value) over resonators, whose fields are clean enough to list."""
        values: dict[str, tuple[str, str]] = {}
        for entity in knowledge.entities:
            if entity.entity_type != RESONATOR_TYPE:
                continue
            for name in LISTABLE_FIELDS:
                for line in (entity.fields.get(name) or "").split("\n"):
                    value = line.split("(")[0].strip()
                    if len(value) >= MIN_VALUE_LENGTH:
                        values.setdefault(fold_for_matching(value), (name, value))
        return values

    def route(self, texts: Iterable[str], entities: tuple[str, ...]) -> QuestionRoute:
        """`texts` are the original and translated wording; a cue in either one counts."""
        folded = [fold_for_matching(text) for text in texts]
        route_fields: dict[str, str] = {}
        location = chapter = character = None
        if any(ASKS_QUESTS.search(text) for text in folded):
            location = self._find_place(folded)
            chapter = self._find_chapter(folded)
            character = next((name for name in entities if name in self._people), None)
        if any(ASKS_RESONATORS.search(text) for text in folded):
            route_fields = self._find_fields(folded)
        return QuestionRoute(
            entities,
            location,
            chapter,
            character,
            route_fields,
            self._names_unknown_chapter(folded),
        )

    def _names_unknown_chapter(self, folded: list[str]) -> bool:
        if not self._chapters:
            return False
        named = (_as_roman(numeral) for text in folded for numeral in NAMED_CHAPTER.findall(text))
        return any(numeral not in self._chapters for numeral in named)

    def _find_place(self, folded: list[str]) -> str | None:
        # The longest name wins, so "Jinzhou City" is not read as "Jinzhou".
        for name in sorted(self._places, key=len, reverse=True):
            if any(_word_in(name, text) for text in folded):
                return self._places[name]
        return None

    @staticmethod
    def _find_chapter(folded: list[str]) -> str | None:
        for text in folded:
            match = CHAPTER.search(text)
            if match:
                return _chapter_label(match)
        return None

    def _find_fields(self, folded: list[str]) -> dict[str, str]:
        found: dict[str, str] = {}
        for value, (name, original) in self._values.items():
            if name not in found and any(_word_in(value, text) for text in folded):
                found[name] = original
        return found
