from typing import Callable, Coroutine, Any
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.memory_extractor import MemoryExtractor
from app.shared.utils.background_tasks import BackgroundTaskManager
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class BackgroundTaskStage(PipelineStage):
    """
    Stage 9: Spawn background tasks for memory extraction and period summarization.
    """
    def __init__(
        self,
        memory_extractor: MemoryExtractor,
        unified_auto_summarize_callback: Callable[[str, str], Coroutine[Any, Any, None]]
    ):
        self.memory_extractor = memory_extractor
        self.unified_auto_summarize_callback = unified_auto_summarize_callback

    async def process(self, context: ChatContext) -> ChatContext:
        # Trigger background fact extraction (tracked task) for non-small-talk messages
        if not context.is_small_talk:
            BackgroundTaskManager.spawn(
                self.memory_extractor.extract_and_store(
                    user_id=context.user_id,
                    conversation_id=str(context.conv_id),
                    user_message=context.user_message
                ),
                name=f"memory_extract:{context.user_id}",
            )
        else:
            log.debug("Skipping memory extraction for small talk message", user_id=context.user_id)
        
        # Periodically trigger unified background auto-summarization (every 10 interactions)
        if context.stats.interaction_count > 0 and context.stats.interaction_count % 10 == 0:
            BackgroundTaskManager.spawn(
                self.unified_auto_summarize_callback(
                    context.user_id,
                    str(context.conv_id)
                ),
                name=f"unified_auto_summarize:{context.user_id}",
            )
            
        log.info("ChatPipeline cycle complete", user_id=context.user_id)
        return context
