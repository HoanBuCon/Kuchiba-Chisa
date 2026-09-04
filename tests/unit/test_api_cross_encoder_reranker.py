"""RAG-05 contract tests for remote reranker adapters without provider calls."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.domain.interfaces.reranker import RerankerDataBoundary, RerankerUnavailableError
from app.infrastructure.rag.api_cross_encoder_reranker import (
    ApiCrossEncoderReranker,
    ApiRerankerProvider,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "response_key", "expected_url"),
    [
        (ApiRerankerProvider.VOYAGE, "data", "https://api.voyageai.com/v1/rerank"),
        (ApiRerankerProvider.JINA, "results", "https://api.jina.ai/v1/rerank"),
        (ApiRerankerProvider.COHERE, "results", "https://api.cohere.com/v2/rerank"),
    ],
)
async def test_remote_adapter_reconstructs_scores_in_input_order(
    provider: ApiRerankerProvider,
    response_key: str,
    expected_url: str,
) -> None:
    received: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["url"] = str(request.url)
        received["headers"] = dict(request.headers)
        received["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                response_key: [
                    {"index": 1, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.14},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        reranker = ApiCrossEncoderReranker(
            provider=provider,
            api_key="test-key",
            model_name="test-model",
            timeout_seconds=1.0,
            max_documents=15,
            http_client=client,
        )
        scores = await reranker.rerank("query", ["first", "second"])

    assert reranker.data_boundary is RerankerDataBoundary.REMOTE
    assert scores == [0.14, 0.91]
    assert received["url"] == expected_url
    assert received["headers"]["authorization"] == "Bearer test-key"
    assert received["json"]["top_n"] == 2
    assert ("return_documents" in received["json"]) is (
        provider is ApiRerankerProvider.JINA
    )


@pytest.mark.asyncio
async def test_remote_adapter_rejects_partial_or_duplicate_scores() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.14},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        reranker = ApiCrossEncoderReranker(
            provider=ApiRerankerProvider.JINA,
            api_key="test-key",
            model_name="test-model",
            timeout_seconds=1.0,
            max_documents=15,
            http_client=client,
        )
        with pytest.raises(RerankerUnavailableError, match="invalid score"):
            await reranker.rerank("query", ["first", "second"])


@pytest.mark.asyncio
async def test_remote_adapter_converts_rate_limit_to_typed_unavailability() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limited"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        reranker = ApiCrossEncoderReranker(
            provider=ApiRerankerProvider.COHERE,
            api_key="test-key",
            model_name="test-model",
            timeout_seconds=1.0,
            max_documents=15,
            http_client=client,
        )
        with pytest.raises(RerankerUnavailableError, match="unavailable"):
            await reranker.rerank("query", ["first"])


@pytest.mark.asyncio
async def test_remote_adapter_rejects_candidate_count_over_the_configured_budget() -> None:
    def no_request(_: httpx.Request) -> httpx.Response:
        raise AssertionError("the provider must not be called")

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_request)) as client:
        reranker = ApiCrossEncoderReranker(
            provider=ApiRerankerProvider.VOYAGE,
            api_key="test-key",
            model_name="test-model",
            timeout_seconds=1.0,
            max_documents=1,
            http_client=client,
        )
        with pytest.raises(RerankerUnavailableError, match="candidate limit"):
            await reranker.rerank("query", ["first", "second"])


@pytest.mark.asyncio
async def test_remote_adapter_redacts_pii_before_the_provider_boundary() -> None:
    received: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"results": [{"index": 0, "relevance_score": 0.8}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        reranker = ApiCrossEncoderReranker(
            provider=ApiRerankerProvider.JINA,
            api_key="test-key",
            model_name="test-model",
            timeout_seconds=1.0,
            max_documents=15,
            http_client=client,
        )
        await reranker.rerank(
            "lore about user@example.com",
            ["Contact user@example.com for private records."],
        )

    assert "user@example.com" not in received["query"]
    assert "user@example.com" not in received["documents"][0]
    assert "[REDACTED_EMAIL]" in received["query"]
