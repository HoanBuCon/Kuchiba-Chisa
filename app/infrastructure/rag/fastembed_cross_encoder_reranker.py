"""FastEmbed adapter for locally approved cross-encoder reranking."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from typing import Any

from app.domain.interfaces.reranker import RerankerUnavailableError


class FastEmbedCrossEncoderReranker:
    """Run a local cross encoder without allowing request-time model downloads.

    The model artifact must be independently approved and provisioned in the
    deployment image/cache. This adapter intentionally fails closed when it is
    absent so a network outage cannot turn reranking into an unbounded request.
    """

    def __init__(
        self,
        *,
        model_name: str,
        timeout_seconds: float,
        batch_size: int,
    ) -> None:
        if not model_name.strip():
            raise ValueError("cross-encoder model name is required")
        if timeout_seconds <= 0:
            raise ValueError("cross-encoder timeout must be positive")
        if batch_size <= 0:
            raise ValueError("cross-encoder batch size must be positive")
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._batch_size = batch_size
        # RAG-05 requires a pre-approved artifact to be provisioned before
        # deployment. This is deliberately not an environment switch: allowing
        # a request-time download defeats the bounded fallback contract.
        self._local_files_only = True
        self._model: Any | None = None

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """Return one finite score per input or raise a typed unavailability error."""
        if not query.strip() or not documents:
            return []
        try:
            scores = await asyncio.wait_for(
                asyncio.to_thread(self._rerank_sync, query, tuple(documents)),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as error:
            raise RerankerUnavailableError("cross-encoder reranking timed out") from error
        except RerankerUnavailableError:
            raise
        except Exception as error:
            raise RerankerUnavailableError("cross-encoder reranking is unavailable") from error
        if len(scores) != len(documents) or not all(math.isfinite(score) for score in scores):
            raise RerankerUnavailableError("cross-encoder returned invalid score cardinality")
        return scores

    def _rerank_sync(self, query: str, documents: tuple[str, ...]) -> list[float]:
        model = self._get_model()
        return [
            float(score)
            for score in model.rerank(query, documents, batch_size=self._batch_size)
        ]

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(
                self._model_name,
                lazy_load=False,
                local_files_only=self._local_files_only,
            )
        except Exception as error:
            raise RerankerUnavailableError("approved cross-encoder model is unavailable") from error
        return self._model
