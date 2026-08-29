from __future__ import annotations
import time
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from app.domain.entities.community import CommunityChatContext, CommunityMessage
from app.domain.entities.emotion import EmotionState
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.interfaces.repositories import IConversationRepository, IEmotionRepository, IUserRepository
from app.domain.interfaces.session import IDbSession
from app.domain.services.budget_mode import BudgetMode
from app.domain.services.community.community_context_builder import CommunityContextBuilder
from app.domain.services.community.transcript_formatter import ChannelTranscriptFormatter
from app.domain.services.emotion_engine import EmotionEngine
from app.domain.services.rag.pipeline import RAGPipeline
from app.shared.utils.json_parser import robust_parse_json
from app.shared.utils.logger import get_logger
from app.shared.utils.user_identity import normalize_user_id

log = get_logger(__name__)


class CommunityChatPipeline:
    """
    Independent RAG pipeline for multi-user community channels.
    Provides speaker attribution, transcript windowing, and group dialogue persona.
    """

    def __init__(
        self,
        llm: BaseLLMAdapter,
        retrieval_pipeline: Optional[RAGPipeline] = None,
        context_builder: Optional[CommunityContextBuilder] = None,
        emotion_engine: Optional[EmotionEngine] = None,
    ):
        self.llm = llm
        self.retrieval_pipeline = retrieval_pipeline
        self.context_builder = context_builder or CommunityContextBuilder()
        self.emotion_engine = emotion_engine or EmotionEngine()

    async def execute(
        self,
        session: IDbSession,
        channel_id: str,
        current_speaker_id: str,
        current_speaker_name: str,
        user_message: str,
        recent_messages: List[CommunityMessage],
        guild_id: Optional[str] = None,
        channel_name: str = "general",
        guild_name: Optional[str] = None,
        user_repo: Optional[IUserRepository] = None,
        emotion_repo: Optional[IEmotionRepository] = None,
        conv_repo: Optional[IConversationRepository] = None,
        on_token: Optional[Callable[[str], Any]] = None,
    ) -> CommunityChatContext:
        start_time = time.time()
        speaker_uuid = normalize_user_id(current_speaker_id)

        context = CommunityChatContext(
            channel_id=channel_id,
            guild_id=guild_id,
            channel_name=channel_name,
            current_speaker_id=current_speaker_id,
            current_speaker_name=current_speaker_name,
            user_message=user_message,
            user_uuid=speaker_uuid,
            recent_messages=recent_messages,
        )

        # ── 1. Initialization Stage: Speaker State & Transcript ──
        if user_repo:
            await user_repo.get_or_create_user(speaker_uuid)
            context.speaker_stats = await user_repo.get_user_stats(speaker_uuid)

        if emotion_repo:
            context.speaker_emotion = await emotion_repo.get_emotion_state(speaker_uuid)
        else:
            context.speaker_emotion = EmotionState(user_id=speaker_uuid)

        context.formatted_transcript = ChannelTranscriptFormatter.format_transcript(
            messages=recent_messages,
            max_tokens=1200,
            token_estimator=self.context_builder.token_estimator,
        )

        # ── 2. Retrieval Stage: Lore & Speaker Memory ──
        lore_chunks: List[str] = []
        memories: List[str] = []
        if self.retrieval_pipeline:
            try:
                rag_result = await self.retrieval_pipeline.retrieve(
                    query=user_message,
                    user_id=speaker_uuid,
                    session=session,
                    max_lore=4,
                    max_memory=3,
                )
                context.rag_context = rag_result
                lore_chunks = [c.content for c in rag_result.lore_chunks]
                memories = [m.content for m in rag_result.memories]
            except Exception as e:
                log.warning("Community retrieval failed, proceeding without RAG context", error=str(e))

        # ── 3. Context Building Stage ──
        build_result = self.context_builder.build(
            speaker_emotion=context.speaker_emotion,
            current_speaker_name=current_speaker_name,
            channel_name=channel_name,
            transcript=context.formatted_transcript,
            user_message=user_message,
            memories=memories,
            lore=lore_chunks,
            guild_name=guild_name,
            budget_mode=BudgetMode.RAG,
        )
        context.prompt = build_result.prompt
        context.budget_audit = build_result.audit.__dict__ if hasattr(build_result.audit, "__dict__") else {}

        # ── 4. Generation Stage ──
        raw_response = await self.llm.generate(context.prompt, on_token=on_token)
        context.raw_llm_response = raw_response

        # ── 5. Output Extraction & DEHA 3.1 Emotion Update ──
        parsed_payload = robust_parse_json(raw_response)
        reply_text = parsed_payload.get("response") or raw_response
        sentiment_data = parsed_payload.get("sentiment") or {
            "reaction": "calm_warmth",
            "user_stance": "neutral",
            "intensity": 0.3,
            "variance": 0.0,
        }

        context.cleaned_response = reply_text
        context.extracted_sentiment = sentiment_data

        # Update Speaker Emotion with DEHA 3.1
        self.emotion_engine.update(context.speaker_emotion, sentiment_analysis=sentiment_data)
        if emotion_repo:
            await emotion_repo.save_emotion_state(context.speaker_emotion)

        if user_repo:
            await user_repo.increment_interaction_count(speaker_uuid)

        context.updated_speaker_emotions = {
            "joy": context.speaker_emotion.joy,
            "sadness": context.speaker_emotion.sadness,
            "trust": context.speaker_emotion.trust,
            "irritation": context.speaker_emotion.irritation,
            "attachment": context.speaker_emotion.attachment,
            "shyness": getattr(context.speaker_emotion, "shyness", 0.0),
            "curiosity": getattr(context.speaker_emotion, "curiosity", 0.20),
            "comfort": getattr(context.speaker_emotion, "comfort", 0.50),
        }

        context.execution_time_ms = (time.time() - start_time) * 1000
        return context
