"""Run a golden set against a target and build a versioned, reproducible report."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from evals.dataset import Behavior, GoldenCase, GoldenSet
from evals.scoring import CaseResult, Status, Summary, score_case, summarize
from evals.targets import EvalTarget, TargetError, UnsupportedCaseError

EVALUATOR_VERSION = "evals-1.0.0"
MANUAL_REVIEW_FRACTION = 0.2


@dataclass(frozen=True)
class Report:
    evaluator_version: str
    dataset_version: str
    dataset_approval: str
    source_snapshot: str
    target: str
    generated_at: str
    overall: Summary
    by_category: dict[str, Summary]
    unverified_cases: list[str]
    manual_review: list[str]
    cases: list[CaseResult]


async def run_case(
    target: EvalTarget, case: GoldenCase, abstain_markers: Sequence[str]
) -> CaseResult:
    try:
        observation = await target.answer(case)
    except UnsupportedCaseError as reason:
        return CaseResult(case.id, case.category.value, Status.SKIPPED, detail=str(reason))
    except TargetError as error:
        return CaseResult(case.id, case.category.value, Status.ERROR, detail=str(error))
    return score_case(case, observation, abstain_markers)


def manual_review_sample(
    case_ids: Sequence[str], fraction: float = MANUAL_REVIEW_FRACTION
) -> list[str]:
    """Stable pseudo-random subset for human spot checks; the same ids every run (SRS §6.5)."""
    size = max(1, round(len(case_ids) * fraction)) if case_ids else 0
    ranked = sorted(case_ids, key=lambda case_id: hashlib.sha256(case_id.encode()).hexdigest())
    return sorted(ranked[:size])


async def run_golden_set(
    target: EvalTarget, golden: GoldenSet, cases: Sequence[GoldenCase]
) -> Report:
    # Sequential on purpose: real-LLM runs are budgeted and must not trip provider rate limits.
    results = [await run_case(target, case, golden.abstain_markers) for case in cases]
    expected_abstain = {case.id for case in cases if case.expected_behavior is Behavior.ABSTAIN}
    categories = sorted({result.category for result in results})
    return Report(
        evaluator_version=EVALUATOR_VERSION,
        dataset_version=golden.dataset_version,
        dataset_approval=golden.approval.status,
        source_snapshot=golden.source_snapshot,
        target=target.name,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        overall=summarize(results, expected_abstain),
        by_category={
            category: summarize([r for r in results if r.category == category], expected_abstain)
            for category in categories
        },
        unverified_cases=sorted(case.id for case in cases if not case.verified),
        manual_review=manual_review_sample(
            [r.case_id for r in results if r.status is Status.SCORED]
        ),
        cases=results,
    )
