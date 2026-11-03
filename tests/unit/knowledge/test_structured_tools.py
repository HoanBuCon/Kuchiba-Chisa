"""Structured tools: alias resolution, quest filters and typed evidence (KNW-004)."""

from app.domain.ingestion.knowledge import Alias, Entity, KnowledgeBase, Quest
from app.domain.services.knowledge.structured_tools import MAX_LISTED_QUESTS, StructuredTools

VERSION = "2026.11.04-1"


def _entity(page_id, title, entity_type="resonator", **fields) -> Entity:
    return Entity(page_id, title, entity_type, fields, None, None, None, None)


def _quest(page_id, title, chapter, locations=(), characters="") -> Quest:
    fields = {"chapter": chapter, "characters": characters}
    return Quest(page_id, title, fields, "A story.", None, ("Step one.",), (), (), tuple(locations))


KNOWLEDGE = KnowledgeBase(
    entities=(
        _entity(1, "Chisa", attribute="Havoc", weapon="Broadblade"),
        _entity(2, "Taoqi", attribute="Havoc", weapon="Broadblade"),
        _entity(3, "Lynae", attribute="Spectro", weapon="Pistols"),
        _entity(4, "Stringmaster", "structured", rarity="5"),
    ),
    aliases=(
        Alias("Kuchiba Chisa", "Chisa", "other_language", "high"),
        Alias("Guess", "Taoqi", "inferred", "inferred"),
        Alias("Honami", "Chronorift Metropolis", "inferred", "inferred", ("Honami Park",)),
    ),
    glossary=(),
    quests=(
        _quest(10, "First Light", "Chapter III", ["Chronorift Metropolis"], "Chisa, Rover"),
        _quest(11, "Second Light", "Chapter III", ["Chronorift Metropolis"], "Rover"),
        _quest(12, "Far Shore", "Chapter II", ["Ragunna"], "Chisa"),
    ),
    locations=(),
)
TOOLS = StructuredTools(KNOWLEDGE, VERSION)


def _titles(evidence) -> list[str]:
    return [item.provenance.source_id for item in evidence]


def test_get_entity_returns_fields_as_public_evidence() -> None:
    evidence = TOOLS.get_entity("Chisa")

    assert "attribute: Havoc" in evidence.text
    assert evidence.access.scope == "public"
    assert evidence.evidence_id == f"kb:{VERSION}:entities:1"
    assert evidence.provenance.source_version == VERSION


def test_get_entity_follows_trusted_aliases_only() -> None:
    assert TOOLS.get_entity("kuchiba chisa").provenance.page_id == 1
    assert TOOLS.get_entity("Guess") is None
    assert TOOLS.get_entity("Nobody") is None


def test_entities_without_a_text_page_are_still_found() -> None:
    assert "rarity: 5" in TOOLS.get_entity("Stringmaster").text


def test_find_entities_requires_every_field() -> None:
    found = TOOLS.find_entities(entity_type="resonator", fields={"attribute": "Havoc"})

    assert _titles(found) == ["Chisa", "Taoqi"]
    both = {"attribute": "Havoc", "weapon": "Pistols"}
    assert TOOLS.find_entities(fields=both) == ()


def test_list_quests_resolves_an_inferred_location_alias() -> None:
    assert _titles(TOOLS.list_quests(location="Honami")) == ["First Light", "Second Light"]
    assert _titles(TOOLS.list_quests(location="Ragunna")) == ["Far Shore"]


def test_list_quests_combines_filters_as_and() -> None:
    found = TOOLS.list_quests(location="Honami", character="Chisa")

    assert _titles(found) == ["First Light"]
    assert TOOLS.list_quests(chapter="Chapter II", location="Honami") == ()


def test_list_quests_without_a_filter_lists_nothing() -> None:
    assert TOOLS.list_quests() == ()


def test_quest_list_is_compact_and_capped() -> None:
    quests = tuple(
        _quest(100 + n, f"Quest {n}", "Chapter I", ["Hub"]) for n in range(MAX_LISTED_QUESTS + 5)
    )
    tools = StructuredTools(KnowledgeBase((), (), (), quests, ()), VERSION)

    found = tools.list_quests(location="Hub")

    assert len(found) == MAX_LISTED_QUESTS
    assert found[0].text == "Quest 0 (Chapter I)"


def test_get_quest_returns_the_full_card() -> None:
    evidence = TOOLS.get_quest("first light")

    assert "A story." in evidence.text
    assert "Step one." in evidence.text
    assert "locations: Chronorift Metropolis" in evidence.text
    assert TOOLS.get_quest("Missing") is None
