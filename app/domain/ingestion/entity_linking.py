"""Deterministic entity linking for questions, built from the corpus knowledge base (ADV-002)."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping

from app.domain.ingestion.knowledge import Alias, KnowledgeBase

MIN_NAME_LENGTH = 4
HIGH_CONFIDENCE = "high"


def fold_for_matching(text: str) -> str:
    """Users type without diacritics or case; "chisa hoc o dau" must still find "Chisa"."""
    decomposed = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class EntityLinker:
    """Longest name wins, so "Black Shores Archipelago" is not read as "Black Shores"."""

    def __init__(self, names: Mapping[str, str], pages: Mapping[str, tuple[str, ...]]) -> None:
        self._names = {fold_for_matching(name): target for name, target in names.items()}
        self._pages = pages
        ordered = sorted(self._names, key=lambda name: (-len(name), name))
        alternation = "|".join(map(re.escape, ordered))
        self._pattern = re.compile(rf"(?<!\w)(?:{alternation})(?!\w)" if ordered else r"(?!)")

    @classmethod
    def from_knowledge(
        cls, knowledge: KnowledgeBase, extra_aliases: Iterable[Alias] = ()
    ) -> EntityLinker:
        pages: dict[str, list[str]] = defaultdict(list)
        for entity in knowledge.entities:
            pages[entity.title.split("/")[0]].append(entity.title)
        names = {root: root for root in pages if len(root) >= MIN_NAME_LENGTH}
        for alias in (*extra_aliases, *knowledge.aliases):
            usable = alias.confidence == HIGH_CONFIDENCE and len(alias.alias) >= MIN_NAME_LENGTH
            if usable and alias.target in pages:
                names.setdefault(alias.alias, alias.target)
        return cls(names, {root: tuple(titles) for root, titles in pages.items()})

    def link(self, question: str) -> tuple[str, ...]:
        found = self._pattern.findall(fold_for_matching(question))
        return tuple(dict.fromkeys(self._names[name] for name in found))

    def own_pages(self, entities: Iterable[str]) -> tuple[str, ...]:
        """An entity's main page and its subpages (Backstory, Voicelines...)."""
        return tuple(title for entity in entities for title in self._pages.get(entity, ()))
