"""Redis cache for single-query embeddings in front of any embedding provider."""

from __future__ import annotations

import hashlib
import json

from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.inference.contracts import with_e5_prefix
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

QUERY_CACHE_TTL_SECONDS = 600


class CachedEmbeddingProvider:
    """Caches embed_text results; batches are passages, not repeat queries, so they pass through."""

    def __init__(self, inner: IEmbeddingProvider, cache) -> None:
        self._inner = inner
        self._cache = cache

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    @property
    def dimension(self) -> int:
        return self._inner.dimension

    @property
    def version(self) -> str:
        return self._inner.version

    async def embed_batch(self, texts: list[str], prefix: str = "query: ") -> list[list[float]]:
        return await self._inner.embed_batch(texts, prefix=prefix)

    async def embed_text(self, text: str, prefix: str = "query: ") -> list[float]:
        cleaned = text.strip()
        if not cleaned:
            return []
        key = self._key(with_e5_prefix(cleaned, prefix))
        try:
            cached = await self._cache.get(key)
            if cached:
                return json.loads(cached)
        except Exception as error:  # noqa: BLE001 - a cache outage must never block embedding
            log.warning("Embedding cache read failed", error_type=type(error).__name__)
        vector = await self._inner.embed_text(cleaned, prefix=prefix)
        try:
            await self._cache.set(key, json.dumps(vector), ttl=QUERY_CACHE_TTL_SECONDS)
        except Exception as error:  # noqa: BLE001 - a cache outage must never block embedding
            log.warning("Embedding cache write failed", error_type=type(error).__name__)
        return vector

    def _key(self, prefixed_text: str) -> str:
        digest = hashlib.sha256(prefixed_text.lower().encode("utf-8")).hexdigest()
        model_slug = self.model_name.replace("/", "_").replace(".", "_")
        return f"chisa:embedding_cache:{model_slug}:{digest}"
