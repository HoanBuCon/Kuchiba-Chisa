"""Typed knowledge lookups that answer list questions without vector search (ADV-004)."""

from app.domain.ingestion.knowledge import Alias, AliasKind, Entity, KnowledgeBase, Quest
from app.domain.ingestion.knowledge_queries import (
    find_entities,
    get_entity,
    quests_in_chapter,
    quests_with_character,
)


def _entity(page_id, title, entity_type="resonator", **fields) -> Entity:
    return Entity(page_id, title, entity_type, fields, None, None, None, None)


def _quest(page_id, title, speakers=(), **fields) -> Quest:
    return Quest(page_id, title, fields, None, None, (), (), tuple(speakers))


KB = KnowledgeBase(
    entities=(
        _entity(1, "Chisa", attribute="Havoc", weapon="Broadblade", birthplace="Ashinohara"),
        _entity(2, "Taoqi", attribute="Havoc", weapon="Broadblade", birthplace="Huanglong"),
        _entity(
            3,
            "Danjin",
            attribute="Havoc",
            weapon="Sword",
            affiliation="Jinzhou (on profile)\nMidnight Rangers",
        ),
        _entity(4, "Chisa NPC", "faction", attribute="Havoc", weapon="Broadblade"),
    ),
    aliases=(
        Alias("Kuchiba Chisa", "Chisa", AliasKind.REDIRECT, "high"),
        Alias("Honami", "Taoqi", AliasKind.INFERRED, "inferred"),
    ),
    glossary=(),
    quests=(
        _quest(10, "Act One", speakers=("Chisa", "Rover"), chapter="Chapter II: Act I"),
        _quest(11, "Segue One", chapter="Chapter II: Segue", characters="Abby, Chisa, Taoqi"),
        _quest(12, "Far Away", speakers=("Rover",), chapter="Chapter III: Segue"),
        _quest(13, "Chapter Twelve Act", chapter="Chapter XII: Act I"),
    ),
    locations=(),
)


def _titles(items) -> list[str]:
    return [item.title for item in items]


def test_find_entities_requires_every_field_and_respects_the_type() -> None:
    found = find_entities(
        KB, entity_type="resonator", fields={"attribute": "havoc", "weapon": "BROADBLADE"}
    )

    assert _titles(found) == ["Chisa", "Taoqi"]


def test_find_entities_matches_whole_values_and_ignores_notes() -> None:
    assert _titles(find_entities(KB, fields={"affiliation": "Jinzhou"})) == ["Danjin"]
    assert _titles(find_entities(KB, fields={"affiliation": "Midnight Rangers"})) == ["Danjin"]
    assert find_entities(KB, fields={"affiliation": "Jin"}) == []


def test_find_entities_on_a_missing_field_finds_nothing() -> None:
    assert find_entities(KB, fields={"nope": "x"}) == []


def test_get_entity_uses_title_or_trusted_alias_only() -> None:
    assert get_entity(KB, "chisa").page_id == 1
    assert get_entity(KB, "Kuchiba Chisa").page_id == 1
    assert get_entity(KB, "Honami") is None
    assert get_entity(KB, "Nobody") is None


def test_quests_with_character_reads_speakers_and_infobox() -> None:
    assert _titles(quests_with_character(KB, "chisa")) == ["Act One", "Segue One"]


def test_quests_in_chapter_matches_a_part_or_the_whole_chapter_only() -> None:
    assert _titles(quests_in_chapter(KB, "Chapter II: Segue")) == ["Segue One"]
    assert _titles(quests_in_chapter(KB, "Chapter II")) == ["Act One", "Segue One"]
