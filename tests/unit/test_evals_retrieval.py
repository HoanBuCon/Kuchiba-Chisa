"""Retrieval evaluation: page-level ranking, cross-collection fusion and grouped metrics."""

from types import SimpleNamespace

from evals.retrieval import CaseOutcome, fuse_ranked, ranked_pages, summarize


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
