import time
from typing import Callable
from app.domain.interfaces.session import IDbSession
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.interfaces.repositories import IUserRepository, IConversationRepository

class PersistenceStage(PipelineStage):
    """
    Stage 8: Save messages to Postgres and update user stats.
    """
    def __init__(
        self,
        user_repo_factory: Callable[[IDbSession], IUserRepository],
        conv_repo_factory: Callable[[IDbSession], IConversationRepository]
    ):
        self.user_repo_factory = user_repo_factory
        self.conv_repo_factory = conv_repo_factory

    async def process(self, context: ChatContext) -> ChatContext:
        user_repo = self.user_repo_factory(context.session)
        conv_repo = self.conv_repo_factory(context.session)

        total_tokens = context.estimated_input_tokens + context.estimated_output_tokens
        await conv_repo.save_message(context.conv_id, context.user_uuid, "user", context.user_message, is_success=True)
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

        return context
