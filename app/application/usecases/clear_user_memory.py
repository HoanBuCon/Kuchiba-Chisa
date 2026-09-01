"""Retryable, auditable user erasure across durable and derived data stores."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.image_storage import IImageStorageProvider
from app.domain.interfaces.repositories import (
    IConversationRepository,
    IEmotionRepository,
    IErasureJobRepository,
    IUserRepository,
)
from app.domain.interfaces.uow import IUnitOfWork
from app.domain.interfaces.vector_store import IVectorStore
from app.infrastructure.logging.logger import get_logger
from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str

log = get_logger(__name__)


class ClearUserMemoryUseCase:
    def __init__(
        self,
        uow_factory: Callable[[AsyncSession], IUnitOfWork],
        user_repo_factory: Callable[[AsyncSession], IUserRepository],
        emotion_repo_factory: Callable[[AsyncSession], IEmotionRepository],
        conv_repo_factory: Callable[[AsyncSession], IConversationRepository],
        erasure_repo_factory: Callable[[AsyncSession], IErasureJobRepository],
        vector_store: IVectorStore,
        cache_provider: ICacheProvider | None = None,
        image_storage: IImageStorageProvider | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.user_repo_factory = user_repo_factory
        self.emotion_repo_factory = emotion_repo_factory
        self.conv_repo_factory = conv_repo_factory
        self.erasure_repo_factory = erasure_repo_factory
        self.vector_store = vector_store
        self.cache_provider = cache_provider
        self.image_storage = image_storage

    async def execute(self, session: AsyncSession, user_id: str) -> dict[str, Any]:
        user_uuid = normalize_user_id(user_id)
        canonical_user_id = normalize_user_id_str(user_id)
        subject_hash = hashlib.sha256(canonical_user_id.encode()).hexdigest()
        erasure_repo = self.erasure_repo_factory(session)
        job = await erasure_repo.create(subject_hash)
        results: dict[str, str] = {}
        current_store = "postgres"
        try:
            image_ids = await self.conv_repo_factory(session).get_image_ids_for_user(user_uuid)
            current_store = "redis"
            if self.cache_provider:
                for key in sorted({
                    f"chisa:user:{user_uuid}:state",
                    f"chisa:user:{user_uuid}:summary",
                    f"chisa:user:{canonical_user_id}:state",
                    f"chisa:user:{canonical_user_id}:summary",
                }):
                    await self.cache_provider.delete(key)
            results["redis"] = "acknowledged"

            current_store = "qdrant"
            for collection in ("memories", "image_memories"):
                await self.vector_store.delete_by_user(collection, canonical_user_id)
            results["qdrant"] = "acknowledged"

            current_store = "images"
            if image_ids and self.image_storage is None:
                raise RuntimeError("image storage is required to erase stored image objects")
            if self.image_storage is not None:
                for image_id in image_ids:
                    await self.image_storage.delete_image(image_id)
            results["images"] = "acknowledged"
            results["traces"] = "not_applicable_redacted"

            current_store = "postgres"
            async with self.uow_factory(session):
                await self.conv_repo_factory(session).delete_all_for_user(user_uuid)
                await self.emotion_repo_factory(session).delete_all_for_user(user_uuid)
                await self.user_repo_factory(session).delete_all_for_user(user_uuid)
            results["postgres"] = "acknowledged"
        except Exception as error:
            results["failed_store"] = current_store
            log.warning(
                "Erasure requires retry",
                subject_hash=subject_hash,
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
