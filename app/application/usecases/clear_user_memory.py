import uuid
from typing import Callable
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.uow import IUnitOfWork
from app.domain.interfaces.repositories import IUserRepository, IEmotionRepository, IConversationRepository
from app.domain.interfaces.vector_store import IVectorStore
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class ClearUserMemoryUseCase:
    """
    Application Use Case to wipe all conversation memory (STM + LTM) 
    and reset emotion/stats for a user.
    """

    def __init__(
        self,
        uow_factory: Callable[[AsyncSession], IUnitOfWork],
        user_repo_factory: Callable[[AsyncSession], IUserRepository],
        emotion_repo_factory: Callable[[AsyncSession], IEmotionRepository],
        conv_repo_factory: Callable[[AsyncSession], IConversationRepository],
        vector_store: IVectorStore,
    ):
        self.uow_factory = uow_factory
        self.user_repo_factory = user_repo_factory
        self.emotion_repo_factory = emotion_repo_factory
        self.conv_repo_factory = conv_repo_factory
        self.vector_store = vector_store

    async def execute(self, session: AsyncSession, user_id: str) -> None:
        from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str
        user_uuid = normalize_user_id(user_id)
        canonical_user_id = normalize_user_id_str(user_id)
        
        # 1. PostgreSQL deletes via UoW and repositories
        async with self.uow_factory(session) as uow:
            await self.conv_repo_factory(session).delete_all_for_user(user_uuid)
            await self.emotion_repo_factory(session).delete_all_for_user(user_uuid)
            await self.user_repo_factory(session).delete_all_for_user(user_uuid)
            
        # 2. Qdrant deletes via vector store
        collections = ["emotional_memories", "conversation_summaries", "persona_embeddings", "user_facts", "memories"]
        for col in collections:
            try:
                await self.vector_store.delete_by_user(col, canonical_user_id)
            except Exception as e:
                log.warning("Could not clear Qdrant collection", collection=col, error=str(e))
        log.info("User memory cleared completely via ClearUserMemoryUseCase", user_id=user_id)
