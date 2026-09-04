"""RAG-05 regressions for cross-encoder ordering and bounded fallback."""

from __future__ import annotations

import pytest

from app.domain.interfaces.reranker import RerankerUnavailableError
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
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        self.calls.append((query, documents))
        return [-1.0, 2.0]


class _UnavailableCrossEncoder:
    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        del query, documents
        raise RerankerUnavailableError("not provisioned")


@pytest.mark.asyncio
async def test_cross_encoder_reranks_candidates_and_keeps_heuristics_as_features() -> None:
    cross_encoder = _CrossEncoder()
    retriever = LoreRetriever(
        vector_store=_VectorStore(), cross_encoder_reranker=cross_encoder
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
        metadata["reranker_fallback_reason"] == "unavailable" for _, _, metadata in results
    )
