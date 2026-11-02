"""Structured knowledge: locations, aliases with evidence, nation inference, quests, glossary."""

from dataclasses import replace
from datetime import UTC, datetime

from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.documents import (
    Block,
    BlockKind,
    CanonicalDocument,
    DialogueTurn,
    GlossaryEntry,
    TurnKind,
)
from app.domain.ingestion.knowledge import (
    AliasKind,
    build_knowledge,
    build_location_edges,
    enrich_chunks,
    infer_prefix_aliases,
    location_chain,
    quests_in_place,
)
from app.domain.ingestion.pages import PageState, PageStatus
from app.domain.ingestion.units import Collection

NOW = datetime(2026, 11, 2, tzinfo=UTC)
METROPOLIS = "Category:Chronorift Metropolis Locations"


def _state(page_id: int, title: str, *categories: str, **changes) -> PageState:
    base = PageState(page_id, title, 1, NOW, family="lore", tier="A", categories=categories)
    return replace(base, **changes)


def _doc(page_id: int, title: str, *blocks: Block, family="lore", infobox=None, **changes):
    infoboxes = (infobox,) if infobox else ()
    return CanonicalDocument(page_id, title, 1, family, "v", blocks, infoboxes=infoboxes, **changes)


def _kb(documents, *states):
    return build_knowledge(documents, {s.page_id: s for s in states})


def _chunk(page_id: int, title: str, text: str) -> Chunk:
    return Chunk("e", "p", page_id, title, "lore", Collection.CANON, "prose", (), text, text, 1)


def test_location_edges_come_from_categories_and_skip_generic_and_deleted_pages() -> None:
    edges = build_location_edges(
        [
            _state(1, "Honami Central Park", METROPOLIS, "Category:Locations"),
            _state(2, "Stage", "Category:Event Locations"),
            _state(3, "Gone", "Category:X Locations", status=PageStatus.DELETED),
        ]
    )

    assert [(e.child, e.parent) for e in edges] == [
        ("Honami Central Park", "Chronorift Metropolis")
    ]


def test_location_chain_walks_up_and_survives_cycles() -> None:
    parents = {"Park": ["City"], "City": ["Nation"], "Nation": ["City"]}

    assert location_chain("Park", parents) == ["City", "Nation"]


def test_inferred_prefix_alias_keeps_its_evidence() -> None:
    edges = build_location_edges(
        [
            _state(1, "Honami Central Park", METROPOLIS),
            _state(2, "Honami Convention Center", METROPOLIS),
            _state(3, "The Plaza", METROPOLIS),
            _state(4, "The Mall", METROPOLIS),
        ]
    )

    [alias] = infer_prefix_aliases(edges)

    assert (alias.alias, alias.target, alias.kind) == (
        "Honami",
        "Chronorift Metropolis",
        AliasKind.INFERRED,
    )
    assert alias.evidence == ("Honami Central Park", "Honami Convention Center")


def test_single_page_prefix_is_not_an_alias() -> None:
    edges = build_location_edges([_state(1, "Honami Park", METROPOLIS)])

    assert infer_prefix_aliases(edges) == []


def test_aliases_keep_source_and_most_trusted_source_wins() -> None:
    state = _state(1, "Chisa", redirects=("Kuchiba Chisa",), aliases=("Old Chisa",))
    document = _doc(
        1,
        "Chisa",
        infobox={"realname": "Kuchiba Chisa", "alias": "Scissors\nThe Tailor"},
        other_names=(("Japanese", "千咲"),),
    )

    aliases = {a.alias: a for a in _kb([document], state).aliases}

    assert aliases["Kuchiba Chisa"].kind == AliasKind.REDIRECT
    assert aliases["Old Chisa"].kind == AliasKind.RENAME
    assert aliases["千咲"].kind == AliasKind.OTHER_LANGUAGE
    assert aliases["千咲"].evidence == ("Japanese",)
    assert (aliases["The Tailor"].kind, aliases["The Tailor"].confidence) == (
        AliasKind.INFOBOX,
        "medium",
    )


def test_nation_inference_order_is_recorded() -> None:
    documents = [
        _doc(1, "Hub", infobox={"nation": "Huanglong"}),
        _doc(2, "Shop", infobox={"location": "Jinzhou"}),
        _doc(3, "Plaza"),
        _doc(4, "Nowhere"),
    ]
    kb = _kb(
        documents,
        _state(1, "Hub"),
        _state(2, "Shop"),
        _state(3, "Plaza", "Category:Jinzhou Locations"),
        _state(4, "Nowhere"),
        _state(5, "Jinzhou", "Category:Huanglong Locations", family=None),
    )

    found = {e.title: (e.nation, e.nation_source) for e in kb.entities}

    assert found == {
        "Hub": ("Huanglong", "infobox"),
        "Shop": ("Huanglong", "location_graph"),
        "Plaza": ("Huanglong", "category"),
        "Nowhere": (None, None),
    }


def test_subpages_inherit_nation_and_version_from_their_parent() -> None:
    kb = _kb(
        [_doc(1, "Chisa", infobox={"nation": "Lahai-Roi"}), _doc(2, "Chisa/Backstory")],
        _state(1, "Chisa", "Category:Released in Version 3.0"),
        _state(2, "Chisa/Backstory"),
    )

    sub = next(e for e in kb.entities if e.title == "Chisa/Backstory")

    assert (sub.nation, sub.game_version, sub.version_source) == ("Lahai-Roi", "3.0", "propagated")
    assert sub.fields == {}


def test_quest_card_works_without_a_summary() -> None:
    turns = (
        DialogueTurn(TurnKind.NARRATION, "Head to the city"),
        DialogueTurn(TurnKind.LINE, "Hi", "Ciaccona"),
        DialogueTurn(TurnKind.LINE, "Hello", "Rover"),
        DialogueTurn(TurnKind.LINE, "Again", "Ciaccona"),
        DialogueTurn(TurnKind.NARRATION, "nested", depth=1),
        DialogueTurn(TurnKind.NARRATION, "Head to the city"),
    )
    document = _doc(
        1,
        "A Quest",
        Block(BlockKind.PROSE, ("Dialogue",), "A swordsman arrives.", title="Quest Description"),
        Block(BlockKind.LIST, ("Steps",), "- Go\n- Fight"),
        Block(BlockKind.DIALOGUE, ("Dialogue",), "x", turns=turns),
        family="main_quest",
        infobox={"chapter": "II", "prev": "B", "next": "C"},
    )

    [quest] = _kb([document], _state(1, "A Quest", family="main_quest")).quests

    assert quest.description == "A swordsman arrives."
    assert quest.summary is None
    assert quest.steps == ("Go", "Fight")
    assert quest.narration == ("Head to the city",)
    assert quest.speakers == ("Ciaccona", "Rover")
    assert quest.fields["next"] == "C"


def test_glossary_filters_ui_hints_and_picks_the_most_frequent_definition() -> None:
    documents = [
        _doc(1, "A", glossary=(GlossaryEntry("Tacet", "Short."), GlossaryEntry("Found you!", "x"))),
        _doc(2, "B", glossary=(GlossaryEntry("Tacet", "Short."), GlossaryEntry("???", "x"))),
        _doc(3, "C", glossary=(GlossaryEntry("Tacet", "A longer but rarer definition."),)),
    ]

    [term] = _kb(documents, _state(1, "A"), _state(2, "B"), _state(3, "C")).glossary

    assert (term.term, term.definition, term.pages) == ("Tacet", "Short.", 3)
    assert term.variants == ("A longer but rarer definition.",)


def test_chunks_get_own_entity_and_whole_word_mentions_through_trusted_aliases() -> None:
    kb = _kb(
        [
            _doc(1, "Chisa", infobox={"nation": "Lahai-Roi"}),
            _doc(2, "Black Shores"),
            _doc(3, "Black Shores Archipelago"),
            _doc(4, "Jinzhou"),
        ],
        _state(1, "Chisa", "Category:Released in Version 3.0", redirects=("Kuchiba Chisa",)),
        _state(2, "Black Shores"),
        _state(3, "Black Shores Archipelago"),
        _state(4, "Jinzhou"),
    )
    text = "Kuchiba Chisa left the Black Shores Archipelago. Jinzhouese food is not Jinzhou."

    [chunk] = enrich_chunks([_chunk(4, "Jinzhou", text)], kb)

    assert chunk.entities == ("Jinzhou", "Chisa", "Black Shores Archipelago")
    [own] = enrich_chunks([_chunk(1, "Chisa/Backstory", "Plain text.")], kb)
    assert (own.entities, own.nation, own.game_version) == (("Chisa",), "Lahai-Roi", "3.0")


def test_inferred_alias_prefers_the_district_over_its_nation_and_skips_real_places() -> None:
    nation = "Category:The Black Shores Locations"
    edges = build_location_edges(
        [
            _state(1, "Honami Central Park", METROPOLIS, nation),
            _state(2, "Honami Convention Center", METROPOLIS, nation),
            _state(3, "Chronorift Metropolis", nation),
            _state(4, "Jinzhou", "Category:Huanglong Locations"),
            _state(5, "Jinzhou Gate", "Category:Huanglong Locations"),
            _state(6, "Jinzhou Port", "Category:Huanglong Locations"),
            _state(7, "Tethys' Hub", "Category:Deep Locations"),
            _state(8, "Tethys' Gate", "Category:Deep Locations"),
        ]
    )

    found = {(a.alias, a.target) for a in infer_prefix_aliases(edges)}

    assert found == {("Honami", "Chronorift Metropolis"), ("Tethys", "Deep")}


def test_prefixes_used_as_ordinary_words_are_not_aliases() -> None:
    states = [
        _state(1, "Port Town", METROPOLIS, family=None),
        _state(2, "Port Plaza", METROPOLIS, family=None),
        _state(3, "Honami Park", METROPOLIS, family=None),
        _state(4, "Honami Hall", METROPOLIS, family=None),
    ]
    document = _doc(9, "Note", Block(BlockKind.PROSE, (), "The ship left the port. Honami stayed."))

    inferred = [a.alias for a in _kb([document], *states).aliases if a.kind == AliasKind.INFERRED]

    assert inferred == ["Honami"]


def test_dialogue_choices_are_not_glossary_terms() -> None:
    document = _doc(1, "A", glossary=(GlossaryEntry("(Comfort her.)", "x"),))

    assert _kb([document], _state(1, "A")).glossary == ()


def test_quests_are_found_through_the_alias_and_the_place_tree() -> None:
    states = [
        _state(1, "Honami Central Park", METROPOLIS, family=None),
        _state(2, "Honami Convention Center", METROPOLIS, family=None),
        _state(3, "Jinzhou City", "Category:Huanglong Locations", family=None),
        _state(4, "Linked Quest", family="main_quest"),
        _state(5, "Elsewhere Quest", family="main_quest"),
        _state(6, "Start Quest", family="main_quest"),
        _state(7, "Named Quest", family="main_quest"),
        _state(8, "Chatter Quest", family="main_quest"),
    ]
    chatter = (DialogueTurn(TurnKind.LINE, "I once visited Honami.", "A"),)
    documents = [
        _doc(
            4,
            "Linked Quest",
            family="main_quest",
            infobox={"chapter": "I"},
            links=("Honami Central Park", "Unrelated"),
        ),
        _doc(
            5,
            "Elsewhere Quest",
            family="main_quest",
            infobox={"chapter": "I"},
            links=("Jinzhou City",),
        ),
        _doc(
            6,
            "Start Quest",
            family="main_quest",
            infobox={"chapter": "I", "startLocation": "Chronorift Metropolis, The Black Shores"},
        ),
        _doc(
            7,
            "Named Quest",
            Block(BlockKind.PROSE, ("Summary",), "The fight moves through Honami at night."),
            family="main_quest",
            infobox={"chapter": "I"},
        ),
        _doc(
            8,
            "Chatter Quest",
            Block(BlockKind.DIALOGUE, ("Dialogue",), "x", turns=chatter),
            family="main_quest",
        ),
    ]
    kb = _kb(documents, *states)

    titles = {quest.title for quest in quests_in_place(kb, "honami")}

    assert titles == {"Linked Quest", "Start Quest", "Named Quest"}
    assert quests_in_place(kb, "Nowhere") == []
