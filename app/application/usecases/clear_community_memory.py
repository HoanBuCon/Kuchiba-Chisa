from typing import Optional
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.interfaces.cache_provider import ICacheProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class ClearCommunityMemoryUseCase:
    """
    Application Use Case to wipe Community / Shared Server Memory:
    - Qdrant guild_memories (guild_id)
    - Redis ambient mood (chisa:guild:{guild_id}:ambient_mood)
    - Redis channel topic summaries (chisa:channel:*:topic_summary)
    """

    def __init__(
        self,
        vector_store: IVectorStore,
        cache_provider: Optional[ICacheProvider] = None,
    ):
        self.vector_store = vector_store
        self.cache_provider = cache_provider

    async def execute(
        self,
        guild_id: str,
        scope: str = "all",
        channel_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> dict:
        from app.infrastructure.vector.qdrant.qdrant_service import COLLECTION_GUILD_MEMORIES, COLLECTION_MEMORIES
        from app.shared.utils.user_identity import normalize_user_id_str

        cleared_details = {
            "guild_id": guild_id,
            "scope": scope,
            "guild_memories_cleared": False,
            "ambient_mood_cleared": False,
            "topic_summaries_cleared": 0,
            "user_memories_cleared": False,
        }

        if scope == "all":
            # 1. Clear all guild_memories for this guild
            try:
                await self.vector_store.delete_by_guild(COLLECTION_GUILD_MEMORIES, str(guild_id))
                cleared_details["guild_memories_cleared"] = True
            except Exception as e:
                log.warning("Could not clear Qdrant guild_memories", guild_id=guild_id, error=str(e))

            # 2. Clear Redis ambient mood and topic summaries
            if self.cache_provider:
                try:
                    await self.cache_provider.delete(f"chisa:guild:{guild_id}:ambient_mood")
                    cleared_details["ambient_mood_cleared"] = True
                except Exception as e:
                    log.warning("Could not clear Redis ambient mood", guild_id=guild_id, error=str(e))

                try:
                    deleted_count = await self.cache_provider.delete_pattern("chisa:channel:*:topic_summary")
                    await self.cache_provider.delete_pattern("chisa:channel:*:rolling_buffer")
                    await self.cache_provider.delete_pattern("chisa:channel:*:msg_count")
                    cleared_details["topic_summaries_cleared"] = deleted_count
                except Exception as e:
                    log.warning("Could not clear Redis topic summaries or rolling buffers", error=str(e))

            log.info("Server-wide community memory cleared", guild_id=guild_id)
        else:
            # scope == "self"
            if user_id:
                canonical_user_id = normalize_user_id_str(user_id)
                try:
                    await self.vector_store.delete_by_user(COLLECTION_MEMORIES, canonical_user_id)
                    cleared_details["user_memories_cleared"] = True
                except Exception as e:
                    log.warning("Could not clear user memory in community scope", user_id=user_id, error=str(e))

        return cleared_details
