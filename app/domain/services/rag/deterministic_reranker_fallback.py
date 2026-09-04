"""Deterministic fallback for unavailable or disallowed cross-encoder reranking."""

from __future__ import annotations

from typing import Any


class DeterministicRerankerFallback:
    """Preserve calibrated dense+sparse/heuristic ordering with observable state.

    The incoming candidates are already ordered by the calibrated hybrid score.
    This fallback intentionally never invokes a model or changes evidence content.
    """

    def apply(
        self,
        scored_candidates: list[tuple[dict[str, Any], float]],
        *,
        reason: str,
        degraded: bool = True,
    ) -> list[tuple[dict[str, Any], float]]:
        for candidate, _ in scored_candidates:
            scoring_meta = candidate["scoring_meta"]
            scoring_meta["reranker_mode"] = "lexical_fallback"
            scoring_meta["reranker_fallback"] = True
            scoring_meta["reranker_fallback_reason"] = reason
            scoring_meta["reranker_degraded"] = degraded
        return scored_candidates
