import time
from typing import Callable, Optional
from app.domain.interfaces.session import IDbSession
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.interfaces.repositories import IUserRepository, IConversationRepository
from app.domain.interfaces.tracker import IPipelineTracker

class PersistenceStage(PipelineStage):
    """
    Stage 9: Save messages to Postgres and update user stats.
    """
    def __init__(
        self,
        user_repo_factory: Callable[[IDbSession], IUserRepository],
        conv_repo_factory: Callable[[IDbSession], IConversationRepository],
        pipeline_tracker: Optional[IPipelineTracker] = None
    ):
        self.user_repo_factory = user_repo_factory
        self.conv_repo_factory = conv_repo_factory
        self.pipeline_tracker = pipeline_tracker

    async def process(self, context: ChatContext) -> ChatContext:
        user_repo = self.user_repo_factory(context.session)
        conv_repo = self.conv_repo_factory(context.session)

        total_tokens = context.estimated_input_tokens + context.estimated_output_tokens
        user_rw = context.rewritten_query or context.cleaned_query or None
        await conv_repo.save_message(
            context.conv_id,
            context.user_uuid,
            "user",
            context.user_message,
            rewritten_content=user_rw,
            is_success=True
        )
        await conv_repo.save_message(
            context.conv_id,
            context.user_uuid,
            "assistant",
            context.chisa_reply,
            token_count=total_tokens,
            is_success=True
        )
        
        context.stats.interaction_count += 1
        context.stats.last_seen = int(time.time() * 1000)
        await user_repo.update_stats(context.stats)

        if self.pipeline_tracker:
            self.pipeline_tracker.add_step(
                name="persistence",
                stage_id="stage_9_persist",
                depth=0,
                category="stage_root",
                status="success",
                title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững",
                subtitle=f"Lưu tin nhắn SQL · Interaction #{context.stats.interaction_count} · {total_tokens} tokens",
                data={
                    "conv_id": str(context.conv_id) if context.conv_id else None,
                    "user_uuid": context.user_uuid,
                    "user_message_length": len(context.user_message) if context.user_message else 0,
                    "assistant_reply_length": len(context.chisa_reply) if context.chisa_reply else 0,
                    "interaction_count": context.stats.interaction_count,
                    "last_seen": context.stats.last_seen,
                    "total_tokens_persisted": total_tokens,
                    "status": "success"
                }
            )

        return context

