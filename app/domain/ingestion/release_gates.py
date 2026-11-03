"""Deterministic data gate for a corpus release (ING-008, design S8); no model or LLM involved."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

REQUIRED_QUALITY = (
    "chunks",
    "pages",
    "over_limit",
    "duplicate_bodies",
    "uncovered_units",
    "pages_quarantined",
    "pages_safety_blocked",
)


@dataclass(frozen=True)
class DataGatePolicy:
    max_quarantined_ratio: float = 0.02
    # Within the routine envelope; a larger swing holds the release for a person to explain.
    max_chunk_change_ratio: float = 0.10
    max_knowledge_change_ratio: float = 0.05


@dataclass(frozen=True)
class RetrievalGatePolicy:
    min_hit_at_5: float = 0.90
    min_mrr_at_10: float = 0.80
    min_cases: int = 100
    max_drop_from_active: float = 0.02
    canary_case_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GateReport:
    checks: tuple[GateCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if not check.passed)


def _at_most(name: str, value: float, limit: float) -> GateCheck:
    return GateCheck(name, value <= limit, f"{value:g} (limit {limit:g})")


def _change_checks(
    name: str, current: Mapping[str, int], previous: Mapping[str, int], limit: float
) -> list[GateCheck]:
    checks = []
    for key, before in previous.items():
        after = current.get(key, 0)
        change = abs(after - before) / before if before else float(after > 0)
        checks.append(
            GateCheck(f"{name}:{key}", change <= limit, f"{before} -> {after} (limit ±{limit:.0%})")
        )
    return checks


def evaluate_data_gate(
    manifest: Mapping[str, Any],
    previous: Mapping[str, Any] | None = None,
    policy: DataGatePolicy | None = None,
) -> GateReport:
    """`previous` is the active release; the first release has nothing to compare against."""
    policy = policy or DataGatePolicy()
    quality = manifest["quality"]
    counts = manifest["counts"]
    # A manifest that never measured a check must not pass it by default.
    missing = [name for name in REQUIRED_QUALITY if name not in quality]
    if missing:
        return GateReport((GateCheck("manifest_complete", False, f"missing {missing}"),))
    quarantined = quality["pages_quarantined"] / max(quality["pages"], 1)
    checks = [
        _at_most("chunks_over_token_limit", quality["over_limit"], 0),
        _at_most("duplicate_chunk_bodies", quality["duplicate_bodies"], 0),
        _at_most("uncovered_units", quality["uncovered_units"], 0),
        _at_most("pages_quarantined_ratio", round(quarantined, 4), policy.max_quarantined_ratio),
        _at_most("unresolved_safety_pages", quality["pages_safety_blocked"], 0),
        GateCheck("corpus_not_empty", quality["chunks"] > 0, f"{quality['chunks']} chunks"),
    ]
    checks.extend(
        GateCheck(f"collection_not_empty:{name}", count > 0, str(count))
        for name, count in counts["collection"].items()
    )
    if previous is not None:
        checks.extend(
            _change_checks(
                "chunk_change",
                {"chunks": quality["chunks"]},
                {"chunks": previous["quality"]["chunks"]},
                policy.max_chunk_change_ratio,
            )
        )
        checks.extend(
            _change_checks(
                "knowledge_change",
                counts.get("knowledge", {}),
                previous["counts"].get("knowledge", {}),
                policy.max_knowledge_change_ratio,
            )
        )
    return GateReport(tuple(checks))


def _at_least(name: str, value: float, limit: float) -> GateCheck:
    return GateCheck(name, value >= limit, f"{value:g} (minimum {limit:g})")


def _no_drop_checks(
    overall: Mapping[str, Any], active: Mapping[str, Any], limit: float
) -> list[GateCheck]:
    hit, hit_before = overall["hit_at_5"], active["hit_at_5"]
    # A drop inside the confidence interval is sampling noise, not a regression.
    hit_dropped = hit_before - hit > limit and overall["hit_at_5_ci95"][1] < hit_before
    mrr, mrr_before = overall["mrr_at_10"], active["mrr_at_10"]
    return [
        GateCheck("hit_at_5_vs_active", not hit_dropped, f"{hit_before} -> {hit}"),
        GateCheck("mrr_at_10_vs_active", mrr_before - mrr <= limit, f"{mrr_before} -> {mrr}"),
    ]


def evaluate_retrieval_gate(
    summary: Mapping[str, Any],
    hit_case_ids: Collection[str],
    active: Mapping[str, Any] | None = None,
    policy: RetrievalGatePolicy | None = None,
) -> GateReport:
    """`summary` is one mode of the retrieval report; `active` the live release's, if any."""
    policy = policy or RetrievalGatePolicy()
    overall = summary["overall"]
    missed = [case for case in policy.canary_case_ids if case not in hit_case_ids]
    checks = [
        # Unreviewed labels can measure progress but cannot approve a release.
        _at_least("golden_verified_cases", summary["verified_cases"], policy.min_cases),
        _at_least("hit_at_5", overall["hit_at_5"], policy.min_hit_at_5),
        _at_least("mrr_at_10", overall["mrr_at_10"], policy.min_mrr_at_10),
        GateCheck("canary_configured", bool(policy.canary_case_ids), "canary list"),
        GateCheck("canary", not missed, f"missed {missed}"),
    ]
    if active is not None:
        checks.extend(_no_drop_checks(overall, active["overall"], policy.max_drop_from_active))
    return GateReport(tuple(checks))
