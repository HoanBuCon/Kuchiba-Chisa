"""Retrieval evaluation: page-level ranking, cross-collection fusion and grouped metrics."""

from types import SimpleNamespace

import pytest

from evals.dataset import Category, GoldenCase, Language, PageRef, Turn, load_golden_set
from evals.retrieval import (
    GOLDEN_PATH,
    TRANSLATIONS_PATH,
    CaseOutcome,
    fuse_ranked,
    load_translations,
    ranked_pages,
    rerank_document,
    rerank_order,
    search_query,
    summarize,
)
from evals.translate_queries import needs_translation


def _point(point_id: str, page_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=point_id, payload={"page_id": page_id})


def _outcome(category: str, language: str, hit: bool, reciprocal: float) -> CaseOutcome:
    return CaseOutcome("c-001", category, language, "q", (1,), (1,), hit, reciprocal)


def test_chunks_of_one_page_count_once_in_rank_order() -> None:
    points = [_point("a", 7), _point("b", 7), _point("c", 3), _point("d", 7), _point("e", 9)]

    assert ranked_pages(points) == [7, 3, 9]


def test_fusion_rewards_points_found_by_several_lists_and_ignores_raw_scores() -> None:
    first = [_point("a", 1), _point("b", 2)]
    second = [_point("c", 3), _point("b", 2)]

    assert [point.id for point in fuse_ranked([first, second])] == ["b", "a", "c"]


def test_summary_groups_by_category_and_language_with_confidence_interval() -> None:
    summary = summarize(
        [
            _outcome("lore_single_hop", "vi", True, 1.0),
            _outcome("lore_single_hop", "en", False, 0.0),
            _outcome("multi_hop", "vi", True, 0.5),
        ]
    )

    assert summary["overall"]["cases"] == 3
    assert summary["overall"]["hit_at_5"] == 0.667
    assert summary["overall"]["mrr_at_10"] == 0.5
    low, high = summary["overall"]["hit_at_5_ci95"]
    assert low < 0.667 < high
    assert summary["by_category"]["lore_single_hop"]["hit_at_5"] == 0.5
    assert summary["by_language"]["vi"]["cases"] == 2


def test_empty_evaluation_reports_no_rates() -> None:
    assert summarize([])["overall"]["hit_at_5"] is None


def test_rerank_reorders_the_head_and_keeps_the_tail() -> None:
    points = [_point("a", 1), _point("b", 2), _point("c", 3), _point("d", 4)]

    assert [p.id for p in rerank_order(points, [0.1, 0.9, 0.5])] == ["b", "c", "a", "d"]


def test_rerank_document_carries_title_and_section() -> None:
    point = SimpleNamespace(
        payload={"title": "Chisa", "section_path": ["Story", "Early"], "text": "Body"}
    )

    assert rerank_document(point) == "Chisa\nStory > Early\nBody"


def _case(language: Language) -> GoldenCase:
    return GoldenCase(
        id="lore-001",
        category=Category.LORE_SINGLE_HOP,
        language=language,
        turns=(Turn(message="q"),),
        expected_facts=(("a",),),
    )


def test_english_question_searches_as_asked() -> None:
    assert search_query(_case(Language.EN), "Where?", {}) == "Where?"


def test_other_languages_search_with_the_frozen_translation() -> None:
    assert search_query(_case(Language.VI), "Ở đâu?", {"lore-001": "Where?"}) == "Where?"


def test_missing_translation_stops_the_run() -> None:
    with pytest.raises(SystemExit):
        search_query(_case(Language.VI), "Ở đâu?", {})


def test_translation_is_needed_only_for_retrieval_cases_not_yet_stored() -> None:
    page = {"relevant_pages": (PageRef(title="P", pageid=1),)}
    case = _case(Language.VI).model_copy(update=page)

    assert needs_translation(case, {})
    assert not needs_translation(case, {"lore-001": "Where?"})
    assert not needs_translation(_case(Language.VI), {})
    assert not needs_translation(_case(Language.EN).model_copy(update=page), {})


def test_every_golden_retrieval_case_has_a_frozen_translation() -> None:
    stored = load_translations(TRANSLATIONS_PATH)

    assert [c.id for c in load_golden_set(GOLDEN_PATH).cases if needs_translation(c, stored)] == []
