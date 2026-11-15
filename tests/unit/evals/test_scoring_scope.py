"""QUAL-004 scope: abstain precision and false abstain exclude multi-hop (ADV-007, QUAL-007)."""

from __future__ import annotations

from evals.metrics import wilson_interval
from evals.report import render_markdown
from evals.runner import Report
from evals.scoring import CaseResult, Status, summarize


def _result(case_id: str, category: str, abstained: bool) -> CaseResult:
    return CaseResult(case_id, category, Status.SCORED, abstained=abstained)


RESULTS = [
    _result("oos-001", "out_of_scope", True),
    _result("oos-002", "out_of_scope", True),
    _result("lore-001", "lore_single_hop", False),
    _result("lore-002", "lore_single_hop", True),
    _result("multi-001", "multi_hop", True),
    _result("multi-002", "multi_hop", True),
    _result("multi-003", "multi_hop", False),
]
EXPECTED_ABSTAIN = {"oos-001", "oos-002"}


def test_multi_hop_abstentions_do_not_affect_precision_or_false_abstain() -> None:
    summary = summarize(RESULTS, EXPECTED_ABSTAIN)
    assert summary.abstain_precision == 2 / 3
    assert summary.false_abstain_rate == 0.5
    assert summary.multi_hop_abstain_rate == 2 / 3
    assert summary.abstain_precision_ci95 == wilson_interval(2, 3)


def test_multi_hop_category_row_reports_only_its_abstain_rate() -> None:
    summary = summarize([r for r in RESULTS if r.category == "multi_hop"], EXPECTED_ABSTAIN)
    assert summary.abstain_precision is None
    assert summary.false_abstain_rate is None
    assert summary.multi_hop_abstain_rate == 2 / 3


def test_multi_hop_abstain_rate_is_none_without_multi_hop_cases() -> None:
    assert summarize(RESULTS[:4], EXPECTED_ABSTAIN).multi_hop_abstain_rate is None


def test_report_shows_multi_hop_column_and_precision_interval() -> None:
    overall = summarize(RESULTS, EXPECTED_ABSTAIN)
    report = Report(
        evaluator_version="e",
        dataset_version="d",
        dataset_approval="a",
        source_snapshot="s",
        target="t",
        generated_at="now",
        overall=overall,
        by_category={},
        by_split={},
        unverified_cases=[],
        manual_review=[],
        cases=[],
    )
    markdown = render_markdown(report)
    low, high = overall.abstain_precision_ci95
    assert "Multi-hop abstain" in markdown
    assert "Abstain precision 95% CI" in markdown
    assert f"{low:.2f}–{high:.2f}" in markdown
