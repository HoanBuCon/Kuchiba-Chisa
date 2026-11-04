"""Advanced flow: routing, sufficiency, one correction pass, abstaining (ADV-001, ADV-007)."""

import pytest

from app.domain.ingestion.entity_linking import EntityLinker
from app.domain.ingestion.knowledge import Alias, Entity, KnowledgeBase, LocationEdge, Quest
from app.domain.services.knowledge.advanced_retrieval import AdvancedRetrieval
from app.domain.services.knowledge.lore_search import LoreHit, LoreSearchService, LoreSearchSettings
from app.domain.services.knowledge.question_router import QuestionRouter
from app.domain.services.knowledge.structured_tools import StructuredTools
from tests.unit.knowledge.test_lore_search import Embedder, Index, Reranker, Translator

VERSION = "v1"


def _entity(page_id, title, entity_type="resonator", **fields) -> Entity:
    return Entity(page_id, title, entity_type, fields, None, None, None, None)


def _quest(page_id, title, chapter, locations, characters) -> Quest:
    fields = {"chapter": chapter, "characters": characters}
    return Quest(page_id, title, fields, None, None, (), (), (), tuple(locations))


KNOWLEDGE = KnowledgeBase(
    entities=(
        _entity(1, "Chisa", attribute="Havoc", weapon="Broadblade", birthplace="Ashinohara"),
        _entity(2, "Taoqi", attribute="Havoc", weapon="Broadblade"),
        _entity(3, "Lynae", attribute="Spectro", weapon="Pistols"),
        _entity(4, "Startorch Academy", "lore"),
    ),
    aliases=(Alias("Honami", "Chronorift Metropolis", "inferred", "inferred"),),
    glossary=(),
    quests=(
        _quest(10, "First Light", "Chapter III: Prologue", ["Chronorift Metropolis"], "Chisa"),
        _quest(11, "Far Shore", "Chapter II: Segue", ["Ragunna"], "Chisa, Rover"),
    ),
    locations=(LocationEdge("Sakura Pedway", "Chronorift Metropolis", "category"),),
)
LINKER = EntityLinker.from_knowledge(KNOWLEDGE)
ROUTER = QuestionRouter(KNOWLEDGE)


def _hit(number: int, source_kind="canon") -> LoreHit:
    return LoreHit(
        f"wiki:1:{number}", 1, "Chisa", f"text {number}", ("S",), VERSION, source_kind, 0.5
    )


def _flow(reply: str, *, score: float, hits=None, dialogue=()):
    reranker = Reranker("jina", scores=[score] * len(hits if hits is not None else [1]))
    search = LoreSearchService(
        Index(hits if hits is not None else [_hit(1)]),
        Embedder(),
        Translator(reply),
        LINKER,
        [reranker],
        LoreSearchSettings(min_scores={"jina": 0.2}),
    )
    index = Index(list(dialogue))
    return AdvancedRetrieval(search, StructuredTools(KNOWLEDGE, VERSION), ROUTER, index), index


@pytest.mark.parametrize(
    ("texts", "entities", "expected"),
    [
        (("Which main quests take place in Honami?",), (), ("Honami", None, None)),
        (("List the main quests Chisa joins.",), ("Chisa",), (None, None, "Chisa")),
        (("Which quests are in Chapter II: Segue?",), (), (None, "Chapter II: Segue", None)),
        (("Liệt kê các nhiệm vụ ở Honami",), (), ("Honami", None, None)),
    ],
)
def test_router_reads_quest_filters(texts, entities, expected) -> None:
    route = ROUTER.route(texts, entities)

    assert (route.quest_location, route.quest_chapter, route.quest_character) == expected


def test_router_reads_entity_fields_from_the_wiki_vocabulary() -> None:
    route = ROUTER.route(("Which Resonators are Havoc and use a Broadblade?",), ())

    assert route.entity_fields == {"attribute": "Havoc", "weapon": "Broadblade"}


def test_router_needs_a_listing_cue_and_a_subject() -> None:
    assert not ROUTER.route(("Tell me about quests in Honami",), ()).lists_quests
    assert not ROUTER.route(("Which food does Chisa like in Honami?",), ("Chisa",)).lists_quests
    assert ROUTER.route(("Is Havoc strong?",), ()).entity_fields == {}


def test_a_place_is_not_read_as_a_quest_character() -> None:
    route = ROUTER.route(("Which quests happen at Startorch Academy?",), ("Startorch Academy",))

    assert route.quest_character is None


async def test_strong_search_answers_with_the_profile_card_first() -> None:
    flow, dialogue = _flow("Where was Chisa born?", score=0.6)

    result = await flow.retrieve("Chisa sinh ra ở đâu?")

    assert not result.abstain and not result.expanded
    assert result.evidence[0].evidence_id == f"kb:{VERSION}:entities:1"
    assert dialogue.calls == []


async def test_listing_is_enough_even_when_search_is_weak() -> None:
    flow, _ = _flow("Which main quests take place in Honami?", score=0.05)

    result = await flow.retrieve("Nhiệm vụ nào diễn ra ở Honami?")

    assert not result.abstain
    assert result.evidence[0].provenance.source_id == "First Light"


async def test_weak_search_expands_once_into_dialogue_about_the_entity() -> None:
    flow, dialogue = _flow(
        "What is Chisa's blood type?", score=0.05, dialogue=[_hit(9, "dialogue")]
    )

    result = await flow.retrieve("Nhóm máu của Chisa?")

    assert result.expanded and not result.abstain
    assert len(dialogue.calls) == 1
    assert dialogue.calls[0][2] == ("Chisa",)
    assert result.evidence[-1].provenance.source_type == "dialogue"


async def test_weak_search_with_empty_dialogue_abstains() -> None:
    flow, _ = _flow("What is Chisa's blood type?", score=0.05)

    result = await flow.retrieve("Nhóm máu của Chisa?")

    assert result.abstain and result.expanded


async def test_profile_card_alone_does_not_count_as_an_answer() -> None:
    flow, _ = _flow("What is Chisa's blood type?", score=0.05)

    result = await flow.retrieve("Nhóm máu của Chisa?")

    assert result.abstain
    assert any(e.evidence_id.startswith("kb:") for e in result.evidence)


async def test_no_entity_means_no_dialogue_search() -> None:
    flow, dialogue = _flow("How does Chapter VII end?", score=0.05)

    result = await flow.retrieve("Chapter VII kết thúc thế nào?")

    assert result.abstain and not result.expanded
    assert dialogue.calls == []


async def test_unknown_reranker_scale_does_not_abstain_on_its_own() -> None:
    search = LoreSearchService(
        Index([_hit(1)]), Embedder(), Translator("x"), LINKER, [Reranker("other", scores=[0.0])]
    )
    flow = AdvancedRetrieval(search, StructuredTools(KNOWLEDGE, VERSION), ROUTER, Index([]))

    assert not (await flow.retrieve("x")).abstain


async def test_listing_is_returned_apart_from_search_evidence() -> None:
    flow, _ = _flow("Which main quests take place in Honami?", score=0.6)

    result = await flow.retrieve("Nhiệm vụ nào diễn ra ở Honami?")

    assert [item.provenance.source_id for item in result.listed] == ["First Light"]


async def test_plain_question_has_no_listing() -> None:
    flow, _ = _flow("Where was Chisa born?", score=0.6)

    assert (await flow.retrieve("Chisa sinh ra ở đâu?")).listed == ()


@pytest.mark.parametrize(
    "text",
    [
        "Which NPC did the Grand Architect disguise as in the quest Far Shore?",
        "Who is Chisa in this quest?",
        "Which Resonator has a Tacet Mark on her tongue?",
    ],
)
def test_a_question_about_one_thing_is_not_a_list(text) -> None:
    route = ROUTER.route((text,), ("Chisa",))

    assert not route.lists_quests
    assert route.entity_fields == {}
