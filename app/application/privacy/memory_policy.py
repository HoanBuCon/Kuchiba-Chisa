"""Consent application service; routes never decide memory retention themselves."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.domain.interfaces.privacy import IPrivacyPreferenceRepository
from app.domain.interfaces.image_storage import IImageStorageProvider
from app.domain.interfaces.repositories import IConversationRepository, IUserRepository
from app.domain.interfaces.session import IDbSession
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.models.privacy import MemoryPrivacyPolicy


class MemoryPolicyService:
    """Owns consent transitions and their derived-memory revocation effect."""

    def __init__(
        self,
        *,
        user_repo_factory: Callable[[IDbSession], IUserRepository],
        conversation_repo_factory: Callable[[IDbSession], IConversationRepository],
        privacy_repo_factory: Callable[[IDbSession], IPrivacyPreferenceRepository],
        vector_store: IVectorStore,
        image_storage: IImageStorageProvider,
    ) -> None:
        self._user_repo_factory = user_repo_factory
        self._conversation_repo_factory = conversation_repo_factory
        self._privacy_repo_factory = privacy_repo_factory
        self._vector_store = vector_store
        self._image_storage = image_storage

    async def get(self, session: IDbSession, user_id: uuid.UUID) -> MemoryPrivacyPolicy:
        return await self._privacy_repo_factory(session).get_memory_policy(user_id)

    async def update(
        self,
        session: IDbSession,
        user_id: uuid.UUID,
        *,
        enabled: bool,
        retention_days: int | None,
    ) -> MemoryPrivacyPolicy:
        if enabled and retention_days is None:
            raise ValueError("retention_days is required when enabling long-term memory")
        if not enabled:
            retention_days = None

        await self._user_repo_factory(session).get_or_create_user(user_id)
        policy = await self._privacy_repo_factory(session).set_memory_policy(
            user_id,
            enabled=enabled,
            retention_days=retention_days,
            changed_at=datetime.now(UTC),
        )
        if not policy.allows_long_term_memory:
            # Revocation is fail-closed: do not report a successful withdrawal
            # before the active derived memory has actually been removed.
            for collection in ("memories", "image_memories", "guild_memories"):
                await self._vector_store.delete_by_user(collection, str(user_id))
            image_ids = await self._conversation_repo_factory(session).get_image_ids_for_user(user_id)
            for image_id in image_ids:
                await self._image_storage.delete_image(image_id)
        return policy
