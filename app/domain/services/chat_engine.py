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

        # ── Per-user distributed lock to prevent race conditions ──
        lock_key = f"chisa:chat_lock:{user_id}"
        acquired = await self.cache.acquire_lock(lock_key, ttl=60)
        if not acquired:
            log.warning("Chat lock not acquired — concurrent request for same user", user_id=user_id)
            raise ChatEngineBusyError(user_id)
        try:
            return await self._chat_inner(session, user_id, user_message, on_token)
        finally:
            await self.cache.release_lock(lock_key)

    async def _chat_inner(self, session: IDbSession, user_id: str, user_message: str, on_token: Optional[Callable[[str], Any]] = None) -> Tuple[str, Dict[str, float]]:
        try:
            async with self.uow_factory(session) as uow:
                context = ChatContext(
                    session=session,
                    user_id=user_id,
                    user_message=user_message,
                    on_token=on_token
                )
                context = await self.pipeline.execute(context)
                
            return context.chisa_reply, context.updated_emotions
            
        except Exception as e:
            log.warning("Production chat generation failed, saving user message as failed", user_id=user_id, error=str(e))
            try:
                from app.shared.utils.user_identity import normalize_user_id
                user_uuid = normalize_user_id(user_id)
                conv_repo = self.conv_repo_factory(session)
                conv_id = await conv_repo.get_or_create_conversation(user_uuid)
                
                # Save the failed message. The previous savepoint was rolled back by UoW.
                await conv_repo.save_message(conv_id, user_uuid, "user", user_message, is_success=False)
                await session.flush()
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
                            vector = await self.embedder.embed_text(point)
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
        Background task to auto-summarize the conversation if message count >= 20.
        """
        log.info("Starting background conversation auto-summarization...", conv_id=str(conv_id))
        async with self.db_session_factory() as session:
            try:
                from app.shared.utils.user_identity import normalize_user_id
                user_uuid = normalize_user_id(user_id)
                conv_repo = self.conv_repo_factory(session)
                msgs = await conv_repo.get_recent_history(user_uuid, conv_id, limit=1000)
                if not msgs:
                    log.info("No messages in conversation to auto-summarize", conv_id=str(conv_id))
                    return

                # Build chat transcript for LLM
                chat_transcript = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in msgs])

                system_prompt = (
                    "You are a conversation summarizer for Kuchiba Chisa, a character from Wuthering Waves.\n"
                    "Analyze the conversation transcript provided and summarize the key discussion points, "
                    "user's preferences, interests, emotional vibe, and current relationship context.\n"
                    "Keep the summary concise, informative, in Vietnamese, and write it in a structured paragraph or bullet points.\n"
                    "You MUST output the result as a valid JSON object matching the requested schema containing a 'summary' key."
                )

                from app.domain.services.tool_router import LLMToolRouter
                prompt = StructuredPrompt(
                    system=system_prompt,
                    history=[],
                    user_message=f"Please summarize this conversation transcript:\n\n{chat_transcript}",
                    response_schema=LLMToolRouter.SUMMARIZE_CONVERSATION_SCHEMA,
                    retrieved_memories=[],
                    retrieved_lore=[],
                    rag_decisions={}
                )

                response = await self.llm.generate(prompt)
                summary_text = (response.parsed or {}).get("summary", "").strip()
                if not summary_text:
                    summary_text = response.raw_content or ""

                log.info("Conversation auto-summarized successfully via background LLM", conv_id=str(conv_id))
            except Exception as e:
                log.error("Failed to run background auto-summarization", error=str(e), conv_id=str(conv_id))

