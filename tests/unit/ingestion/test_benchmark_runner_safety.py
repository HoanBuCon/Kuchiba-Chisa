"""Regression coverage for fail-closed ingestion quality benchmarking."""

from __future__ import annotations

import pytest

from app.infrastructure.ingestion.quality.benchmark_runner import BenchmarkRunner


@pytest.mark.asyncio
async def test_unavailable_retriever_cannot_fabricate_a_passing_quality_result() -> None:
    async def unavailable_retriever(_: str, *, top_k: int) -> list[object]:
        raise RuntimeError("staging vector store unavailable")

    result = await BenchmarkRunner(top_k=5).run(unavailable_retriever)

    assert result.total_cases == 50
    assert result.passed_cases == 0
    assert result.quality_gate_passed is False
    assert not hasattr(BenchmarkRunner, "_run_mock_benchmark")
