import hashlib
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.services.intent_classifier import ChatIntent
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class CacheStage(PipelineStage):
    """
    Checks Redis for a cached answer if the query is purely LORE.
    If a cache hit occurs, flags the context so subsequent heavy stages are skipped.
    """
    def __init__(self, cache: ICacheProvider):
        self.cache = cache

    async def process(self, context: ChatContext) -> ChatContext:
        # Only cache if intent is exclusively LORE (no SYSTEM_ACTION or MEMORY)
        if len(context.intents) == 1 and context.intents[0] == ChatIntent.LORE and not context.is_small_talk:
            query_hash = hashlib.md5(context.cleaned_query.encode()).hexdigest()
            cache_key = f"chisa:answer_cache:lore:{query_hash}"
            cached_answer = await self.cache.get(cache_key)
            if cached_answer:
                log.info("Answer cache hit", cache_key=cache_key)
                context.is_cached_answer = True
                context.chisa_reply = cached_answer
                
        return context
