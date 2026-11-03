"""Typed read-only lookups for questions vector search cannot answer: lists and facts (ADV-004)."""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.ingestion.entity_linking import fold_for_matching
from app.domain.ingestion.knowledge import Entity, KnowledgeBase, Quest


def _field_values(value: str | None) -> tuple[str, ...]:
    """Infobox fields hold one value per line, some with a note: "Jinzhou (on profile)"."""
    lines = (line.split("(")[0] for line in (value or "").split("\n"))
    return tuple(fold_for_matching(line.strip()) for line in lines if line.strip())


def _character_names(value: str | None) -> tuple[str, ...]:
    """Quest infoboxes list characters on one comma-separated line."""
    return tuple(
        fold_for_matching(name.strip()) for name in (value or "").split(",") if name.strip()
    )


def find_entities(
    knowledge: KnowledgeBase, *, entity_type: str | None = None, fields: Mapping[str, str]
) -> list[Entity]:
    """Entities whose every named field holds the exact value: "Fire" never finds "Firefly"."""
    wanted = {name: fold_for_matching(value) for name, value in fields.items()}
    return [
        entity
        for entity in knowledge.entities
        if (entity_type is None or entity.entity_type == entity_type)
        and all(value in _field_values(entity.fields.get(name)) for name, value in wanted.items())
    ]


def get_entity(knowledge: KnowledgeBase, name: str) -> Entity | None:
    """Exact title or a trusted alias; inferred aliases name regions, not entities to describe."""
    wanted = fold_for_matching(name)
    titles = {fold_for_matching(entity.title): entity for entity in knowledge.entities}
    if wanted in titles:
        return titles[wanted]
    for alias in knowledge.aliases:
        if alias.confidence == "high" and fold_for_matching(alias.alias) == wanted:
            return titles.get(fold_for_matching(alias.target))
    return None


def quests_with_character(knowledge: KnowledgeBase, name: str) -> list[Quest]:
    wanted = fold_for_matching(name)
    return [
        quest
        for quest in knowledge.quests
        if wanted in _character_names(quest.fields.get("characters"))
        or wanted in map(fold_for_matching, quest.speakers)
    ]


def quests_in_chapter(knowledge: KnowledgeBase, chapter: str) -> list[Quest]:
    """Matches a whole chapter ("Chapter II") or one part of it ("Chapter II: Segue")."""
    wanted = fold_for_matching(chapter)
    return [
        quest
        for quest in knowledge.quests
        if any(
            value == wanted or value.startswith(f"{wanted}:")
            for value in _field_values(quest.fields.get("chapter"))
        )
    ]


def quests_at_location(knowledge: KnowledgeBase, location: str) -> list[Quest]:
    """Inferred aliases count here: they exist to name places, as with Honami (KNW-004)."""
    wanted = fold_for_matching(location)
    places = {wanted}
    places.update(
        fold_for_matching(alias.target)
        for alias in knowledge.aliases
        if fold_for_matching(alias.alias) == wanted
    )
    return [
        quest
        for quest in knowledge.quests
        if places.intersection(map(fold_for_matching, quest.locations))
    ]
