"""RAG-05 contract tests for the local FastEmbed reranker adapter."""

from __future__ import annotations

import inspect
import time
from typing import Any

import pytest

from app.domain.interfaces.reranker import RerankerUnavailableError
from app.infrastructure.rag.fastembed_cross_encoder_reranker import (
    FastEmbedCrossEncoderReranker,
)


def test_request_time_download_policy_is_not_configurable() -> None:
    """No deployment setting or caller can opt the adapter into network fetching."""
    assert "local_files_only" not in inspect.signature(FastEmbedCrossEncoderReranker).parameters


def test_model_loading_forwards_local_only_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """The adapter must never permit a request-time model download."""
    from fastembed.rerank import cross_encoder

    constructed: dict[str, Any] = {}

    class _Model:
        def __init__(self, model_name: str, **kwargs: Any) -> None:
            constructed["model_name"] = model_name
            constructed.update(kwargs)

        def rerank(self, *_: object, **__: object) -> list[float]:
            return [0.1]

    monkeypatch.setattr(cross_encoder, "TextCrossEncoder", _Model)
    reranker = FastEmbedCrossEncoderReranker(
        model_name="approved-reranker",
        timeout_seconds=1.0,
        batch_size=8,
    )

    assert reranker._get_model() is not None
    assert constructed == {
        "model_name": "approved-reranker",
        "lazy_load": False,
        "local_files_only": True,
    }


@pytest.mark.asyncio
async def test_timeout_is_a_typed_fail_closed_result(monkeypatch: pytest.MonkeyPatch) -> None:
    reranker = FastEmbedCrossEncoderReranker(
        model_name="approved-reranker",
        timeout_seconds=0.001,
        batch_size=8,
    )

    def slow_rerank(_: str, __: tuple[str, ...]) -> list[float]:
        time.sleep(0.02)
        return [0.1]

    monkeypatch.setattr(reranker, "_rerank_sync", slow_rerank)

    with pytest.raises(RerankerUnavailableError, match="timed out"):
        await reranker.rerank("query", ["document"])


@pytest.mark.asyncio
async def test_invalid_score_cardinality_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    reranker = FastEmbedCrossEncoderReranker(
        model_name="approved-reranker",
        timeout_seconds=1.0,
        batch_size=8,
    )
    monkeypatch.setattr(reranker, "_rerank_sync", lambda *_: [0.1])

    with pytest.raises(RerankerUnavailableError, match="invalid score cardinality"):
        await reranker.rerank("query", ["first", "second"])


@pytest.mark.asyncio
async def test_model_load_failure_does_not_escape_as_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reranker = FastEmbedCrossEncoderReranker(
        model_name="approved-reranker",
        timeout_seconds=1.0,
        batch_size=8,
    )
    monkeypatch.setattr(reranker, "_rerank_sync", lambda *_: (_ for _ in ()).throw(OSError()))

    with pytest.raises(RerankerUnavailableError, match="unavailable"):
        await reranker.rerank("query", ["document"])
