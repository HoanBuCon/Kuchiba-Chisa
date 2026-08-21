from typing import Callable, Coroutine, Any, Optional
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.memory_extractor import MemoryExtractor
from app.domain.interfaces.tracker import IPipelineTracker
from app.shared.utils.background_tasks import BackgroundTaskManager
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class BackgroundTaskStage(PipelineStage):
    """
    Stage 10: Spawn background tasks for memory extraction and period summarization.
    """
    def __init__(
        self,
        memory_extractor: MemoryExtractor,
        unified_auto_summarize_callback: Callable[[str, str], Coroutine[Any, Any, None]],
        pipeline_tracker: Optional[IPipelineTracker] = None
    ):
        self.memory_extractor = memory_extractor
        self.unified_auto_summarize_callback = unified_auto_summarize_callback
        self.pipeline_tracker = pipeline_tracker

    async def process(self, context: ChatContext) -> ChatContext:
        triggered_extract = bool(context.stats and context.stats.interaction_count > 0 and context.stats.interaction_count % 3 == 0)
        triggered_summary = bool(context.stats and context.stats.interaction_count > 0 and context.stats.interaction_count % 10 == 0)

        # Trigger batched background fact extraction every 3 interaction turns (batch of 3 pairs + 2 context msgs)
        if triggered_extract:
            BackgroundTaskManager.spawn(
                self.memory_extractor.extract_and_store_batch(
                    user_id=context.user_id,
                    conversation_id=str(context.conv_id),
                    history=context.history,
                    current_user_message=context.user_message,
                    current_assistant_reply=context.chisa_reply,
                ),
                name=f"memory_extract_batch:{context.user_id}",
            )
        else:
            log.debug("Skipping batch memory extraction (runs every 3 turns)", user_id=context.user_id, count=getattr(context.stats, 'interaction_count', 0))
        
        # Periodically trigger unified background auto-summarization (every 10 interactions)
        if triggered_summary:
            BackgroundTaskManager.spawn(
                self.unified_auto_summarize_callback(
                    context.user_id,
                    str(context.conv_id)
                ),
                name=f"unified_auto_summarize:{context.user_id}",
            )

        if self.pipeline_tracker:
            extract_desc = "Kích hoạt" if triggered_extract else "Bỏ qua (chờ chu kỳ 3 lượt)"
            summary_desc = "Kích hoạt" if triggered_summary else "Bỏ qua (chờ chu kỳ 10 lượt)"
            self.pipeline_tracker.add_step(
                name="background_tasks",
                stage_id="stage_10_bg",
                depth=0,
                category="stage_root",
                status="success",
                title="Stage 10: [BACKGROUND] Tác vụ Nền Tự động",
                subtitle=f"Batch Memories ({extract_desc}) · Auto-Summarize ({summary_desc})",
                data={
                    "interaction_count": getattr(context.stats, 'interaction_count', 0),
                    "batch_memory_extraction_triggered": triggered_extract,
                    "batch_memory_interval": 3,
                    "auto_summarization_triggered": triggered_summary,
                    "auto_summary_interval": 10,
                    "status": "success"
                }
            )
            
        log.info("ChatPipeline cycle complete", user_id=context.user_id)
        return context

