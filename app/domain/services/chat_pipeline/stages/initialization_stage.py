import math
from typing import Callable
from app.domain.interfaces.session import IDbSession

from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.interfaces.repositories import IUserRepository, IEmotionRepository, IConversationRepository
from app.shared.utils.user_identity import normalize_user_id
from app.shared.utils.logger import get_logger
from app.domain.context import request_question_idx, request_turn_idx

log = get_logger(__name__)

class InitializationStage(PipelineStage):
    """
    Stage 1: Initialize repositories, load context,
    and compute initial emotion/attachment baseline.
    """
    def __init__(
        self,
        user_repo_factory: Callable[[IDbSession], IUserRepository],
        emotion_repo_factory: Callable[[IDbSession], IEmotionRepository],
        conv_repo_factory: Callable[[IDbSession], IConversationRepository],
    ):
        self.user_repo_factory = user_repo_factory
        self.emotion_repo_factory = emotion_repo_factory
        self.conv_repo_factory = conv_repo_factory

    async def process(self, context: ChatContext) -> ChatContext:
        user_uuid = normalize_user_id(context.user_id)
        user_repo = self.user_repo_factory(context.session)
        emotion_repo = self.emotion_repo_factory(context.session)
        conv_repo = self.conv_repo_factory(context.session)
        
        # 1. Ensure user exists first (FK constraint)
        await user_repo.get_or_create_user(user_uuid)

        # 2. Sequentialize independent user stats, emotion state, and conversation ID reads (SQLAlchemy session is not thread-safe)
        stats = await user_repo.get_user_stats(user_uuid)
        emotion = await emotion_repo.get_emotion_state(user_uuid)
        conv_id = await conv_repo.get_or_create_conversation(user_uuid)

        # 3. Sequentialize conversation history and summary reads
        history = await conv_repo.get_recent_history(user_uuid, conv_id, limit=40)
        summary = await conv_repo.get_latest_summary(user_uuid, conv_id)

        # Initialize ContextVars for request-scoped logging
        question_idx = len([m for m in history if m.get("role") == "user"]) + 1
        request_question_idx.set(question_idx)
        request_turn_idx.set(1)
        
        # Formulate Attachment Bonus and current emotions snapshot
        attachment_bonus_raw = math.log(max(1, stats.interaction_count)) * 0.05
        current_emotions = {
            "joy": emotion.joy,
            "sadness": emotion.sadness,
            "trust": emotion.trust,
            "irritation": emotion.irritation,
            "attachment": emotion.attachment + attachment_bonus_raw
        }

        # Update context
        context.user_uuid = user_uuid
        context.conv_id = conv_id
        context.stats = stats
        context.emotion = emotion
        context.history = history
        context.conversation_summary = summary
        context.attachment_bonus_raw = attachment_bonus_raw
        context.current_emotions = current_emotions

        # PH-001: Explicitly commit to release the initial read connection back to the pool
        # before the pipeline proceeds to external network LLM calls.
        if hasattr(context.session, "commit"):
            await context.session.commit()

        return context
