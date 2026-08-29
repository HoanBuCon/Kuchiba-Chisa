from typing import Callable, Optional
from app.domain.interfaces.session import IDbSession

from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.interfaces.repositories import IUserRepository, IEmotionRepository, IConversationRepository
from app.domain.interfaces.tracker import IPipelineTracker
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
        pipeline_tracker: Optional[IPipelineTracker] = None,
    ):
        self.user_repo_factory = user_repo_factory
        self.emotion_repo_factory = emotion_repo_factory
        self.conv_repo_factory = conv_repo_factory
        self.pipeline_tracker = pipeline_tracker


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
        if context.is_community:
            history = []
            summary = None
            if context.recent_community_messages and not context.channel_transcript:
                from app.domain.services.community.transcript_formatter import ChannelTranscriptFormatter
                context.channel_transcript = ChannelTranscriptFormatter.format_transcript(context.recent_community_messages)
        else:
            history = await conv_repo.get_recent_history(user_uuid, conv_id, limit=40)
            summary = await conv_repo.get_latest_summary(user_uuid, conv_id)

        # Initialize ContextVars for request-scoped logging
        question_idx = len([m for m in history if m.get("role") == "user"]) + 1
        request_question_idx.set(question_idx)
        request_turn_idx.set(1)
        
        # Single Source of Truth for emotions
        attachment_bonus_raw = 0.0
        current_emotions = {
            "joy": emotion.joy,
            "sadness": emotion.sadness,
            "trust": emotion.trust,
            "irritation": emotion.irritation,
            "attachment": emotion.attachment,
            "shyness": getattr(emotion, "shyness", 0.0),
            "curiosity": getattr(emotion, "curiosity", 0.20),
            "comfort": getattr(emotion, "comfort", 0.50),
        }

        # Update context
        context.user_uuid = user_uuid
        context.conv_id = conv_id
        context.stats = stats
        context.emotion = emotion
        context.history = history
        context.conversation_summary = summary
        context.attachment_bonus_raw = 0.0
        context.current_emotions = current_emotions

        if self.pipeline_tracker:
            self.pipeline_tracker.add_step(
                name="initialization",
                stage_id="stage_1_init",
                depth=0,
                category="stage_root",
                title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh",
                subtitle=f"Load stats, profile · Turn #{question_idx} ({context.user_id[:8]}...)",
                data={
                    "user_uuid": user_uuid,
                    "user_id": context.user_id,
                    "conv_id": str(conv_id) if conv_id else None,
                    "turn_index": question_idx,
                    "interaction_count": stats.interaction_count,
                    "history_count": len(history),
                    "has_summary": bool(summary),
                    "summary_preview": (summary[:200] + "...") if summary and len(summary) > 200 else summary,
                    "current_emotions": current_emotions,
                    "baseline_emotions": current_emotions,
                    "attachment_bonus_raw": round(attachment_bonus_raw, 4),
                    "status": "success"
                }
            )

        # PH-001: Explicitly commit to release the initial read connection back to the pool
        # before the pipeline proceeds to external network LLM calls.
        if hasattr(context.session, "commit"):
            await context.session.commit()

        return context

