"""HTTP adapters for approved remote cross-encoder reranker providers."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

import httpx

from app.domain.interfaces.reranker import (
    RerankerDataBoundary,
    RerankerFailureKind,
    RerankerUnavailableError,
)
from app.domain.services.guardrails.pii_redaction import PiiRedactor


class ApiRerankerProvider(StrEnum):
    """Remote providers approved for the RAG-05 benchmark."""

    VOYAGE = "voyage"
    JINA = "jina"
    COHERE = "cohere"


class ApiCrossEncoderReranker:
    """Bounded remote reranker with strict response cardinality validation.

    The endpoint is selected from a provider allowlist rather than configuration,
    preventing a deployment setting from becoming an arbitrary outbound URL.
    Callers must apply their evidence policy before invoking this adapter.
    """

    data_boundary = RerankerDataBoundary.REMOTE

    _ENDPOINTS: Mapping[ApiRerankerProvider, str] = {
        ApiRerankerProvider.VOYAGE: "https://api.voyageai.com/v1/rerank",
        ApiRerankerProvider.JINA: "https://api.jina.ai/v1/rerank",
        ApiRerankerProvider.COHERE: "https://api.cohere.com/v2/rerank",
    }

    def __init__(
        self,
        *,
        provider: ApiRerankerProvider,
        api_key: str,
        model_name: str,
        timeout_seconds: float,
        max_documents: int,
        http_client: httpx.AsyncClient,
        pii_redactor: PiiRedactor | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("reranker API key is required")
        if not model_name.strip():
            raise ValueError("reranker model name is required")
        if timeout_seconds <= 0:
            raise ValueError("reranker timeout must be positive")
        if max_documents < 1:
            raise ValueError("reranker max_documents must be positive")
        self._provider = provider
        self._api_key = api_key
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._max_documents = max_documents
        self._http_client = http_client
        self._pii_redactor = pii_redactor or PiiRedactor()
        self._last_http_latency_ms: float | None = None

    @property
    def last_http_latency_ms(self) -> float | None:
        """Latency of the latest successfully validated provider response."""
        return self._last_http_latency_ms

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """Return one finite score per document or a typed unavailable result."""
        self._last_http_latency_ms = None
        if not query.strip() or not documents:
            return []
        if len(documents) > self._max_documents:
            raise RerankerUnavailableError("reranker candidate limit exceeded")
        if not all(document.strip() for document in documents):
            raise RerankerUnavailableError("reranker received an empty candidate")

        redacted_query = self._pii_redactor.redact(query).value
        redacted_documents = [
            self._pii_redactor.redact(document).value for document in documents
        ]
        payload: dict[str, Any] = {
            "model": self._model_name,
            "query": redacted_query,
            "documents": redacted_documents,
        }
        if self._provider is ApiRerankerProvider.VOYAGE:
            # Voyage names this field ``top_k``.  Using the Cohere/Jina
            # spelling (``top_n``) makes a valid model request fail with 400.
            payload["top_k"] = len(documents)
        else:
            payload["top_n"] = len(documents)
        if self._provider is ApiRerankerProvider.JINA:
            payload["return_documents"] = False

        request_started = time.perf_counter()
        try:
            response = await self._http_client.post(
                self._ENDPOINTS[self._provider],
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            response_payload = response.json()
        except httpx.TimeoutException as error:
            raise RerankerUnavailableError(
                "remote reranker timed out",
                failure_kind=RerankerFailureKind.TIMEOUT,
            ) from error
        except httpx.HTTPStatusError as error:
            failure_kind = (
                RerankerFailureKind.RATE_LIMIT
                if error.response.status_code == 429
                else RerankerFailureKind.PROVIDER
            )
            raise RerankerUnavailableError(
                "remote reranker is unavailable", failure_kind=failure_kind
            ) from error
        except httpx.RequestError as error:
            raise RerankerUnavailableError(
                "remote reranker is unavailable",
                failure_kind=RerankerFailureKind.PROVIDER,
            ) from error
        except (TypeError, ValueError) as error:
            raise RerankerUnavailableError(
                "remote reranker returned invalid JSON",
                failure_kind=RerankerFailureKind.INVALID_RESPONSE,
            ) from error

        try:
            scores = self._parse_scores(response_payload, len(documents))
        except RerankerUnavailableError as error:
            raise RerankerUnavailableError(
                "remote reranker returned an invalid response",
                failure_kind=RerankerFailureKind.INVALID_RESPONSE,
            ) from error
        self._last_http_latency_ms = (time.perf_counter() - request_started) * 1000
        return scores

    def _parse_scores(self, response_payload: object, expected_count: int) -> list[float]:
        if not isinstance(response_payload, dict):
            raise RerankerUnavailableError("remote reranker returned an invalid response")
        results_key = "data" if self._provider is ApiRerankerProvider.VOYAGE else "results"
        raw_results = response_payload.get(results_key)
        if not isinstance(raw_results, list) or len(raw_results) != expected_count:
            raise RerankerUnavailableError("remote reranker returned invalid score cardinality")

        scores: list[float | None] = [None] * expected_count
        for result in raw_results:
            if not isinstance(result, dict):
                raise RerankerUnavailableError("remote reranker returned an invalid score")
            index = result.get("index")
            relevance_score = result.get("relevance_score")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or not 0 <= index < expected_count
                or scores[index] is not None
                or not isinstance(relevance_score, int | float)
                or isinstance(relevance_score, bool)
                or not math.isfinite(float(relevance_score))
            ):
                raise RerankerUnavailableError("remote reranker returned an invalid score")
            scores[index] = float(relevance_score)

        if any(score is None for score in scores):
            raise RerankerUnavailableError("remote reranker returned incomplete scores")
        return [score for score in scores if score is not None]
