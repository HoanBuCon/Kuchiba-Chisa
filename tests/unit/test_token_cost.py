"""Estimated turn cost from token usage and a configured price table (COST-001)."""

import pytest

from app.domain.services.token_cost import TokenPrices, estimate_cost_usd

PRICES = TokenPrices(
    input_per_million=0.28, cached_input_per_million=0.028, output_per_million=0.42
)


def test_cached_tokens_are_billed_at_the_cache_rate_not_twice() -> None:
    cost = estimate_cost_usd(PRICES, 1_000_000, 750_000, 1_000_000)

    assert cost == pytest.approx(0.25 * 0.28 + 0.75 * 0.028 + 0.42)


def test_no_usage_costs_nothing() -> None:
    assert estimate_cost_usd(PRICES, 0, 0, 0) == 0.0


def test_default_prices_are_zero() -> None:
    assert estimate_cost_usd(TokenPrices(), 500, 100, 50) == 0.0


def test_cache_hits_above_the_input_count_never_make_the_cost_negative() -> None:
    assert estimate_cost_usd(PRICES, 10, 20, 0) == pytest.approx(20 * 0.028 / 1_000_000)
