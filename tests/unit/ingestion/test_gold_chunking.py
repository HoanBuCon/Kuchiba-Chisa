"""Units, owner-based dedup and token-bounded chunking (ING-004, ING-011, E1)."""

from app.domain.ingestion.chunking import Chunker, ChunkPolicy, evidence_id
from app.domain.ingestion.dedup import OwnerPolicy, deduplicate, drop_duplicate_bodies, fingerprint
from app.domain.ingestion.documents import (
    Block,
    BlockKind,
    CanonicalDocument,
    DialogueTurn,
    TurnKind,
)
from app.domain.ingestion.units import Collection, Unit, document_units, profile_unit

OWNERS = OwnerPolicy(("resonator_backstory", "resonator", "terminology"), min_chars=10)
POLICY = ChunkPolicy(
    target_tokens=30, max_tokens=40, min_tokens=10, overlap_turns=1, passage_prefix=""
)


def _count(text: str) -> int:
    return len(text.split())


def _doc(
    *blocks: Block, page_id=1, title="T", family="resonator", infoboxes=()
) -> CanonicalDocument:
    return CanonicalDocument(page_id, title, 1, family, "v", tuple(blocks), infoboxes=infoboxes)


def _words(count: int, stem: str = "w") -> str:
    return " ".join(f"{stem}{index}" for index in range(count))


def _unit(text, page_id=1, family="resonator", section=("S",), group="g", **changes) -> Unit:
    return Unit(page_id, "T", family, Collection.CANON, "prose", section, group, text, **changes)


def test_prose_splits_by_paragraph_and_lists_by_line() -> None:
    units = document_units(
        _doc(
            Block(BlockKind.PROSE, ("A",), "one\n\ntwo"),
            Block(BlockKind.LIST, ("A",), "- x\n- y"),
        )
    )

    assert [u.text for u in units] == ["one", "two", "- x", "- y"]
    assert len({u.group for u in units}) == 1


def test_punctuation_only_paragraphs_are_not_units() -> None:
    assert [u.text for u in document_units(_doc(Block(BlockKind.PROSE, (), "...\n\nreal")))] == [
        "real"
    ]


def test_story_title_and_variant_lead_the_first_unit_only() -> None:
    block = Block(BlockKind.STORY, ("V",), "one\n\ntwo", title="Thoughts", variant="Lv. 1")

    assert [u.text for u in document_units(_doc(block))] == ["Thoughts (Lv. 1)\none", "two"]


def test_tab_variant_without_title_prefixes_the_text() -> None:
    block = Block(BlockKind.FACTS, ("V",), "Greeting: Hi", variant="Male")

    assert document_units(_doc(block))[0].text == "(Male) Greeting: Hi"


def test_dialogue_scenes_start_at_top_level_narration() -> None:
    turns = (
        DialogueTurn(TurnKind.NARRATION, "Go"),
        DialogueTurn(TurnKind.LINE, "hi", "A"),
        DialogueTurn(TurnKind.NARRATION, "nested", depth=1),
        DialogueTurn(TurnKind.NARRATION, "Next"),
    )
    block = Block(BlockKind.DIALOGUE, ("D",), "x", turns=turns)

    units = document_units(_doc(block))

    assert [u.scene for u in units] == [1, 1, 1, 2]
    assert {u.collection for u in units} == {Collection.DIALOGUE}
    assert all(u.is_turn for u in units)


def test_profile_card_needs_enough_fields_and_names_the_page() -> None:
    thin = _doc(infoboxes=({"type": "Lore"},))
    full = _doc(title="Chisa", infoboxes=({"age": "18", "class": "Mutant", "ally": "A\nB"},))

    assert profile_unit(thin) is None
    assert profile_unit(full).text == "Chisa\nage: 18\nclass: Mutant\nally: A, B"


def test_owner_family_keeps_the_shared_passage() -> None:
    shared = "A long passage shared by two pages."
    result = deduplicate(
        [
            _unit(shared, page_id=1, family="terminology"),
            _unit(shared, page_id=2, family="resonator_backstory"),
        ],
        OWNERS,
    )

    assert [u.page_id for u in result.units] == [2]
    assert result.duplicate_of == {fingerprint(shared): 2}


def test_case_and_spacing_do_not_hide_a_duplicate() -> None:
    result = deduplicate(
        [_unit("Shared   passage text", page_id=1), _unit("shared passage TEXT", page_id=2)], OWNERS
    )

    assert [u.page_id for u in result.units] == [1]


def test_short_lines_and_profiles_are_never_unit_deduped() -> None:
    units = [_unit("Hello.", page_id=1), _unit("Hello.", page_id=2)]

    assert len(deduplicate(units, OWNERS).units) == 2


def test_repeated_passage_inside_one_page_is_kept_once() -> None:
    assert (
        len(deduplicate([_unit("Repeated passage"), _unit("Repeated passage")], OWNERS).units) == 1
    )


def test_dialogue_dedups_whole_scenes() -> None:
    def scene(page_id, family):
        return [
            _unit("Hello there", page_id=page_id, family=family, is_turn=True, scene=1),
            _unit("Short", page_id=page_id, family=family, is_turn=True, scene=1),
        ]

    result = deduplicate([*scene(1, "terminology"), *scene(2, "resonator_backstory")], OWNERS)

    assert {u.page_id for u in result.units} == {2}
    assert len(result.units) == 2


def test_different_scenes_with_a_shared_line_both_stay() -> None:
    units = [
        _unit("Shared line here", page_id=1, is_turn=True, scene=1),
        _unit("Shared line here", page_id=2, is_turn=True, scene=1),
        _unit("Only on page two", page_id=2, is_turn=True, scene=1),
    ]

    assert len(deduplicate(units, OWNERS).units) == 3


def test_units_merge_up_to_the_target_and_never_across_groups() -> None:
    chunks = Chunker(_count, POLICY).chunk(
        [
            _unit(_words(12, "a")),
            _unit(_words(12, "b")),
            _unit(_words(12, "c")),
            _unit(_words(12, "d"), group="h"),
        ]
    )

    assert [c.text.count("\n") for c in chunks] == [1, 0, 0]
    assert all(c.tokens <= POLICY.max_tokens for c in chunks)


def test_small_tail_joins_its_predecessor_when_it_fits() -> None:
    chunks = Chunker(_count, POLICY).chunk([_unit(_words(29, "a")), _unit(_words(3, "b"))])

    assert len(chunks) == 1


def test_long_unit_splits_on_sentences_within_the_limit() -> None:
    text = " ".join(f"{_words(12, f's{i}')}." for i in range(8))

    chunks = Chunker(_count, POLICY).chunk([_unit(text)])

    assert len(chunks) > 1
    assert all(c.tokens <= POLICY.max_tokens for c in chunks)
    assert " ".join(c.text.replace("\n", " ") for c in chunks) == text


def test_sentence_longer_than_the_limit_splits_on_words() -> None:
    chunks = Chunker(_count, POLICY).chunk([_unit(_words(100))])

    assert all(c.tokens <= POLICY.max_tokens for c in chunks)
    assert " ".join(c.text.replace("\n", " ") for c in chunks) == _words(100)


def test_dialogue_windows_overlap_by_one_turn_inside_a_scene() -> None:
    turns = [_unit(f"t{i} {_words(9, 'x')}", is_turn=True, scene=1) for i in range(5)]

    chunks = Chunker(_count, POLICY).chunk(turns)

    assert len(chunks) == 4
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert later.text.splitlines()[0] == earlier.text.splitlines()[-1]


def test_small_scenes_merge_but_big_ones_cut_cleanly_without_overlap() -> None:
    small = [
        _unit("(Cutscene plays)", is_turn=True, scene=1),
        _unit("A: hi", is_turn=True, scene=2),
    ]
    big = [
        _unit(_words(12, "a"), is_turn=True, scene=1),
        _unit(_words(12, "b"), is_turn=True, scene=2),
    ]

    assert len(Chunker(_count, POLICY).chunk(small)) == 1
    # A second chunk would be below the minimum only if merged; both scenes stand alone here.
    cut = Chunker(_count, POLICY).chunk(big)
    assert [c.text for c in cut] == [_words(12, "a"), _words(12, "b")]


def test_embedding_text_carries_prefix_title_and_section() -> None:
    policy = ChunkPolicy(target_tokens=30, max_tokens=40, min_tokens=1, passage_prefix="passage: ")

    [chunk] = Chunker(_count, policy).chunk([_unit("Body", section=("A", "B"))])

    assert chunk.embedding_text == "passage: T\nA > B\nBody"
    assert chunk.tokens == _count(chunk.embedding_text)


def test_evidence_ids_are_stable_and_identical_text_gets_a_suffix() -> None:
    first, second = Chunker(_count, POLICY).chunk([_unit(_words(35)), _unit(_words(35), group="h")])

    assert first.evidence_id == evidence_id(1, _words(35))
    assert second.evidence_id == f"{first.evidence_id}:2"
    assert first.point_id != second.point_id
    again = Chunker(_count, POLICY).chunk([_unit(_words(35))])[0]
    assert again.point_id == first.point_id


def test_chunk_level_pass_removes_short_exact_duplicates_keeping_the_owner() -> None:
    chunks = Chunker(_count, POLICY).chunk(
        [
            _unit("(Cutscene)", page_id=1, family="terminology"),
            _unit("(Cutscene)", page_id=2, family="resonator"),
        ]
    )

    assert [c.page_id for c in drop_duplicate_bodies(chunks, OWNERS)] == [2]
