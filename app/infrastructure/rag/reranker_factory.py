"""Composition helper for the approved RAG-05 reranker implementations."""

from __future__ import annotations

import httpx

from app.config.settings import Settings
from app.domain.interfaces.reranker import ICrossEncoderReranker
from app.infrastructure.rag.api_cross_encoder_reranker import (
    ApiCrossEncoderReranker,
    ApiRerankerProvider,
)
from app.infrastructure.rag.fastembed_cross_encoder_reranker import FastEmbedCrossEncoderReranker


def build_cross_encoder_reranker(
    *, config: Settings, http_client: httpx.AsyncClient
) -> ICrossEncoderReranker | None:
    """Construct only an explicitly configured remote or provisioned local adapter."""
    if config.RERANKER_PROVIDER == "disabled":
        return None
    if config.RERANKER_PROVIDER == "local":
        if not config.RERANKER_MODEL:
            return None
        return FastEmbedCrossEncoderReranker(
            model_name=config.RERANKER_MODEL,
            timeout_seconds=config.RERANKER_TIMEOUT_SECONDS,
            batch_size=config.RERANKER_BATCH_SIZE,
        )

    api_key_by_provider = {
        "voyage": config.VOYAGE_API_KEY,
        "jina": config.JINA_API_KEY,
        "cohere": config.COHERE_API_KEY,
    }
    api_key = api_key_by_provider[config.RERANKER_PROVIDER]
    if not api_key:
        return None
    return ApiCrossEncoderReranker(
        provider=ApiRerankerProvider(config.RERANKER_PROVIDER),
        api_key=api_key,
        model_name=config.RERANKER_API_MODEL,
        timeout_seconds=config.RERANKER_TIMEOUT_SECONDS,
        max_documents=config.RERANKER_API_MAX_DOCUMENTS,
        http_client=http_client,
    )
