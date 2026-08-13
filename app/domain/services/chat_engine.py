import time
import uuid
import asyncio
import dataclasses
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
                    if hasattr(current_emotion, "model_dump"):
                        emotion_dict = current_emotion.model_dump()
                    elif dataclasses.is_dataclass(current_emotion):
                        emotion_dict = dataclasses.asdict(current_emotion)
                    elif hasattr(current_emotion, "dict"):
                        emotion_dict = current_emotion.dict()
                    else:
                        emotion_dict = vars(current_emotion)
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

    async def _unified_auto_summarize(self, user_id: str, conv_id: Any) -> None:
        """
        Unified background auto-summarization workflow triggered every 50 interactions.
        1. Loads previous summary (from PostgreSQL) + last 50 messages.
        2. Performs Incremental Merge LLM call producing:
           - "summary": Narrative standalone summary -> saved to PostgreSQL conversations.summary (Task 1).
           - "extracted_facts": Array of key memory items -> vector embedded, conflict-reconciled, and upserted/deleted in Qdrant memories collection (Task 2).
        """
        log.info("Starting unified background auto-summarization...", user_id=user_id, conv_id=str(conv_id))
        async with self.db_session_factory() as session:
            try:
                from app.shared.utils.user_identity import normalize_user_id
                user_uuid = normalize_user_id(user_id)
                conv_uuid = uuid.UUID(str(conv_id)) if isinstance(conv_id, (str, uuid.UUID)) else conv_id
                conv_repo = self.conv_repo_factory(session)
                user_repo = self.user_repo_factory(session)

                # 1. Load previous summary & stats
                previous_summary = await conv_repo.get_latest_summary(user_uuid, conv_uuid)
                stats = await user_repo.get_user_stats(user_uuid)
                is_full_refresh = stats and stats.interaction_count > 0 and stats.interaction_count % 100 == 0

                # 2. Load recent 10 pairs of messages (20 messages = 10 user + 10 assistant)
                msgs = await conv_repo.get_recent_history(user_uuid, conv_uuid, limit=20)
                if not msgs:
                    log.info("No messages to auto-summarize", conv_id=str(conv_uuid))
                    return

                new_transcript = "\n".join(
                    f"{m['role'].upper()}: {m['content']}" for m in msgs
                )

                # 3. Combined Output JSON Schema
                UNIFIED_SUMMARIZE_SCHEMA = {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "extracted_facts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["preferences", "shared_memories", "relationship", "important_facts"]
                                    },
                                    "content": {"type": "string"},
                                    "importance_score": {"type": "number", "minimum": 0.1, "maximum": 1.0}
                                },
                                "required": ["type", "content"]
                            }
                        }
                    },
                    "required": ["summary"]
                }

                MERGE_SYSTEM_PROMPT = (
                    "You are UPDATING a conversation summary and extracting key memory facts "
                    "for Kuchiba Chisa, a character from Wuthering Waves.\n\n"
                    "CRITICAL RULES:\n"
                    "1. 'summary': PRESERVE important details from previous summary and merge new info from recent messages. "
                    "Must be a STANDALONE, COMPLETE, concise narrative summary in Vietnamese.\n"
                    "2. 'extracted_facts': Extract discrete, persistent memory facts (user preferences, relationship milestones, important events) "
                    "to store long-term in memory DB. Output in Vietnamese with types 'preferences', 'shared_memories', 'relationship', or 'important_facts'.\n"
                    "You MUST output a valid JSON object matching the requested schema."
                )

                FRESH_SYSTEM_PROMPT = (
                    "You are a conversation summarizer and memory extractor for Kuchiba Chisa.\n"
                    "1. 'summary': Analyze transcript and provide a concise standalone summary in Vietnamese.\n"
                    "2. 'extracted_facts': Extract discrete persistent memory facts to store long-term in memory DB.\n"
                    "You MUST output a valid JSON object matching the requested schema."
                )

                if previous_summary and previous_summary.strip() and not is_full_refresh:
                    user_message = (
                        f"Previous summary:\n{previous_summary}\n\n"
                        f"New messages to merge:\n{new_transcript}"
                    )
                    system_prompt = MERGE_SYSTEM_PROMPT
                    log.info("Unified auto-summarize: Incremental merge mode", conv_id=str(conv_uuid))
                else:
                    user_message = f"Please summarize this conversation transcript:\n\n{new_transcript}"
                    system_prompt = FRESH_SYSTEM_PROMPT
                    log.info("Unified auto-summarize: Fresh mode", conv_id=str(conv_uuid))

                prompt = StructuredPrompt(
                    system=system_prompt,
                    history=[],
                    user_message=user_message,
                    response_schema=UNIFIED_SUMMARIZE_SCHEMA,
                    temperature=0.3,
                    retrieved_memories=[],
                    retrieved_lore=[],
                    rag_decisions={"use_deep_thinking": False},
                )

                from app.domain.context import llm_call_purpose
                llm_call_purpose.set("unified_auto_summarize")
                response = await self.llm.generate(prompt)
                parsed = response.parsed or {}
                summary_text = str(parsed.get("summary", "")).strip()
                extracted_facts = parsed.get("extracted_facts", [])

                # ── TASK 1: Save summary to PostgreSQL ──
                if summary_text:
                    await conv_repo.update_conversation_summary(conv_uuid, summary_text)
                    await session.commit()
                    log.info("Task 1: Conversation summary saved to PostgreSQL", conv_id=str(conv_uuid))
                else:
                    log.warning("Unified auto-summarize produced empty summary_text", conv_id=str(conv_uuid))

                # ── TASK 2: Extract & Conflict-Check Memory Points for Qdrant Vector DB ──
                if isinstance(extracted_facts, list) and extracted_facts:
                    from app.domain.services.memory_extractor import MemoryExtractor
                    memory_extractor = MemoryExtractor(self.llm, self.embedder, self.vector_store)
                    
                    for item in extracted_facts:
                        if not isinstance(item, dict):
                            continue
                        content = str(item.get("content", "")).strip()
                        fact_type = item.get("type", "shared_memories")
                        importance = float(item.get("importance_score", 0.7))

                        if len(content) < 5:
                            continue

                        # Vector Search @ threshold 0.70 to find existing candidate memories
                        vector = await self.embedder.embed_text(content, prefix="passage: ")
                        existing = await self.vector_store.search_by_user(
                            collection="memories",
                            query_vector=vector,
                            user_id=user_id,
                            limit=3,
                            score_threshold=0.70
                        )

                        if existing:
                            # Conflict / Duplicate Reconciliation
                            action, conflicting_id = await memory_extractor.reconcile_memory_conflict(content, existing)
                            if action == "DUPLICATE":
                                log.info("Task 2: Skipped memory insertion — duplicate fact detected", content=content)
                                continue
                            elif action == "CONTRADICT" and conflicting_id:
                                log.info("Task 2: Deleting superseded memory point", old_id=conflicting_id, new_content=content)
                                try:
                                    await self.vector_store.delete_points(collection="memories", ids=[conflicting_id])
                                except Exception as del_err:
                                    log.warning("Task 2: Failed to delete conflicting memory point", id=conflicting_id, error=str(del_err))

                        point_id = str(uuid.uuid4())
                        payload = MemoryPayload(
                            user_id=user_id,
                            conversation_id=str(conv_uuid),
                            memory_type=fact_type,
                            importance_score=importance,
                            created_at=int(time.time()),
                            text_content=content,
                        )
                        await self.vector_store.upsert_memory(
                            collection="memories",
                            point_id=point_id,
                            vector=vector,
                            payload=payload
                        )
                        log.info("Task 2: Upserted memory fact to Qdrant Vector DB", content=content)

            except Exception as e:
                log.error("Failed to run unified background auto-summarization", error=str(e), user_id=user_id)

