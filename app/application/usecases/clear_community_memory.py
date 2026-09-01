"""Retryable, tenant-scoped erasure of shared community memory."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.repositories import IErasureJobRepository
from app.domain.interfaces.vector_store import IVectorStore
from app.infrastructure.logging.logger import get_logger
from app.shared.utils.user_identity import normalize_user_id_str

log = get_logger(__name__)


class ClearCommunityMemoryUseCase:
    """Erases only tenant-indexed state and records retryable outcomes."""

    def __init__(
        self,
        vector_store: IVectorStore,
        cache_provider: ICacheProvider,
        erasure_repo_factory: Callable[[AsyncSession], IErasureJobRepository],
    ) -> None:
        self.vector_store = vector_store
        self.cache_provider = cache_provider
        self.erasure_repo_factory = erasure_repo_factory

    async def execute(
        self,
        session: AsyncSession,
        guild_id: str,
        scope: str = "all",
        channel_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Return completed only after all in-scope store deletions acknowledge."""
        if scope not in {"all", "self"}:
            raise ValueError("unsupported community erasure scope")
        if scope == "self" and (channel_id is None or user_id is None):
            raise ValueError("self community erasure requires verified channel and user")

        target_hash = self._target_hash(guild_id, scope, channel_id, user_id)
        erasure_repo = self.erasure_repo_factory(session)
        job = await erasure_repo.create(target_hash)
        results: dict[str, str] = {"traces": "not_applicable_redacted"}
        current_store = "qdrant"

        try:
            if scope == "all":
                await self._clear_all_vectors(guild_id, results)
                current_store = "redis"
                await self._clear_all_cache(guild_id, results)
            else:
                await self._clear_self_vectors(user_id, results)
                current_store = "redis"
                await self._clear_self_cache(guild_id, channel_id, results)
        except Exception as error:
            results["failed_store"] = current_store
            log.warning(
                "Community erasure requires retry",
                target_hash=target_hash,
                failed_store=current_store,
                error_type=type(error).__name__,
            )
            await erasure_repo.finish(
                job.id,
                status="RETRY_REQUIRED",
                store_results=results,
                error_code=type(error).__name__,
            )
            return {"job_id": str(job.id), "status": "retry_required", "stores": results}

        await erasure_repo.finish(job.id, status="COMPLETED", store_results=results)
        return {"job_id": str(job.id), "status": "completed", "stores": results}

    async def _clear_all_vectors(self, guild_id: str, results: dict[str, str]) -> None:
        from app.infrastructure.vector.qdrant.qdrant_service import COLLECTION_GUILD_MEMORIES

        await self.vector_store.delete_by_guild(COLLECTION_GUILD_MEMORIES, guild_id)
        results["qdrant"] = "acknowledged"

    async def _clear_all_cache(self, guild_id: str, results: dict[str, str]) -> None:
        await self.cache_provider.delete(f"chisa:guild:{guild_id}:ambient_mood")
        channel_ids = await self.cache_provider.get_json(
            f"chisa:guild:{guild_id}:community_channels"
        )
        cleared_channels = 0
        if isinstance(channel_ids, list):
            for cached_channel_id in channel_ids:
                if not isinstance(cached_channel_id, str):
                    continue
                prefix = f"chisa:guild:{guild_id}:channel:{cached_channel_id}"
                for suffix in ("topic_summary", "rolling_buffer", "msg_count"):
                    await self.cache_provider.delete(f"{prefix}:{suffix}")
                cleared_channels += 1
        await self.cache_provider.delete(f"chisa:guild:{guild_id}:community_channels")
        results["redis"] = "acknowledged"
        results["channels"] = str(cleared_channels)

    async def _clear_self_vectors(
        self,
        user_id: str | None,
        results: dict[str, str],
    ) -> None:
        from app.infrastructure.vector.qdrant.qdrant_service import COLLECTION_MEMORIES

        assert user_id is not None
        await self.vector_store.delete_by_user(
            COLLECTION_MEMORIES, normalize_user_id_str(user_id)
        )
        results["qdrant"] = "acknowledged"

    async def _clear_self_cache(
        self,
        guild_id: str,
        channel_id: str | None,
        results: dict[str, str],
    ) -> None:
        assert channel_id is not None
        prefix = f"chisa:guild:{guild_id}:channel:{channel_id}"
        for suffix in ("topic_summary", "rolling_buffer", "msg_count"):
            await self.cache_provider.delete(f"{prefix}:{suffix}")
        results["redis"] = "acknowledged"

    @staticmethod
    def _target_hash(
        guild_id: str,
        scope: str,
        channel_id: str | None,
        user_id: str | None,
    ) -> str:
        target = "|".join((guild_id, scope, channel_id or "-", user_id or "-"))
        return hashlib.sha256(target.encode()).hexdigest()
