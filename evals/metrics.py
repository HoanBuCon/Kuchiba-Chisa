"""Deterministic ranking, proportion and text-matching metrics for evaluation reports."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence

WILSON_Z_95 = 1.959964


def normalize_text(text: str) -> str:
    """Lowercase, strip Vietnamese diacritics and collapse whitespace so variants compare equal."""
    decomposed = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", stripped).strip()


def fact_recall(answer: str, facts: Sequence[Sequence[str]]) -> float:
    """Share of facts with at least one surface form present in the answer."""
    if not facts:
        return 0.0
    haystack = normalize_text(answer)
    matched = sum(1 for forms in facts if any(normalize_text(form) in haystack for form in forms))
    return matched / len(facts)


def hit_at_k(ranked: Sequence[int], relevant: set[int], k: int) -> bool:
    return any(item in relevant for item in ranked[:k])


def reciprocal_rank(ranked: Sequence[int], relevant: set[int], k: int) -> float:
    for position, item in enumerate(ranked[:k], start=1):
        if item in relevant:
            return 1.0 / position
    return 0.0


def wilson_interval(successes: int, total: int, z: float = WILSON_Z_95) -> tuple[float, float]:
    """Wilson score interval; stays sensible for the small samples a golden set has."""
    if total == 0:
        return (0.0, 0.0)
    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    margin = (
        z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Nearest-rank percentile, or None when there is nothing to rank."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]
