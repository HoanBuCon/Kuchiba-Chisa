from typing import Callable, Optional
from app.domain.interfaces.session import IDbSession

from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.interfaces.repositories import IUserRepository, IEmotionRepository, IConversationRepository
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.tracker import IPipelineTracker
from app.shared.utils.user_identity import normalize_user_id
from app.shared.utils.logger import get_logger
from app.domain.context import request_question_idx, request_turn_idx

log = get_logger(__name__)

class InitializationStage(PipelineStage):
    """
    Stage 1: Initialize repositories, load context,
    and compute initial emotion/attachment baseline with
    Dual-Layer Ambient Social & Cross-Channel Residual Dynamics.
    """
    def __init__(
        self,
        user_repo_factory: Callable[[IDbSession], IUserRepository],
        emotion_repo_factory: Callable[[IDbSession], IEmotionRepository],
        conv_repo_factory: Callable[[IDbSession], IConversationRepository],
        cache_provider: Optional[ICacheProvider] = None,
        pipeline_tracker: Optional[IPipelineTracker] = None,
    ):
        self.user_repo_factory = user_repo_factory
        self.emotion_repo_factory = emotion_repo_factory
        self.conv_repo_factory = conv_repo_factory
        self.cache_provider = cache_provider
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

        # 4. Server-Level Holistic Ambient Emotion Dynamics (Continuous Exponential Decay)
        is_server_shared = (
            bool(context.guild_id)
            and not context.guild_id.startswith("CHANNEL_")
            and context.guild_id != "DM"
        )
        if is_server_shared and self.cache_provider:
            from app.domain.services.community.ambient_manager import AmbientMoodManager
            cache_key = f"chisa:guild:{context.guild_id}:ambient_mood"
            stored_ambient = await self.cache_provider.get_json(cache_key)
            decayed_ambient = AmbientMoodManager.calculate_decay(stored_ambient)
            
            # Synthesize transient ambient channels into current emotion state (preserving individual Trust & Attachment)
            AmbientMoodManager.synthesize_ambient_into_emotion(emotion, decayed_ambient)
            context.recent_social_trace = decayed_ambient
            context.ambient_context = AmbientMoodManager.describe_ambient_mood(decayed_ambient)

            # Load rolling community topic summary from Redis if available
            if context.channel_id:
                try:
                    summary_key = f"chisa:channel:{context.channel_id}:topic_summary"
                    stored_summary = await self.cache_provider.get(summary_key)
                    if stored_summary:
                        context.topic_summary = stored_summary.strip()
                except Exception as ts_err:
                    log.warning("Failed to load topic summary in InitializationStage", error=str(ts_err))

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
            "curiosity": getattr(emotion, "curiosity", 0.10),
            "comfort": getattr(emotion, "comfort", 0.50),
        }

        # 5. Process Image Inputs (if any) via ImageIngestionService
        if context.images:
            from app.domain.services.image_ingestion import ImageIngestionService
            ingestion_service = ImageIngestionService()
            try:
                processed_images = await ingestion_service.ingest_images(
                    image_inputs=context.images,
                    save_to_disk=True,
                    is_ephemeral=False,
                )
                context.processed_images = processed_images
                context.has_images = len(processed_images) > 0
                context.images_processed = processed_images
            except Exception as img_err:
                log.error("Failed to process images in InitializationStage", error=str(img_err))
                context.has_images = False

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
            if not context.trace_id:
                current_trace = self.pipeline_tracker.get_current_trace()
                if current_trace:
                    context.trace_id = current_trace.get("id")
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
                    "speaker_name": context.speaker_name,
                    "is_community": context.is_community,
                    "channel_name": context.channel_name,
                    "guild_name": context.guild_name,
                    "conv_id": str(conv_id) if conv_id else None,
                    "turn_index": question_idx,
                    "interaction_count": stats.interaction_count,
                    "history_count": len(history),
                    "has_summary": bool(summary),
                    "summary_preview": (summary[:200] + "...") if summary and len(summary) > 200 else summary,
                    "topic_summary": context.topic_summary,
                    "topic_summary_preview": (context.topic_summary[:200] + "...") if context.topic_summary and len(context.topic_summary) > 200 else context.topic_summary,
                    "current_emotions": current_emotions,
                    "initial_emotions": current_emotions,
                    "baseline_emotions": current_emotions,
                    "ambient_mood": context.recent_social_trace,
                    "channel_transcript_preview": (context.channel_transcript[:300] + "...") if context.channel_transcript and len(context.channel_transcript) > 300 else context.channel_transcript,
                    "attachment_bonus_raw": round(attachment_bonus_raw, 4),
                    "has_images": context.has_images,
                    "images_count": len(context.processed_images),
                    "processed_images": [
                        {
                            "image_id": img.get("image_id"),
                            "url": img.get("url"),
                            "thumbnail_url": img.get("thumbnail_url") or img.get("thumbnail_data_uri"),
                            "thumbnail_data_uri": img.get("thumbnail_data_uri"),
                            "width": img.get("width"),
                            "height": img.get("height"),
                            "size_bytes": img.get("size_bytes"),
                            "is_ephemeral": img.get("is_ephemeral"),
                        }
                        for img in context.processed_images
                    ],
                    "status": "success"
                }
            )

        # PH-001: Explicitly commit to release the initial read connection back to the pool
        # before the pipeline proceeds to external network LLM calls.
        if hasattr(context.session, "commit"):
            await context.session.commit()

        return context

