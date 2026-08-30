import hashlib
from typing import Optional
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.tracker import IPipelineTracker
from app.domain.services.intent_classifier import ChatIntent
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class CacheStage(PipelineStage):
    """
    Stage 3: Checks Redis for a cached answer if the query is purely LORE.
    If a cache hit occurs, flags the context so subsequent heavy stages are skipped.
    """
    def __init__(self, cache: ICacheProvider, pipeline_tracker: Optional[IPipelineTracker] = None):
        self.cache = cache
        self.pipeline_tracker = pipeline_tracker

    async def process(self, context: ChatContext) -> ChatContext:
        cache_key = None
        is_lore_only = len(context.intents) == 1 and context.intents[0] == ChatIntent.LORE and not context.is_small_talk and not context.has_images
        
        # Only cache if intent is exclusively LORE (no SYSTEM_ACTION or MEMORY or Images)
        if is_lore_only:
            from app.shared.utils.fallback_detector import is_fallback_reply
            query_hash = hashlib.md5(context.cleaned_query.encode()).hexdigest()
            cache_key = f"chisa:answer_cache:lore:{query_hash}"
            cached_answer = await self.cache.get(cache_key)
            if cached_answer:
                if is_fallback_reply(cached_answer):
                    log.warning("Lore cache contains fallback/error reply. Invalidating key", cache_key=cache_key)
                    await self.cache.delete(cache_key)
                else:
                    log.info("Answer cache hit", cache_key=cache_key)
                    context.is_cached_answer = True
                    context.chisa_reply = cached_answer

        if self.pipeline_tracker:
            hit = bool(context.is_cached_answer)
            status_val = "cached" if hit else "skipped"
            sub_title = "⚡ Cache HIT (Bỏ qua RAG & trả lời tức thì)" if hit else (
                "⚪ Cache MISS (Chuyển tiếp RAG Pipeline)" if is_lore_only else "⚪ Bỏ qua Cache (Non-Lore query)"
            )
            self.pipeline_tracker.add_step(
                name="cache_check",
                stage_id="stage_3_cache",
                depth=0,
                category="stage_root",
                status=status_val,
                title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm (Redis Answer Cache)",
                subtitle=sub_title,
                data={
                    "hit": hit,
                    "is_hit": hit,
                    "cache_key": cache_key,
                    "cached_answer": context.chisa_reply if hit else None,
                    "is_lore_only": is_lore_only,
                    "status": "hit" if hit else "miss",
                }
            )
                
        return context

