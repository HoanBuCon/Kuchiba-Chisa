"""Eval metrics are deterministic and tolerant of Vietnamese spelling variants."""

import pytest

from evals.metrics import (
    fact_recall,
    hit_at_k,
    normalize_text,
    percentile,
    reciprocal_rank,
    wilson_interval,
)


def test_normalize_text_folds_case_diacritics_and_whitespace() -> None:
    assert normalize_text("  Cà Phê   MUỐI  Đà Lạt ") == "ca phe muoi da lat"


def test_fact_recall_counts_each_fact_once_with_any_surface_form() -> None:
    answer = "Chisa dùng đại kiếm và thuộc hệ Havoc."
    assert fact_recall(
        answer, [["havoc"], ["broadblade", "dai kiem"], ["ashinohara"]]
    ) == pytest.approx(2 / 3)


def test_fact_recall_without_facts_is_zero() -> None:
    assert fact_recall("anything", []) == 0.0


def test_ranking_metrics_use_the_first_relevant_position() -> None:
    ranked = [10, 20, 30]
    assert hit_at_k(ranked, {30}, 3)
    assert not hit_at_k(ranked, {30}, 2)
    assert reciprocal_rank(ranked, {20, 30}, 10) == 0.5
    assert reciprocal_rank(ranked, {99}, 10) == 0.0


def test_wilson_interval_brackets_the_proportion() -> None:
    low, high = wilson_interval(9, 10)
    assert low < 0.9 < high
    assert wilson_interval(0, 0) == (0.0, 0.0)
    assert wilson_interval(10, 10)[1] == pytest.approx(1.0)


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([5.0, 1.0, 3.0, 2.0], 0.5) == 2.0
    assert percentile([5.0, 1.0, 3.0, 2.0], 0.95) == 5.0
    assert percentile([], 0.5) is None
