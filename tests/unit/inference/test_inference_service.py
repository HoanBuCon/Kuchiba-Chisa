"""Inference service contract: limits, e5 prefixes, optional rerank, failures (KNW-005/007)."""

import asyncio
import threading
from collections.abc import Sequence

import httpx
import pytest

from app.config.inference_settings import InferenceSettings
from app.domain.interfaces.reranker import RerankerUnavailableError
from app.infrastructure.inference.contracts import EmbeddingGenerationError, EmbeddingModelInfo
from app.interface.inference.main import create_app

INFO = EmbeddingModelInfo(model="intfloat/multilingual-e5-small", dimension=3, revision="rev-1")


class FakeEmbedder:
    def __init__(self, fail: bool = False) -> None:
        self.seen: list[list[str]] = []
        self.fail = fail

    def info(self) -> EmbeddingModelInfo:
        return INFO

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise EmbeddingGenerationError("onnx exploded")
        self.seen.append(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeReranker:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        if self.fail:
            raise RerankerUnavailableError("model missing")
        return [float(len(d)) for d in documents]


def _client(embedder=None, reranker=None, **settings) -> httpx.AsyncClient:
    config = InferenceSettings(INFERENCE_MAX_BATCH=2, INFERENCE_MAX_TEXT_CHARS=300, **settings)
    app = create_app(
        embedder or FakeEmbedder(), reranker, config, reranker_name="tiny" if reranker else None
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://inference")


@pytest.mark.asyncio
async def test_embed_applies_the_requested_e5_prefix_once() -> None:
    embedder = FakeEmbedder()
    async with _client(embedder) as client:
        response = await client.post(
            "/v1/embed", json={"texts": ["Chisa", "passage: kept"], "kind": "passage"}
        )
    assert response.status_code == 200
    assert response.json()["dimension"] == 3 and len(response.json()["vectors"]) == 2
    assert embedder.seen == [["passage: Chisa", "passage: kept"]]


@pytest.mark.asyncio
async def test_embed_rejects_oversized_batches_and_texts() -> None:
    async with _client() as client:
        too_many = await client.post("/v1/embed", json={"texts": ["a", "b", "c"], "kind": "query"})
        too_long = await client.post("/v1/embed", json={"texts": ["x" * 301], "kind": "query"})
        bad_kind = await client.post("/v1/embed", json={"texts": ["a"], "kind": "other"})
    assert too_many.status_code == 413 and too_long.status_code == 413
    assert bad_kind.status_code == 422


@pytest.mark.asyncio
async def test_embedding_failure_is_a_503_without_internal_detail() -> None:
    async with _client(FakeEmbedder(fail=True)) as client:
        response = await client.post("/v1/embed", json={"texts": ["a"], "kind": "query"})
    assert response.status_code == 503
    assert "onnx" not in response.text


@pytest.mark.asyncio
async def test_info_and_readiness_report_the_loaded_model() -> None:
    async with _client(reranker=FakeReranker()) as client:
        info = (await client.get("/v1/info")).json()
        ready = await client.get("/ready")
    assert info == {"model": INFO.model, "revision": "rev-1", "dimension": 3, "reranker": "tiny"}
    assert ready.status_code == 200


@pytest.mark.asyncio
async def test_rerank_is_404_until_a_local_model_is_provisioned() -> None:
    async with _client() as client:
        response = await client.post("/v1/rerank", json={"query": "q", "documents": ["a"]})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rerank_scores_and_maps_unavailability_to_503() -> None:
    async with _client(reranker=FakeReranker()) as client:
        ok = await client.post("/v1/rerank", json={"query": "q", "documents": ["a", "bbb"]})
    async with _client(reranker=FakeReranker(fail=True)) as client:
        down = await client.post("/v1/rerank", json={"query": "q", "documents": ["a"]})
    assert ok.json() == {"scores": [1.0, 3.0]}
    assert down.status_code == 503


class BlockingPassageEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        if texts[0].startswith("passage: "):
            self.release.wait(timeout=5)
        return super().embed_sync(texts)


@pytest.mark.asyncio
async def test_query_is_served_while_a_passage_batch_is_running() -> None:
    embedder = BlockingPassageEmbedder()
    async with _client(embedder) as client:
        batch = asyncio.create_task(
            client.post("/v1/embed", json={"texts": ["chunk"], "kind": "passage"})
        )
        await asyncio.sleep(0.05)
        query = await asyncio.wait_for(
            client.post("/v1/embed", json={"texts": ["Chisa?"], "kind": "query"}), timeout=2
        )
        embedder.release.set()
        assert query.status_code == 200
        assert (await batch).status_code == 200
