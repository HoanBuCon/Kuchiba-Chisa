import uuid
from typing import Callable, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.interfaces.uow import IUnitOfWork
from app.domain.interfaces.repositories import IUserRepository, IEmotionRepository, IConversationRepository
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.interfaces.cache_provider import ICacheProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class ClearUserMemoryUseCase:
    """
    Application Use Case to wipe all conversation memory (STM + LTM),
    invalidate Redis State Cache, and reset emotion/stats for a user.
    """

    def __init__(
        self,
        uow_factory: Callable[[AsyncSession], IUnitOfWork],
        user_repo_factory: Callable[[AsyncSession], IUserRepository],
        emotion_repo_factory: Callable[[AsyncSession], IEmotionRepository],
        conv_repo_factory: Callable[[AsyncSession], IConversationRepository],
        vector_store: IVectorStore,
        cache_provider: Optional[ICacheProvider] = None,
    ):
        self.uow_factory = uow_factory
        self.user_repo_factory = user_repo_factory
        self.emotion_repo_factory = emotion_repo_factory
        self.conv_repo_factory = conv_repo_factory
        self.vector_store = vector_store
        self.cache_provider = cache_provider

    async def execute(self, session: AsyncSession, user_id: str) -> None:
        from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str
        user_uuid = normalize_user_id(user_id)
        canonical_user_id = normalize_user_id_str(user_id)
        
        # 1. PostgreSQL deletes via UoW and repositories
        async with self.uow_factory(session) as uow:
            await self.conv_repo_factory(session).delete_all_for_user(user_uuid)
            await self.emotion_repo_factory(session).delete_all_for_user(user_uuid)
            await self.user_repo_factory(session).delete_all_for_user(user_uuid)
            
        # 2. Redis State & Summary Cache Invalidation
        if self.cache_provider:
            from app.domain.services.user_state_cache import UserStateCache
            await UserStateCache.invalidate(self.cache_provider, user_uuid)
            await self.cache_provider.delete(f"chisa:user:{user_uuid}:summary")
            if canonical_user_id != str(user_uuid):
                await UserStateCache.invalidate(self.cache_provider, canonical_user_id)
                await self.cache_provider.delete(f"chisa:user:{canonical_user_id}:summary")

        # 3. Qdrant deletes via vector store
        from app.infrastructure.vector.qdrant.qdrant_service import COLLECTION_MEMORIES
        collections = [COLLECTION_MEMORIES]
        for col in collections:
            try:
                await self.vector_store.delete_by_user(col, canonical_user_id)
            except Exception as e:
                log.warning("Could not clear Qdrant collection", collection=col, error=str(e))
        log.info("User memory and state cache cleared completely via ClearUserMemoryUseCase", user_id=user_id)
