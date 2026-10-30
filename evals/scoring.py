"""Per-case scoring and per-category aggregation (SRS v2 §6.5)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from evals.dataset import Behavior, GoldenCase
from evals.metrics import (
    fact_recall,
    hit_at_k,
    normalize_text,
    percentile,
    reciprocal_rank,
    wilson_interval,
)
from evals.targets import Observation

HIT_K = 5
MRR_K = 10


class Status(StrEnum):
    SCORED = "scored"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    category: str
    status: Status
    correct: bool = False
    fact_recall: float | None = None
    abstained: bool | None = None
    hit_at_5: bool | None = None
    reciprocal_rank: float | None = None
    persona_ok: bool | None = None
    latency_ms: float | None = None
    answer: str = ""
    detail: str = ""


def detect_abstain(observation: Observation, markers: Sequence[str]) -> bool:
    """Prefer the target's own signal; otherwise fall back to the dataset's marker phrases."""
    if observation.abstained is not None:
        return observation.abstained
    answer = normalize_text(observation.answer)
    return any(normalize_text(marker) in answer for marker in markers)


def persona_ok(case: GoldenCase, answer: str) -> bool:
    if case.persona.require_senpai and "senpai" not in answer.lower():
        return False
    return not any(
        re.search(pattern, answer, re.IGNORECASE) for pattern in case.persona.forbidden_patterns
    )


def score_case(
    case: GoldenCase, observation: Observation, abstain_markers: Sequence[str]
) -> CaseResult:
    abstained = detect_abstain(observation, abstain_markers)
    if case.expected_behavior is Behavior.ABSTAIN:
        recall, correct = None, abstained
    else:
        recall = fact_recall(observation.answer, case.expected_facts)
        correct = not abstained and recall >= case.min_fact_recall
    relevant = {page.pageid for page in case.relevant_pages}
    has_ranking = bool(relevant and observation.evidence_pages)
    return CaseResult(
        case_id=case.id,
        category=case.category.value,
        status=Status.SCORED,
        correct=correct,
        fact_recall=recall,
        abstained=abstained,
        hit_at_5=hit_at_k(observation.evidence_pages, relevant, HIT_K) if has_ranking else None,
        reciprocal_rank=reciprocal_rank(observation.evidence_pages, relevant, MRR_K)
        if has_ranking
        else None,
        persona_ok=persona_ok(case, observation.answer),
        latency_ms=observation.latency_ms,
        answer=observation.answer,
    )


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rate(flags: Sequence[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


@dataclass(frozen=True)
class Summary:
    n_total: int
    n_scored: int
    n_skipped: int
    n_error: int
    accuracy: float | None
    accuracy_ci95: tuple[float, float]
    mean_fact_recall: float | None
    hit_at_5: float | None
    mrr_at_10: float | None
    abstain_precision: float | None
    false_abstain_rate: float | None
    persona_addressing: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None


def summarize(results: Sequence[CaseResult], expected_abstain: set[str]) -> Summary:
    """Aggregate scored results; skipped and errored cases are counted but never scored."""
    scored = [result for result in results if result.status is Status.SCORED]
    correct = sum(result.correct for result in scored)
    abstentions = [result for result in scored if result.abstained]
    answerable = [result for result in scored if result.case_id not in expected_abstain]
    latencies = [result.latency_ms for result in scored if result.latency_ms is not None]
    return Summary(
        n_total=len(results),
        n_scored=len(scored),
        n_skipped=sum(result.status is Status.SKIPPED for result in results),
        n_error=sum(result.status is Status.ERROR for result in results),
        accuracy=correct / len(scored) if scored else None,
        accuracy_ci95=wilson_interval(correct, len(scored)),
        mean_fact_recall=_mean([r.fact_recall for r in scored if r.fact_recall is not None]),
        hit_at_5=_rate([r.hit_at_5 for r in scored if r.hit_at_5 is not None]),
        mrr_at_10=_mean([r.reciprocal_rank for r in scored if r.reciprocal_rank is not None]),
        abstain_precision=_rate([r.case_id in expected_abstain for r in abstentions]),
        false_abstain_rate=_rate([bool(r.abstained) for r in answerable]),
        persona_addressing=_rate([r.persona_ok for r in scored if r.persona_ok is not None]),
        latency_p50_ms=percentile(latencies, 0.50),
        latency_p95_ms=percentile(latencies, 0.95),
    )
