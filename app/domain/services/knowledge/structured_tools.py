"""`get_entity`, `list_quests`, `get_quest`: typed, read-only, returning Evidence (KNW-001)."""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.ingestion.entity_linking import fold_for_matching
from app.domain.ingestion.knowledge import Entity, KnowledgeBase, Quest
from app.domain.ingestion.knowledge_queries import (
    find_entities,
    get_entity,
    quests_at_location,
    quests_in_chapter,
    quests_with_character,
)
from app.domain.models.evidence import (
    Evidence,
    EvidenceAccess,
    EvidenceProvenance,
    EvidenceScore,
)

# Exact structured lookups outrank any similarity score.
STRUCTURED_SCORE = 1.0
MAX_LISTED_QUESTS = 30


def _evidence(kind: str, page_id: int, title: str, text: str, version: str) -> Evidence:
    return Evidence(
        evidence_id=f"kb:{version}:{kind}:{page_id}",
        kind="lore",
        text=text,
        provenance=EvidenceProvenance(
            source_id=title,
            source_title=title,
            source_type="canon",
            collection=f"kb_{kind}",
            source_version=version,
            page_id=page_id,
        ),
        access=EvidenceAccess(scope="public"),
        score=EvidenceScore(final=STRUCTURED_SCORE),
    )


def _entity_text(entity: Entity) -> str:
    fields = "\n".join(f"{key}: {value}" for key, value in entity.fields.items())
    return f"{entity.title}\n{fields}" if fields else entity.title


def _quest_text(quest: Quest) -> str:
    lines = [quest.title]
    lines.extend(f"{key}: {value}" for key, value in quest.fields.items())
    if quest.locations:
        lines.append(f"locations: {', '.join(quest.locations)}")
    lines.extend(text for text in (quest.description, quest.summary) if text)
    lines.extend(quest.steps)
    return "\n".join(lines)


def _quest_line(quest: Quest) -> str:
    """Listing stays one line per quest, so a long list cannot fill the context budget."""
    chapter = quest.fields.get("chapter")
    return f"{quest.title} ({chapter})" if chapter else quest.title


class StructuredTools:
    """Bound to one corpus release, so a lookup never mixes two versions of the facts."""

    def __init__(self, knowledge: KnowledgeBase, corpus_version: str) -> None:
        self._knowledge = knowledge
        self._version = corpus_version

    def get_entity(self, name: str) -> Evidence | None:
        entity = get_entity(self._knowledge, name)
        if entity is None:
            return None
        return self._entity_evidence(entity)

    def find_entities(
        self, *, fields: Mapping[str, str], entity_type: str | None = None
    ) -> tuple[Evidence, ...]:
        found = find_entities(self._knowledge, entity_type=entity_type, fields=fields)
        return tuple(self._entity_evidence(entity) for entity in found)

    def get_quest(self, name: str) -> Evidence | None:
        wanted = fold_for_matching(name)
        for quest in self._knowledge.quests:
            if fold_for_matching(quest.title) == wanted:
                text = _quest_text(quest)
                return _evidence("quests", quest.page_id, quest.title, text, self._version)
        return None

    def list_quests(
        self,
        *,
        location: str | None = None,
        chapter: str | None = None,
        character: str | None = None,
    ) -> tuple[Evidence, ...]:
        """Every given filter must hold; no filter at all lists nothing rather than everything."""
        selections = [
            quests_at_location(self._knowledge, location) if location else None,
            quests_in_chapter(self._knowledge, chapter) if chapter else None,
            quests_with_character(self._knowledge, character) if character else None,
        ]
        chosen = [selection for selection in selections if selection is not None]
        if not chosen:
            return ()
        kept = {quest.page_id for quest in chosen[0]}
        for selection in chosen[1:]:
            kept &= {quest.page_id for quest in selection}
        quests = [quest for quest in chosen[0] if quest.page_id in kept]
        return tuple(
            _evidence("quests", quest.page_id, quest.title, _quest_line(quest), self._version)
            for quest in quests[:MAX_LISTED_QUESTS]
        )

    def _entity_evidence(self, entity: Entity) -> Evidence:
        text = _entity_text(entity)
        return _evidence("entities", entity.page_id, entity.title, text, self._version)
