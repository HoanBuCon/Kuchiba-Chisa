"""Render an evaluation report as JSON and a short Markdown summary."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from evals.runner import Report
from evals.scoring import Summary

_METRICS = (
    ("accuracy", "Accuracy"),
    ("mean_fact_recall", "Fact recall"),
    ("hit_at_5", "Hit@5"),
    ("mrr_at_10", "MRR@10"),
    ("abstain_precision", "Abstain precision"),
    ("false_abstain_rate", "False abstain"),
    ("persona_addressing", "Persona addressing"),
    ("latency_p95_ms", "Latency p95 (ms)"),
)


def _cell(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0f}" if value > 1 else f"{value:.2f}"


def _row(name: str, summary: Summary) -> str:
    low, high = summary.accuracy_ci95
    cells = [name, f"{summary.n_scored}/{summary.n_total}"]
    cells += [_cell(getattr(summary, key)) for key, _ in _METRICS]
    cells.append(f"{low:.2f}–{high:.2f}")
    return "| " + " | ".join(cells) + " |"


def render_markdown(report: Report) -> str:
    header = ["Category", "Scored"] + [label for _, label in _METRICS] + ["Accuracy 95% CI"]
    lines = [
        f"# Eval report: {report.target} on {report.dataset_version}",
        "",
        f"Evaluator `{report.evaluator_version}`, dataset approval `{report.dataset_approval}`, "
        f"snapshot `{report.source_snapshot}`, generated {report.generated_at}.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
        _row("**overall**", report.overall),
        *[_row(name, summary) for name, summary in report.by_category.items()],
        "",
        f"Manual review sample: {', '.join(report.manual_review) or 'none'}.",
        f"Unverified ground truth: {len(report.unverified_cases)} cases.",
        "",
    ]
    return "\n".join(lines)


def write_report(report: Report, directory: Path, stem: str) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = directory / f"{stem}.json", directory / f"{stem}.md"
    json_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path
