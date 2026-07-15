import hashlib
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.services.intent_classifier import ChatIntent
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class CacheUpdateStage(PipelineStage):
    """
    Saves the generated answer to Redis if the query was purely LORE and not already cached.
    """
    def __init__(self, cache: ICacheProvider):
        self.cache = cache

    async def process(self, context: ChatContext) -> ChatContext:
        if context.is_cached_answer:
            return context
            
        if len(context.intents) == 1 and context.intents[0] == ChatIntent.LORE and not context.is_small_talk:
            if context.chisa_reply:
                query_hash = hashlib.md5(context.cleaned_query.encode()).hexdigest()
                cache_key = f"chisa:answer_cache:lore:{query_hash}"
                # Cache for 24 hours
                await self.cache.set(cache_key, context.chisa_reply, ttl=86400)
                log.info("Saved answer to cache", cache_key=cache_key)
                
        return context
