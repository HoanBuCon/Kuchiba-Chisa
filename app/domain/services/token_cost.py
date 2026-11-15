"""Estimated dollar cost of a turn from its token usage (COST-001)."""

from __future__ import annotations

from dataclasses import dataclass

TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class TokenPrices:
    """Dollars per million tokens; zero until the composition root passes the configured table."""

    input_per_million: float = 0.0
    cached_input_per_million: float = 0.0
    output_per_million: float = 0.0


def estimate_cost_usd(
    prices: TokenPrices, input_tokens: int, cached_input_tokens: int, output_tokens: int
) -> float:
    """Cached tokens are part of the input count and billed at the cheaper cache-hit rate."""
    uncached = max(0, input_tokens - cached_input_tokens)
    total = (
        uncached * prices.input_per_million
        + cached_input_tokens * prices.cached_input_per_million
        + output_tokens * prices.output_per_million
    )
    return total / TOKENS_PER_MILLION
