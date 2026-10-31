"""HTTP clients for the shared inference service; the API and worker never load models (KNW-007)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import httpx

from app.domain.interfaces.reranker import (
    RerankerDataBoundary,
    RerankerFailureKind,
    RerankerUnavailableError,
)
from app.infrastructure.inference.contracts import EmbeddingGenerationError, EmbeddingModelInfo


class InferenceEmbeddingClient:
    """IEmbeddingProvider over HTTP; splits large batches to the service's per-request limit."""

    def __init__(self, client: httpx.AsyncClient, *, model_name: str, max_batch: int) -> None:
        self._client = client
        self._model_name = model_name
        self._max_batch = max_batch
        self._info: EmbeddingModelInfo | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._loaded_info().dimension

    @property
    def version(self) -> str:
        return self._loaded_info().revision

    def _loaded_info(self) -> EmbeddingModelInfo:
        if self._info is None:
            raise EmbeddingGenerationError(
                "inference model info not loaded; call ensure_compatible()"
            )
        return self._info

    async def ensure_compatible(self, expected_dimension: int | None = None) -> EmbeddingModelInfo:
        """Refuse a service serving another model or dimension than expected here (KNW-005)."""
        payload = await self._call("GET", "/v1/info")
        info = EmbeddingModelInfo(
            model=str(payload["model"]),
            dimension=int(payload["dimension"]),
            revision=str(payload["revision"]),
        )
        if info.model != self._model_name:
            raise EmbeddingGenerationError(
                f"inference serves {info.model}, expected {self._model_name}"
            )
        if expected_dimension is not None and info.dimension != expected_dimension:
            raise EmbeddingGenerationError(
                f"inference dimension {info.dimension} != {expected_dimension}"
            )
        self._info = info
        return info

    async def embed_batch(self, texts: list[str], prefix: str = "query: ") -> list[list[float]]:
        kind = prefix.strip().rstrip(":")
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._max_batch):
            batch = texts[start : start + self._max_batch]
            payload = await self._call("POST", "/v1/embed", {"texts": batch, "kind": kind})
            received = payload.get("vectors")
            if not isinstance(received, list) or len(received) != len(batch):
                raise EmbeddingGenerationError("inference returned the wrong number of vectors")
            vectors.extend(received)
        return vectors

    async def embed_text(self, text: str, prefix: str = "query: ") -> list[float]:
        cleaned = text.strip()
        if not cleaned:
            return []
        return (await self.embed_batch([cleaned], prefix=prefix))[0]

    async def health_check(self) -> bool:
        try:
            response = await self._client.get("/ready")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def _call(self, method: str, path: str, body: dict[str, object] | None = None) -> dict:
        try:
            response = await self._client.request(method, path, json=body)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise EmbeddingGenerationError(
                f"inference {path} failed: {type(error).__name__}"
            ) from error
        payload = response.json()
        if not isinstance(payload, dict):
            raise EmbeddingGenerationError(f"inference {path} returned a non-object")
        return payload


class InferenceCrossEncoderReranker:
    """Local cross-encoder hosted by the inference service; text never leaves the VPS."""

    data_boundary = RerankerDataBoundary.LOCAL
    provider_name = "local"

    def __init__(self, client: httpx.AsyncClient, *, timeout_seconds: float) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        if not query.strip() or not documents:
            return []
        try:
            response = await self._client.post(
                "/v1/rerank",
                json={"query": query, "documents": list(documents)},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise RerankerUnavailableError(
                "local reranking timed out", failure_kind=RerankerFailureKind.TIMEOUT
            ) from error
        except httpx.HTTPError as error:
            raise RerankerUnavailableError("local reranking is unavailable") from error
        scores = response.json().get("scores")
        if (
            not isinstance(scores, list)
            or len(scores) != len(documents)
            or not all(isinstance(s, int | float) and math.isfinite(s) for s in scores)
        ):
            raise RerankerUnavailableError(
                "local reranker returned invalid scores",
                failure_kind=RerankerFailureKind.INVALID_RESPONSE,
            )
        return [float(score) for score in scores]
