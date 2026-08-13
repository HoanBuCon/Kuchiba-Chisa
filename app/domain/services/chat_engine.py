import time
import math
import uuid
import asyncio
from typing import Tuple, Dict, Any, List, Optional, Callable, AsyncContextManager
from app.domain.interfaces.session import IDbSession
from app.config.settings import settings
from app.shared.utils.background_tasks import BackgroundTaskManager
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.entities.emotion import EmotionState
from app.domain.entities.memory import MemoryPayload
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.interfaces.repositories import IUserRepository, IEmotionRepository, IConversationRepository
from app.domain.interfaces.uow import IUnitOfWork
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class ChatEngineBusyError(Exception):
    """Raised when a user's chat request is already being processed (per-user lock not acquired)."""
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"Chat engine busy for user {user_id} — concurrent request rejected")

class ChatPipeline:
    def __init__(self, stages: List[PipelineStage]):
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
        db_session_factory: Callable[[], AsyncContextManager[IDbSession]],
        # The following are needed for background tasks that weren't extracted
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        vector_store: IVectorStore,
    ):
        self.pipeline = pipeline
        self.uow_factory = uow_factory
        self.cache = cache_provider
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
        emotion_repo = self.emotion_repo_factory(session)
        return await emotion_repo.get_emotion_state(user_uuid)

    async def get_history(self, session: IDbSession, user_id: str, limit: int = 50) -> list[dict[str, str]]:
        from app.shared.utils.user_identity import normalize_user_id
        user_uuid = normalize_user_id(user_id)
        user_repo = self.user_repo_factory(session)
        conv_repo = self.conv_repo_factory(session)
        
        await user_repo.get_or_create_user(user_uuid)
        conv_id = await conv_repo.get_or_create_conversation(user_uuid)
        return await conv_repo.get_recent_history(user_uuid, conv_id, limit)

    async def chat(self, session: IDbSession, user_id: str, user_message: str, on_token: Optional[Callable[[str], Any]] = None) -> Tuple[str, Dict[str, float]]:
        log.info("Starting ChatEngine cycle", user_id=user_id)

        # ── Per-user distributed lock to prevent race conditions (TTL 120s) ──
        lock_key = f"chisa:chat_lock:{user_id}"
        acquired = await self.cache.acquire_lock(lock_key, ttl=120)
        if not acquired:
            log.warning("Chat lock not acquired — concurrent request for same user", user_id=user_id)
            raise ChatEngineBusyError(user_id)
        try:
            return await self._chat_inner(session, user_id, user_message, on_token)
        finally:
            await self.cache.release_lock(lock_key)

    async def _chat_inner(self, session: IDbSession, user_id: str, user_message: str, on_token: Optional[Callable[[str], Any]] = None) -> Tuple[str, Dict[str, float]]:
        from app.shared.utils.fallback_detector import is_fallback_reply
        try:
            import hashlib
            query_hash = hashlib.md5(user_message.encode('utf-8')).hexdigest()
            cache_key = f"chisa:answer_cache:{user_id}:{query_hash}"
            
            # 1. Check Answer Cache (invalidate if fallback/error reply)
            cached_answer = await self.cache.get(cache_key)
            if cached_answer:
                if is_fallback_reply(cached_answer):
                    log.warning("Redis Answer Cache contains fallback/error reply. Invalidating key", user_id=user_id, cache_key=cache_key)
                    await self.cache.delete(cache_key)
                else:
                    log.info("Redis Answer Cache HIT", user_id=user_id, query_hash=query_hash)
                    current_emotion = await self.get_emotion_state(session, user_id)
                    emotion_dict = current_emotion.model_dump() if hasattr(current_emotion, "model_dump") else current_emotion.dict()
                    return cached_answer, emotion_dict

            # 2. Run Pipeline on Cache Miss
            context = ChatContext(
                session=session,
                user_id=user_id,
                user_message=user_message,
                on_token=on_token
            )
            context = await self.pipeline.execute(context)
            
            # 3. Store in Answer Cache (TTL 12 hours) — only valid responses!
            if context.chisa_reply and not is_fallback_reply(context.chisa_reply):
                await self.cache.set(cache_key, context.chisa_reply, ttl=43200)
                
            return context.chisa_reply, context.updated_emotions
            
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

    async def _summarize_and_store_memories(self, user_id: str, conv_id: str, history: list[dict[str, str]]) -> None:
        """
        Background task summarizing chat and saving summary points to the memories collection.
        """
        log.info("Starting background summarization for memories collection", user_id=user_id)
        chat_transcript = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history])
        
        RESPONSE_SCHEMA = {
            "type": "object",
            "properties": {
                "summary_points": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["summary_points"]
        }
        
        system_instructions = (
            "You are an AI Memory Summarizer. Extract important facts about the user and their relationship with the AI.\n"
            "Focus on: personal facts, preferences, emotional events, and relationship progress.\n"
            "You must output a JSON object containing a 'summary_points' array of concise bullet points in Vietnamese."
        )
        
        user_prompt = f"Summarize this conversation transcript:\n\n{chat_transcript}"
        prompt = StructuredPrompt(
            system=system_instructions,
            history=[],
            user_message=user_prompt,
            response_schema=RESPONSE_SCHEMA
        )
        
        try:
            response = await self.llm.generate(prompt)
            if response.parsed and "summary_points" in response.parsed:
                points = response.parsed["summary_points"]
                if isinstance(points, list):
                    for point in points:
                        point = point.strip()
                        if len(point) > 5:
                            vector = await self.embedder.embed_text(point, prefix="passage: ")
                            point_id = str(uuid.uuid4())
                            payload = MemoryPayload(
                                user_id=user_id,
                                conversation_id=conv_id,
                                memory_type="shared_memories",
                                importance_score=0.7,
                                created_at=int(time.time()),
                                text_content=point,
                            )
                            await self.vector_store.upsert_memory(
                                collection="memories",
                                point_id=point_id,
                                vector=vector,
                                payload=payload
                            )
                    log.info("Successfully summarized conversation and saved points to memories collection", user_id=user_id)
        except Exception as e:
            log.error("Failed to run background summarization for memories collection", error=str(e), user_id=user_id)

    async def _auto_summarize_conversation(self, user_id: str, conv_id: uuid.UUID) -> None:
        """
        Background incremental merge summarization — O(1) token cost per call.
        Merges last 60 messages with previous summary (if exists),
        then overwrites conversations.summary in PostgreSQL.
        Full refresh every 500 interactions to prevent quality degradation.
        """
        log.info("Starting background conversation auto-summarization...", conv_id=str(conv_id))
        async with self.db_session_factory() as session:
            try:
                from app.shared.utils.user_identity import normalize_user_id
                user_uuid = normalize_user_id(user_id)
                conv_repo = self.conv_repo_factory(session)
                user_repo = self.user_repo_factory(session)

                # 1. Load previous summary & interaction count for full-refresh check
                previous_summary = await conv_repo.get_latest_summary(user_uuid, conv_id)
                stats = await user_repo.get_user_stats(user_uuid)
                is_full_refresh = stats and stats.interaction_count > 0 and stats.interaction_count % 500 == 0

                # 2. Load only last 60 messages (O(1) regardless of conversation length)
                msgs = await conv_repo.get_recent_history(user_uuid, conv_id, limit=60)
                if not msgs:
                    log.info("No messages to auto-summarize", conv_id=str(conv_id))
                    return

                new_transcript = "\n".join(
                    f"{m['role'].upper()}: {m['content']}" for m in msgs
                )

                # 3. Build prompt: merge or fresh
                MERGE_SYSTEM_PROMPT = (
                    "You are UPDATING (not creating from scratch) a conversation summary "
                    "for Kuchiba Chisa, a character from Wuthering Waves.\n\n"
                    "CRITICAL RULES:\n"
                    "- PRESERVE ALL important details from the previous summary "
                    "(user preferences, personal facts, emotional events, relationship milestones).\n"
                    "- INTEGRATE new information from the recent messages.\n"
                    "- REMOVE duplicates and merge related points.\n"
                    "- The output must be a STANDALONE, COMPLETE summary — "
                    "do NOT reference the previous summary or raw messages.\n"
                    "- Keep it concise, in Vietnamese, as structured bullet points or a short paragraph.\n"
                    "You MUST output a valid JSON object matching the requested schema containing a 'summary' key."
                )

                FRESH_SYSTEM_PROMPT = (
                    "You are a conversation summarizer for Kuchiba Chisa, a character from Wuthering Waves.\n"
                    "Analyze the conversation transcript and summarize the key discussion points, "
                    "user's preferences, interests, emotional vibe, and current relationship context.\n"
                    "Keep the summary concise, informative, in Vietnamese, as structured bullet points or a short paragraph.\n"
                    "You MUST output a valid JSON object matching the requested schema containing a 'summary' key."
                )

                if previous_summary and previous_summary.strip() and not is_full_refresh:
                    user_message = (
                        f"Previous summary:\n{previous_summary}\n\n"
                        f"New messages to merge:\n{new_transcript}"
                    )
                    system_prompt = MERGE_SYSTEM_PROMPT
                    log.info("Incremental merge mode", conv_id=str(conv_id))
                else:
                    user_message = f"Please summarize this conversation transcript:\n\n{new_transcript}"
                    system_prompt = FRESH_SYSTEM_PROMPT
                    if is_full_refresh:
                        log.info("Full refresh mode (500-interaction milestone)", conv_id=str(conv_id))
                    else:
                        log.info("Fresh summarize mode (no previous summary)", conv_id=str(conv_id))

                from app.domain.services.tool_router import LLMToolRouter
                prompt = StructuredPrompt(
                    system=system_prompt,
                    history=[],
                    user_message=user_message,
                    response_schema=LLMToolRouter.SUMMARIZE_CONVERSATION_SCHEMA,
                    temperature=0.3,
                    retrieved_memories=[],
                    retrieved_lore=[],
                    rag_decisions={},
                )

                response = await self.llm.generate(prompt)
                summary_text = (response.parsed or {}).get("summary", "").strip()
                if not summary_text:
                    summary_text = response.raw_content or ""

                if summary_text:
                    await conv_repo.update_conversation_summary(conv_id, summary_text)
                    await session.commit()
                    log.info("Conversation summary saved to PostgreSQL", conv_id=str(conv_id))
                else:
                    log.warning("Summarizer produced empty output", conv_id=str(conv_id))

            except Exception as e:
                log.error("Failed to run background auto-summarization", error=str(e), conv_id=str(conv_id))

