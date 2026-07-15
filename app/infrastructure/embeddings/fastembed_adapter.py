import asyncio
from typing import List, Optional

from fastembed import TextEmbedding

from app.config.settings import settings
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class EmbeddingGenerationError(Exception):
    """Custom exception raised when vector embedding generation fails."""
    pass


class FastEmbedAdapter(IEmbeddingProvider):
    """
    Adapter for generating vector embeddings locally using FastEmbed.
    It runs CPU-bound matrix operations in a separate thread to prevent blocking
    the FastAPI async event loop.
    """

    def __init__(self) -> None:
        self.model_name = settings.EMBEDDING_MODEL
        self._model: Optional[TextEmbedding] = None
        log.info("FastEmbedAdapter initialized. Model parsing deferred until first use.", model=self.model_name)

    def _get_model(self) -> TextEmbedding:
        """
        Lazily load the FastEmbed model on first use.
        This prevents blocking the application startup, especially when downloading weights.
        """
        if self._model is None:
            log.info("Loading FastEmbed model into memory...", model=self.model_name)
            try:
                # Register intfloat/multilingual-e5-small dynamically if selected
                if self.model_name == "intfloat/multilingual-e5-small":
                    from fastembed.common.model_description import PoolingType, ModelSource
                    try:
                        TextEmbedding.add_custom_model(
                            model="intfloat/multilingual-e5-small",
                            pooling=PoolingType.MEAN,
                            normalization=True,
                            sources=ModelSource(hf="intfloat/multilingual-e5-small"),
                            dim=384,
                            model_file="onnx/model.onnx"
                        )
                        log.info("Registered custom model intfloat/multilingual-e5-small successfully.")
                    except Exception as register_ex:
                        log.debug("Note: Custom model registration handled.", error=str(register_ex))

                # This will download the model weights (if not cached) and load it into RAM
                self._model = TextEmbedding(model_name=self.model_name)
                log.info("FastEmbed model loaded successfully.")
            except Exception as e:
                log.error("Failed to load FastEmbed model.", error=str(e))
                raise EmbeddingGenerationError(f"Model initialization failed: {e}") from e
        return self._model

    def _sync_embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Synchronous method computing the embeddings.
        FastEmbed yields an iterable of numpy arrays; we convert them to floats.
        """
        model = self._get_model()
        try:
            # list() forces the generator to evaluate
            embeddings_generator = model.embed(texts)
            embeddings = [vector.tolist() for vector in embeddings_generator]
            return embeddings
        except Exception as e:
            log.error("Error during embedding generation.", error=str(e))
            raise EmbeddingGenerationError(f"Failed to generate embeddings: {e}") from e

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Async wrapper to compute embeddings in a separate thread.
        """
        # Run the CPU-heavy blocking operation in the default ThreadPoolExecutor
        return await asyncio.to_thread(self._sync_embed_batch, texts)

    async def embed_text(self, text: str) -> List[float]:
        """
        Embed a single string text into a vector of floats, cached in Redis.
        """
        cleaned = text.strip().lower()
        if not cleaned:
            return []

        import hashlib
        import json
        from app.infrastructure.cache.redis.redis_service import redis_service

        h = hashlib.md5(cleaned.encode("utf-8")).hexdigest()
        model_slug = self.model_name.replace("/", "_").replace(".", "_")
        cache_key = f"chisa:embedding_cache:{model_slug}:{h}"

        # Try cache lookup first
        try:
            cached = await redis_service.get(cache_key)
            if cached:
                log.debug("Embedding cache hit", text=cleaned[:30])
                return json.loads(cached)
        except Exception as e:
            log.warning("Embedding cache read failed, falling back to generation", error=str(e))

        results = await self.embed_batch([text])
        if not results:
            raise EmbeddingGenerationError("No embedding was returned for the text.")

        # Cache the result for 10 minutes (600s)
        try:
            await redis_service.set(cache_key, json.dumps(results[0]), ttl=600)
        except Exception as e:
            log.warning("Embedding cache write failed", error=str(e))

        return results[0]
