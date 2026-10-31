"""API/worker side of the inference service: batching, model verification and rerank validation."""

import json

import httpx
import pytest

from app.domain.interfaces.reranker import RerankerFailureKind, RerankerUnavailableError
from app.infrastructure.embeddings.cached_embedder import CachedEmbeddingProvider
from app.infrastructure.inference.client import (
    InferenceCrossEncoderReranker,
    InferenceEmbeddingClient,
)
from app.infrastructure.inference.contracts import EmbeddingGenerationError

MODEL = "intfloat/multilingual-e5-small"


def _transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://inference")


def _embedding_service(calls: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/info":
            return httpx.Response(
                200, json={"model": MODEL, "dimension": 384, "revision": "r1", "reranker": None}
            )
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200, json={"vectors": [[float(i)] for i, _ in enumerate(body["texts"])]}
        )

    return handler


@pytest.mark.asyncio
async def test_batches_are_split_to_the_service_limit_and_keep_order() -> None:
    calls: list[dict] = []
    async with _transport(_embedding_service(calls)) as http:
        client = InferenceEmbeddingClient(http, model_name=MODEL, max_batch=2)
        vectors = await client.embed_batch(["a", "b", "c"], prefix="passage: ")
    assert [c["texts"] for c in calls] == [["a", "b"], ["c"]]
    assert {c["kind"] for c in calls} == {"passage"}
    assert vectors == [[0.0], [1.0], [0.0]]


@pytest.mark.asyncio
async def test_ensure_compatible_rejects_another_model_or_dimension() -> None:
    async with _transport(_embedding_service([])) as http:
        good = InferenceEmbeddingClient(http, model_name=MODEL, max_batch=8)
        info = await good.ensure_compatible(384)
        assert (info.dimension, good.version) == (384, "r1")
        with pytest.raises(EmbeddingGenerationError, match="dimension"):
            await good.ensure_compatible(1024)
        with pytest.raises(EmbeddingGenerationError, match="expected"):
            await InferenceEmbeddingClient(
                http, model_name="bge-m3", max_batch=8
            ).ensure_compatible()


@pytest.mark.asyncio
async def test_transport_failures_and_short_answers_raise_embedding_errors() -> None:
    async with _transport(lambda request: httpx.Response(503)) as http:
        with pytest.raises(EmbeddingGenerationError, match="HTTPStatusError"):
            await InferenceEmbeddingClient(http, model_name=MODEL, max_batch=8).embed_text("hi")
    async with _transport(lambda request: httpx.Response(200, json={"vectors": []})) as http:
        with pytest.raises(EmbeddingGenerationError, match="wrong number"):
            await InferenceEmbeddingClient(http, model_name=MODEL, max_batch=8).embed_batch(["a"])


@pytest.mark.asyncio
async def test_dimension_needs_a_verified_model() -> None:
    async with _transport(_embedding_service([])) as http:
        with pytest.raises(EmbeddingGenerationError, match="not loaded"):
            _ = InferenceEmbeddingClient(http, model_name=MODEL, max_batch=8).dimension


@pytest.mark.asyncio
async def test_reranker_validates_cardinality_and_maps_timeouts() -> None:
    async with _transport(lambda request: httpx.Response(200, json={"scores": [0.5, 0.1]})) as http:
        assert await InferenceCrossEncoderReranker(http, timeout_seconds=1).rerank(
            "q", ["a", "b"]
        ) == [0.5, 0.1]
    async with _transport(lambda request: httpx.Response(200, json={"scores": [0.5]})) as http:
        with pytest.raises(RerankerUnavailableError) as invalid:
            await InferenceCrossEncoderReranker(http, timeout_seconds=1).rerank("q", ["a", "b"])
    assert invalid.value.failure_kind is RerankerFailureKind.INVALID_RESPONSE

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async with _transport(slow) as http:
        with pytest.raises(RerankerUnavailableError) as timeout:
            await InferenceCrossEncoderReranker(http, timeout_seconds=1).rerank("q", ["a"])
    assert timeout.value.failure_kind is RerankerFailureKind.TIMEOUT


class FakeCache:
    def __init__(self, fail: bool = False) -> None:
        self.values: dict[str, str] = {}
        self.fail = fail

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise ConnectionError("redis down")
        return self.values.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        if self.fail:
            raise ConnectionError("redis down")
        self.values[key] = value


@pytest.mark.asyncio
async def test_query_cache_hits_skip_the_service_and_outages_fall_through() -> None:
    calls: list[dict] = []
    async with _transport(_embedding_service(calls)) as http:
        inner = InferenceEmbeddingClient(http, model_name=MODEL, max_batch=8)
        cached = CachedEmbeddingProvider(inner, FakeCache())
        assert await cached.embed_text("Chisa") == await cached.embed_text("Chisa")
        assert len(calls) == 1
        assert await CachedEmbeddingProvider(inner, FakeCache(fail=True)).embed_text("Chisa") == [
            0.0
        ]
