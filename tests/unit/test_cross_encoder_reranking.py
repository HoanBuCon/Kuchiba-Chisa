"""RAG-05 regressions for cross-encoder ordering and bounded fallback."""

from __future__ import annotations

from contextlib import nullcontext

import pytest

from app.domain.interfaces.observability import (
    CounterSignal,
    GaugeSignal,
    HistogramSignal,
    TelemetryDimensions,
    TraceOperation,
)
from app.domain.interfaces.reranker import (
    RerankerDataBoundary,
    RerankerUnavailableError,
)
from app.domain.services.rag.retriever_lore import LoreRetriever


class _VectorStore:
    async def search_lore(self, **_: object) -> list[dict[str, object]]:
        return [
            {
                "id": "less-relevant",
                "score": 0.92,
                "payload": {
                    "text_content": "A partial answer with overlapping words.",
                    "access_scope": "public",
                },
            },
            {
                "id": "more-relevant",
                "score": 0.78,
                "payload": {
                    "text_content": "The complete grounded answer for this query.",
                    "access_scope": "public",
                },
            },
        ]


class _CrossEncoder:
    provider_name = "deterministic"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        self.calls.append((query, documents))
        return [-1.0, 2.0]


class _UnavailableCrossEncoder:
    provider_name = "deterministic"

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        del query, documents
        raise RerankerUnavailableError("not provisioned")


class _RemoteCrossEncoder:
    data_boundary = RerankerDataBoundary.REMOTE
    provider_name = "jina"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        self.calls.append((query, documents))
        return [0.5] * len(documents)


class _MixedScopeVectorStore:
    async def search_lore(self, **_: object) -> list[dict[str, object]]:
        return [
            {
                "id": "public-lore",
                "score": 0.92,
                "payload": {
                    "text_content": "Public approved lore.",
                    "access_scope": "public",
                },
            },
            {
                "id": "tenant-lore",
                "score": 0.91,
                "payload": {
                    "text_content": "Tenant private evidence must stay local.",
                    "access_scope": "tenant",
                },
            },
        ]


class _Span:
    def set_dimensions(self, dimensions: TelemetryDimensions) -> None:
        return None

    def set_status(self, status: str, failure_class: str | None = None) -> None:
        return None


class _Telemetry:
    def __init__(self) -> None:
        self.counters: list[tuple[CounterSignal, TelemetryDimensions, int]] = []
        self.histograms: list[tuple[HistogramSignal, float, TelemetryDimensions]] = []

    def span(self, operation: TraceOperation, dimensions: TelemetryDimensions):
        return nullcontext(_Span())

    def count(
        self,
        signal: CounterSignal,
        dimensions: TelemetryDimensions,
        amount: int = 1,
    ) -> None:
        self.counters.append((signal, dimensions, amount))

    def observe(
        self,
        signal: HistogramSignal,
        value_seconds: float,
        dimensions: TelemetryDimensions,
    ) -> None:
        self.histograms.append((signal, value_seconds, dimensions))

    def set_gauge(
        self,
        signal: GaugeSignal,
        value: int | float,
        dimensions: TelemetryDimensions,
    ) -> None:
        return None


@pytest.mark.asyncio
async def test_cross_encoder_reranks_candidates_and_keeps_heuristics_as_features() -> None:
    cross_encoder = _CrossEncoder()
    telemetry = _Telemetry()
    retriever = LoreRetriever(
        vector_store=_VectorStore(),
        cross_encoder_reranker=cross_encoder,
        telemetry=telemetry,
    )

    results = await retriever.retrieve_lore_parent_child(
        collection="character_lore",
        query_vector=[0.1],
        query_text="complete answer",
        top_k=2,
    )

    assert cross_encoder.calls == [
        (
            "complete answer",
            [
                "A partial answer with overlapping words.",
                "The complete grounded answer for this query.",
            ],
        )
    ]
    assert results[0][2]["point_id"] == "more-relevant"
    assert results[0][2]["reranker_mode"] == "cross_encoder"
    assert results[0][2]["reranker_fallback"] is False
    assert "hybrid_score" in results[0][2]
    assert results[0][2]["cross_encoder_score"] == 2.0
    assert any(
        signal is CounterSignal.RERANKER_CALLS
        for signal, _dimensions, _amount in telemetry.counters
    )
    assert any(
        signal is HistogramSignal.RAG_RETRIEVAL_DURATION
        for signal, _value, _dimensions in telemetry.histograms
    )
    assert any(
        signal is HistogramSignal.RAG_RETRIEVAL_SCORE
        for signal, _value, _dimensions in telemetry.histograms
    )
    assert any(
        signal is HistogramSignal.RAG_RERANKER_TOTAL_DURATION
        for signal, _value, _dimensions in telemetry.histograms
    )


@pytest.mark.asyncio
async def test_unavailable_cross_encoder_uses_observable_deterministic_fallback() -> None:
    retriever = LoreRetriever(
        vector_store=_VectorStore(), cross_encoder_reranker=_UnavailableCrossEncoder()
    )

    results = await retriever.retrieve_lore_parent_child(
        collection="character_lore",
        query_vector=[0.1],
        query_text="complete answer",
        top_k=2,
    )

    assert results[0][2]["point_id"] == "less-relevant"
    assert all(metadata["reranker_mode"] == "lexical_fallback" for _, _, metadata in results)
    assert all(metadata["reranker_fallback"] is True for _, _, metadata in results)
    assert all(
        metadata["reranker_fallback_reason"] == "provider_unavailable"
        for _, _, metadata in results
    )
    assert all(metadata["reranker_degraded"] is True for _, _, metadata in results)


@pytest.mark.asyncio
async def test_remote_reranker_never_receives_non_public_evidence() -> None:
    cross_encoder = _RemoteCrossEncoder()
    telemetry = _Telemetry()
    retriever = LoreRetriever(
        vector_store=_MixedScopeVectorStore(),
        cross_encoder_reranker=cross_encoder,
        telemetry=telemetry,
    )

    results = await retriever.retrieve_lore_parent_child(
        collection="character_lore",
        query_vector=[0.1],
        query_text="approved lore",
        top_k=2,
    )

    assert cross_encoder.calls == []
    assert {metadata["point_id"] for _, _, metadata in results} == {
        "public-lore",
        "tenant-lore",
    }
    assert all(metadata["reranker_mode"] == "lexical_fallback" for _, _, metadata in results)
    assert all(metadata["reranker_fallback"] is True for _, _, metadata in results)
    assert all(
        metadata["reranker_fallback_reason"] == "remote_policy"
        for _, _, metadata in results
    )
    assert any(
        signal is CounterSignal.RERANKER_PRIVACY_REJECTIONS
        and dimensions.failure_class == "privacy_rejected"
        for signal, dimensions, _amount in telemetry.counters
    )


@pytest.mark.asyncio
async def test_reranker_is_skipped_for_non_lore_or_non_factual_retrieval() -> None:
    cross_encoder = _RemoteCrossEncoder()
    retriever = LoreRetriever(vector_store=_VectorStore(), cross_encoder_reranker=cross_encoder)

    results = await retriever.retrieve_lore_parent_child(
        collection="character_lore",
        query_vector=[0.1],
        query_text="complete answer",
        top_k=2,
        enable_cross_encoder_rerank=False,
    )

    assert cross_encoder.calls == []
    assert all(
        metadata["reranker_fallback_reason"] == "not_applicable"
        for _, _, metadata in results
    )
    assert all(metadata["reranker_degraded"] is False for _, _, metadata in results)
