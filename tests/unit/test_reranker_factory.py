"""RAG-05 composition tests for explicit reranker selection."""

from __future__ import annotations

import httpx
import pytest

from app.config.settings import Settings
from app.domain.interfaces.reranker import RerankerDataBoundary
from app.infrastructure.rag.api_cross_encoder_reranker import ApiCrossEncoderReranker
from app.infrastructure.rag.fastembed_cross_encoder_reranker import FastEmbedCrossEncoderReranker
from app.infrastructure.rag.reranker_factory import build_cross_encoder_reranker


def _settings(**overrides: str) -> Settings:
    values = {
        "SECRET_KEY": "a" * 32,
        "DATABASE_URL": "postgresql+asyncpg://chisa:secret@postgres/chisa_db",
        "JWT_SECRET": "b" * 32,
        "DISCORD_WORKLOAD_JWT_SECRET": "c" * 32,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_factory_keeps_remote_reranking_disabled_without_explicit_provider() -> None:
    async with httpx.AsyncClient() as client:
        assert build_cross_encoder_reranker(config=_settings(), http_client=client) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "model", "key_setting"),
    [
        ("voyage", "rerank-3-lite", "VOYAGE_API_KEY"),
        ("jina", "jina-reranker-v3.5", "JINA_API_KEY"),
    ],
)
async def test_factory_constructs_an_explicit_remote_provider(
    provider: str,
    model: str,
    key_setting: str,
) -> None:
    async with httpx.AsyncClient() as client:
        reranker = build_cross_encoder_reranker(
            config=_settings(
                RERANKER_PROVIDER=provider,
                RERANKER_API_MODEL=model,
                **{key_setting: "test-key"},
            ),
            http_client=client,
        )
        assert isinstance(reranker, ApiCrossEncoderReranker)
        assert reranker.data_boundary is RerankerDataBoundary.REMOTE


@pytest.mark.asyncio
async def test_factory_preserves_the_explicitly_provisioned_local_adapter() -> None:
    async with httpx.AsyncClient() as client:
        reranker = build_cross_encoder_reranker(
            config=_settings(
                RERANKER_PROVIDER="local",
                RERANKER_MODEL="approved-reranker",
            ),
            http_client=client,
        )
        assert isinstance(reranker, FastEmbedCrossEncoderReranker)
        assert reranker.data_boundary is RerankerDataBoundary.LOCAL
