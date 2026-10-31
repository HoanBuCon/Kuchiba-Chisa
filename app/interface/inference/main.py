"""Internal inference API: one model copy serves embeddings and optional local rerank (KNW-007)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Literal, Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.config.inference_settings import InferenceSettings
from app.domain.interfaces.reranker import RerankerUnavailableError
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.inference.contracts import (
    EmbeddingGenerationError,
    EmbeddingModelInfo,
    with_e5_prefix,
)
from app.infrastructure.rag.fastembed_cross_encoder_reranker import FastEmbedCrossEncoderReranker

log = logging.getLogger(__name__)


class Embedder(Protocol):
    def info(self) -> EmbeddingModelInfo: ...

    def embed_sync(self, texts: list[str]) -> list[list[float]]: ...


class Reranker(Protocol):
    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]: ...


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmbedRequest(_Strict):
    texts: list[str] = Field(min_length=1)
    kind: Literal["query", "passage"]


class EmbedResponse(_Strict):
    model: str
    revision: str
    dimension: int
    vectors: list[list[float]]


class RerankRequest(_Strict):
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1)


class RerankResponse(_Strict):
    scores: list[float]


class InfoResponse(_Strict):
    model: str
    revision: str
    dimension: int
    reranker: str | None


def _enforce_limits(texts: Sequence[str], settings: InferenceSettings, *, query: str = "") -> None:
    if len(texts) > settings.INFERENCE_MAX_BATCH:
        raise HTTPException(413, f"at most {settings.INFERENCE_MAX_BATCH} texts per request")
    if any(len(text) > settings.INFERENCE_MAX_TEXT_CHARS for text in (query, *texts)):
        raise HTTPException(
            413, f"texts are limited to {settings.INFERENCE_MAX_TEXT_CHARS} characters"
        )


def create_app(
    embedder: Embedder,
    reranker: Reranker | None,
    settings: InferenceSettings,
    *,
    reranker_name: str | None = None,
) -> FastAPI:
    gate = asyncio.Semaphore(settings.INFERENCE_CONCURRENCY)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Load before accepting traffic so /ready means the model is in memory.
        await asyncio.to_thread(embedder.info)
        yield

    app = FastAPI(title="Chisa inference", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready", "model": embedder.info().model}

    @app.get("/v1/info", response_model=InfoResponse)
    async def info() -> InfoResponse:
        model = embedder.info()
        return InfoResponse(
            model=model.model,
            revision=model.revision,
            dimension=model.dimension,
            reranker=reranker_name,
        )

    @app.post("/v1/embed", response_model=EmbedResponse)
    async def embed(request: EmbedRequest) -> EmbedResponse:
        _enforce_limits(request.texts, settings)
        prefixed = [with_e5_prefix(text, f"{request.kind}: ") for text in request.texts]
        async with gate:
            try:
                vectors = await asyncio.to_thread(embedder.embed_sync, prefixed)
            except EmbeddingGenerationError as error:
                log.warning("Embedding failed: %s", type(error).__name__)
                raise HTTPException(503, "embedding unavailable") from error
        model = embedder.info()
        return EmbedResponse(
            model=model.model, revision=model.revision, dimension=model.dimension, vectors=vectors
        )

    @app.post("/v1/rerank", response_model=RerankResponse)
    async def rerank(request: RerankRequest) -> RerankResponse:
        if reranker is None:
            raise HTTPException(404, "local reranker is not provisioned")
        _enforce_limits(request.documents, settings, query=request.query)
        async with gate:
            try:
                scores = await reranker.rerank(request.query, request.documents)
            except RerankerUnavailableError as error:
                raise HTTPException(503, "reranker unavailable") from error
        return RerankResponse(scores=scores)

    return app


def build_app(settings: InferenceSettings | None = None) -> FastAPI:
    """Composition root for `uvicorn app.interface.inference.main:app`."""
    settings = settings or InferenceSettings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    embedder = FastEmbedAdapter(settings.EMBEDDING_MODEL, threads=settings.INFERENCE_THREADS)
    reranker = (
        FastEmbedCrossEncoderReranker(
            model_name=settings.RERANKER_MODEL,
            timeout_seconds=settings.RERANKER_TIMEOUT_SECONDS,
            batch_size=settings.RERANKER_BATCH_SIZE,
        )
        if settings.RERANKER_MODEL
        else None
    )
    return create_app(embedder, reranker, settings, reranker_name=settings.RERANKER_MODEL)


app = build_app()
