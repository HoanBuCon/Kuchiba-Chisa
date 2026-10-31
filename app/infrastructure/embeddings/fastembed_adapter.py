"""In-process ONNX embedding; only the inference service and offline tools load it (KNW-007)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.infrastructure.inference.contracts import (
    EmbeddingGenerationError,
    EmbeddingModelInfo,
    with_e5_prefix,
)
from app.infrastructure.inference.models import E5_SMALL, register_known_models

# Stdlib logging: the inference service must run without the application Settings and secrets.
log = logging.getLogger(__name__)


class FastEmbedAdapter:
    """Loads the model once and embeds on a worker thread so the event loop stays responsive."""

    def __init__(self, model_name: str = E5_SMALL, *, threads: int | None = None) -> None:
        self._model_name = model_name
        self._threads = threads
        self._model: Any | None = None
        self._info: EmbeddingModelInfo | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self.info().dimension

    @property
    def version(self) -> str:
        return self.info().revision

    def info(self) -> EmbeddingModelInfo:
        if self._info is None:
            self._load()
        assert self._info is not None
        return self._info

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        from fastembed import TextEmbedding

        register_known_models()
        log.info("Loading embedding model %s", self._model_name)
        try:
            # The default ONNX arena keeps peak batch buffers for the process lifetime
            # (measured 1.75 GB vs 0.8 GB at batch 32), so it is disabled.
            self._model = TextEmbedding(
                self._model_name, threads=self._threads, enable_cpu_mem_arena=False
            )
            probe = next(iter(self._model.embed(["query: warm-up"])))
        except Exception as error:
            raise EmbeddingGenerationError(f"Model initialization failed: {error}") from error
        model_dir = getattr(self._model.model, "_model_dir", None)
        self._info = EmbeddingModelInfo(
            model=self._model_name,
            dimension=len(probe),
            revision=getattr(model_dir, "name", None) or "unknown",
        )
        return self._model

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Embed already-prefixed texts in the calling thread."""
        model = self._load()
        try:
            return [vector.tolist() for vector in model.embed(texts, batch_size=len(texts) or 1)]
        except Exception as error:
            raise EmbeddingGenerationError(f"Failed to generate embeddings: {error}") from error

    async def embed_batch(self, texts: list[str], prefix: str = "query: ") -> list[list[float]]:
        prefixed = [with_e5_prefix(text, prefix) for text in texts]
        return await asyncio.to_thread(self.embed_sync, prefixed)

    async def embed_text(self, text: str, prefix: str = "query: ") -> list[float]:
        cleaned = text.strip()
        if not cleaned:
            return []
        return (await self.embed_batch([cleaned], prefix=prefix))[0]
