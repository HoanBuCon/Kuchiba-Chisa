from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from app.domain.entities.emotion import EmotionState
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.repositories import (
    IConversationRepository,
    IEmotionRepository,
    IUserRepository,
)
from app.domain.interfaces.session import IDbSession
from app.domain.interfaces.uow import IUnitOfWork
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.services.attachment_manifest import AttachmentManifest
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class ChatEngineBusyError(Exception):
    """Raised when a user's chat request is already being processed (per-user lock not acquired)."""
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"Chat engine busy for user {user_id} — concurrent request rejected")

@dataclass(frozen=True)
class ChatExecutionResult:
    """Typed terminal chat state; citations are server-validated evidence IDs."""

    reply_text: str
    emotions: dict[str, float]
    images_processed: list[dict[str, Any]]
    attached_images: list[AttachmentManifest]
    citation_ids: list[str]

    def legacy_tuple(
        self,
    ) -> tuple[str, dict[str, float], list[dict[str, Any]], list[AttachmentManifest]]:
        """Preserve the internal legacy call contract while API callers migrate."""
        return self.reply_text, self.emotions, self.images_processed, self.attached_images


class ChatPipeline:
    def __init__(self, stages: list[PipelineStage]):
        self.stages = stages

    async def execute(self, context: ChatContext) -> ChatContext:
        for stage in self.stages:
            context = await stage.process(context)
        return context

class ChatEngine:
    """
    Production-grade chat orchestrator using Phase 1-10 pipeline.
    This is now a facade over the ChatPipeline.
    """
    def __init__(
        self,
        pipeline: ChatPipeline,
        uow_factory: Callable[[IDbSession], IUnitOfWork],
        cache_provider: ICacheProvider,
        emotion_repo_factory: Callable[[IDbSession], IEmotionRepository],
        conv_repo_factory: Callable[[IDbSession], IConversationRepository],
        user_repo_factory: Callable[[IDbSession], IUserRepository],
        db_session_factory: Callable[[], AbstractAsyncContextManager[IDbSession]],
        # The following are needed for background tasks that weren't extracted
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        vector_store: IVectorStore,
    ):
        self.pipeline = pipeline
        self.uow_factory = uow_factory
        self.cache = cache_provider
        self.cache_provider = cache_provider
        self.emotion_repo_factory = emotion_repo_factory
        self.conv_repo_factory = conv_repo_factory
        self.user_repo_factory = user_repo_factory
        
        self.llm = llm
        self.embedder = embedder
        self.vector_store = vector_store
        
        self.db_session_factory = db_session_factory

    async def get_emotion_state(self, session: IDbSession, user_id: str) -> EmotionState:
        from app.shared.utils.user_identity import normalize_user_id
        user_uuid = normalize_user_id(user_id)
        
        # 1. Check Redis State Cache (~0.2ms)
        if self.cache_provider:
            from app.domain.services.user_state_cache import UserStateCache
            cached_state = await UserStateCache.get_state(self.cache_provider, user_uuid)
            if cached_state:
                _, emotion, _ = cached_state
                return emotion

        # 2. Cache MISS -> Fallback to PostgreSQL
        user_repo = self.user_repo_factory(session)
        await user_repo.get_or_create_user(user_uuid)
        emotion_repo = self.emotion_repo_factory(session)
        emotion = await emotion_repo.get_emotion_state(user_uuid)
        
        # Write-Through to Redis Cache
        if self.cache_provider:
            stats = await user_repo.get_user_stats(user_uuid)
            from app.domain.services.user_state_cache import UserStateCache
            await UserStateCache.set_state(self.cache_provider, user_uuid, stats, emotion)

        return emotion

    async def get_history(self, session: IDbSession, user_id: str, limit: int = 50) -> list[dict[str, str]]:
        from app.shared.utils.user_identity import normalize_user_id
        user_uuid = normalize_user_id(user_id)
        user_repo = self.user_repo_factory(session)
        conv_repo = self.conv_repo_factory(session)
        
        await user_repo.get_or_create_user(user_uuid)
        conv_id = await conv_repo.get_or_create_conversation(user_uuid)
        return await conv_repo.get_recent_history(user_uuid, conv_id, limit)

    async def chat(
        self,
        session: IDbSession,
        user_id: str,
        user_message: str,
        on_token: Callable[[str], Any] | None = None,
        images: list[str] | None = None,
        is_ephemeral_reference: bool = False,
    ) -> tuple[str, dict[str, float], list[dict[str, Any]], list[AttachmentManifest]]:
        result = await self.chat_detailed(
            session=session,
            user_id=user_id,
            user_message=user_message,
            on_token=on_token,
            images=images,
            is_ephemeral_reference=is_ephemeral_reference,
        )
        return result.legacy_tuple()

    async def chat_detailed(
        self,
        session: IDbSession,
        user_id: str,
        user_message: str,
        on_token: Callable[[str], Any] | None = None,
        images: list[str] | None = None,
        is_ephemeral_reference: bool = False,
    ) -> ChatExecutionResult:
        log.info("Starting ChatEngine cycle", user_id=user_id, has_images=bool(images))

        # ── Per-user distributed lock to prevent race conditions (TTL 120s) ──
        lock_key = f"chisa:chat_lock:{user_id}"
        acquired = await self.cache.acquire_lock(lock_key, ttl=120)
        if not acquired:
            log.warning("Chat lock not acquired — concurrent request for same user", user_id=user_id)
            raise ChatEngineBusyError(user_id)
        try:
            return await self._chat_inner(
                session=session,
                user_id=user_id,
                user_message=user_message,
                on_token=on_token,
                images=images,
                is_ephemeral_reference=is_ephemeral_reference,
            )
        finally:
            await self.cache.release_lock(lock_key, token=acquired)

    async def community_chat(
        self,
        session: IDbSession,
        channel_id: str,
        user_id: str,
        user_message: str,
        speaker_name: str,
        channel_name: str = "general",
        guild_id: str | None = None,
        guild_name: str | None = None,
        recent_messages: list[Any] | None = None,
        on_token: Callable[[str], Any] | None = None,
        images: list[str] | None = None,
        is_ephemeral_reference: bool = False,
    ) -> tuple[str, dict[str, float], list[dict[str, Any]], list[AttachmentManifest]]:
        result = await self.community_chat_detailed(
            session=session,
            channel_id=channel_id,
            user_id=user_id,
            user_message=user_message,
            speaker_name=speaker_name,
            channel_name=channel_name,
            guild_id=guild_id,
            guild_name=guild_name,
            recent_messages=recent_messages,
            on_token=on_token,
            images=images,
            is_ephemeral_reference=is_ephemeral_reference,
        )
        return result.legacy_tuple()

    async def community_chat_detailed(
        self,
        session: IDbSession,
        channel_id: str,
        user_id: str,
        user_message: str,
        speaker_name: str,
        channel_name: str = "general",
        guild_id: str | None = None,
        guild_name: str | None = None,
        recent_messages: list[Any] | None = None,
        on_token: Callable[[str], Any] | None = None,
        images: list[str] | None = None,
        is_ephemeral_reference: bool = False,
    ) -> ChatExecutionResult:
        log.info(
            "Starting ChatEngine Community cycle",
            channel_id=channel_id,
            speaker_id=user_id,
            speaker_name=speaker_name,
            channel_name=channel_name,
            has_images=bool(images),
        )

        # ── Per-speaker distributed lock to prevent race conditions (TTL 120s) ──
        lock_key = f"chisa:chat_lock:{user_id}"
        acquired = await self.cache.acquire_lock(lock_key, ttl=120)
        if not acquired:
            log.warning("Community chat lock not acquired — concurrent request for same speaker", user_id=user_id)
            raise ChatEngineBusyError(user_id)
        try:
            context = ChatContext(
                session=session,
                user_id=user_id,
                user_message=user_message,
                on_token=on_token,
                is_community=True,
                channel_id=channel_id,
                guild_id=guild_id,
                channel_name=channel_name,
                guild_name=guild_name,
                speaker_name=speaker_name,
                recent_community_messages=recent_messages or [],
                images=images or [],
                is_ephemeral_reference=is_ephemeral_reference,
            )
            context = await self.pipeline.execute(context)
            return ChatExecutionResult(
                reply_text=context.chisa_reply,
                emotions=context.updated_emotions,
                images_processed=context.images_processed,
                attached_images=context.attached_images,
                citation_ids=context.citation_ids,
            )
        finally:
            await self.cache.release_lock(lock_key, token=acquired)

    async def _chat_inner(
        self,
        session: IDbSession,
        user_id: str,
        user_message: str,
        on_token: Callable[[str], Any] | None = None,
        images: list[str] | None = None,
        is_ephemeral_reference: bool = False,
    ) -> ChatExecutionResult:
        try:
            # Run Chat Pipeline (CacheStage handles pure-lore caching internally)
            context = ChatContext(
                session=session,
                user_id=user_id,
                user_message=user_message,
                on_token=on_token,
                images=images or [],
                is_ephemeral_reference=is_ephemeral_reference,
            )
            context = await self.pipeline.execute(context)
            return ChatExecutionResult(
                reply_text=context.chisa_reply,
                emotions=context.updated_emotions,
                images_processed=context.images_processed,
                attached_images=context.attached_images,
                citation_ids=context.citation_ids,
            )
            
        except Exception as e:
            log.warning("Production chat generation failed, saving user message as failed", user_id=user_id, error=str(e))
            # Use a separate session to persist the failed message, because the outer
            # get_db_session dependency will roll back the original session on exception.
            try:
                from app.shared.utils.user_identity import normalize_user_id
                user_uuid = normalize_user_id(user_id)
                async with self.db_session_factory() as fail_session:
                    conv_repo = self.conv_repo_factory(fail_session)
                    conv_id = await conv_repo.get_or_create_conversation(user_uuid)
                    await conv_repo.save_message(conv_id, user_uuid, "user", user_message, is_success=False)
                    await fail_session.commit()
            except Exception as db_err:
                log.error("Failed to save failed message to database in production pipeline", error=str(db_err))
            raise e

    async def _unified_auto_summarize(self, user_id: str, conv_id: Any) -> None:
        """
        Background auto-summarization workflow for Private 1-on-1 DM triggered every 10 interactions.
        1. Loads previous summary (from PostgreSQL or Redis) + last 20 messages (10 interaction turns).
        2. Cleans debug noise/emotion blocks from transcript.
        3. Generates concise narrative summary (80-120 words) in Vietnamese.
        4. Saves to PostgreSQL and synchronizes with Redis cache (TTL 7 days).
        """
        log.info("Starting background auto-summarization...", user_id=user_id, conv_id=str(conv_id))
        async with self.db_session_factory() as session:
            try:
                from app.domain.services.community.transcript_formatter import (
                    ChannelTranscriptFormatter,
                )
                from app.shared.utils.user_identity import normalize_user_id

                user_uuid = normalize_user_id(user_id)
                conv_uuid = uuid.UUID(str(conv_id)) if isinstance(conv_id, (str, uuid.UUID)) else conv_id
                conv_repo = self.conv_repo_factory(session)
                user_repo = self.user_repo_factory(session)

                # 1. Load previous summary & stats
                previous_summary = None
                if self.cache_provider:
                    try:
                        previous_summary = await self.cache_provider.get(f"chisa:user:{user_uuid}:summary")
                    except Exception:
                        pass
                if not previous_summary:
                    previous_summary = await conv_repo.get_latest_summary(user_uuid, conv_uuid)

                stats = await user_repo.get_user_stats(user_uuid)
                is_full_refresh = stats and stats.interaction_count > 0 and stats.interaction_count % 100 == 0

                # 2. Load recent 10 pairs of messages (20 messages = 10 user + 10 assistant)
                msgs = await conv_repo.get_recent_history(user_uuid, conv_uuid, limit=20)
                if not msgs:
                    log.info("No messages to auto-summarize", conv_id=str(conv_uuid))
                    return

                # Clean debug noise and emotion blocks from transcript
                cleaned_lines = []
                for m in msgs:
                    cleaned_content = ChannelTranscriptFormatter.clean_message_content(m.get("content", ""))
                    if cleaned_content:
                        cleaned_lines.append(f"{m.get('role', 'user').upper()}: {cleaned_content}")

                new_transcript = "\n".join(cleaned_lines)
                if not new_transcript:
                    return

                # 3. Output JSON Schema
                AUTO_SUMMARIZE_SCHEMA = {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Concise standalone narrative summary in Vietnamese describing Senpai's life/mood, ongoing topics, and relationship dynamics (80-120 words)."
                        }
                    },
                    "required": ["summary"]
                }

                MERGE_SYSTEM_PROMPT = (
                    "You are an Auto-Summarizer for an anime AI Companion (Kuchiba Chisa) in Private 1-on-1 DM.\n"
                    "Your job is to UPDATE the rolling conversation summary by integrating new conversation messages into the previous summary.\n\n"
                    "CRITICAL RULES:\n"
                    "1. Output a standalone, concise narrative in Vietnamese (80-120 words) describing: Senpai's current life/mood updates, key topics discussed, and relationship progression with Chisa.\n"
                    "2. Retain important ongoing context from the previous summary while prioritizing newest discussions.\n"
                    "3. Do not include individual timestamps, roleplay metadata, or emotion debug blocks.\n"
                    "Return valid JSON matching schema: {\"summary\": \"...\"}"
                )

                FRESH_SYSTEM_PROMPT = (
                    "You are an Auto-Summarizer for an anime AI Companion (Kuchiba Chisa) in Private 1-on-1 DM.\n"
                    "Analyze the conversation transcript and provide a concise narrative summary in Vietnamese (80-120 words).\n\n"
                    "CRITICAL RULES:\n"
                    "1. Summarize Senpai's current life/mood updates, key topics discussed, and relationship progression with Chisa.\n"
                    "2. Output must be a clear, standalone paragraph in Vietnamese (80-120 words).\n"
                    "Return valid JSON matching schema: {\"summary\": \"...\"}"
                )

                if previous_summary and previous_summary.strip() and not is_full_refresh:
                    user_message = (
                        f"1. Previous conversation summary (Bản tóm tắt chu kỳ trước):\n{previous_summary}\n\n"
                        f"2. Recent conversation messages (Diễn biến 10 lượt trò chuyện vừa qua):\n{new_transcript}"
                    )
                    system_prompt = MERGE_SYSTEM_PROMPT
                    log.info("Auto-summarize: Incremental merge mode", conv_id=str(conv_uuid))
                else:
                    user_message = f"Conversation messages transcript:\n{new_transcript}"
                    system_prompt = FRESH_SYSTEM_PROMPT
                    log.info("Auto-summarize: Fresh mode", conv_id=str(conv_uuid))

                prompt = StructuredPrompt(
                    system=system_prompt,
                    history=[],
                    user_message=user_message,
                    response_schema=AUTO_SUMMARIZE_SCHEMA,
                    temperature=0.3,
                    retrieved_memories=[],
                    retrieved_lore=[],
                    rag_decisions={"use_deep_thinking": False},
                )

                from app.domain.context import llm_call_purpose
                llm_call_purpose.set("auto_summarize_private")
                response = await self.llm.generate(prompt)
                parsed = response.parsed or {}
                summary_text = str(parsed.get("summary", "")).strip()

                if summary_text:
                    # 1. Save summary to PostgreSQL
                    await conv_repo.update_conversation_summary(conv_uuid, summary_text)
                    await session.commit()
                    log.info("Conversation summary saved to PostgreSQL", conv_id=str(conv_uuid))

                    # 2. Sync to Redis Summary Cache (TTL 7 days)
                    if self.cache_provider:
                        try:
                            await self.cache_provider.set(f"chisa:user:{user_uuid}:summary", summary_text, ttl=7 * 24 * 3600)
                            log.info("Conversation summary synced to Redis cache", user_id=str(user_uuid))
                        except Exception as cache_err:
                            log.warning("Failed to sync summary to Redis cache", error=str(cache_err))
                else:
                    log.warning("Auto-summarize produced empty summary_text", conv_id=str(conv_uuid))

            except Exception as e:
                log.error("Failed to run background auto-summarization", error=str(e), user_id=user_id)

