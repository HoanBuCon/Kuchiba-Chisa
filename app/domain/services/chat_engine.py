import time
import math
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.domain.services.rag_retriever import rag_retriever
from app.infrastructure.database.models.emotion_state import EmotionState
from app.infrastructure.database.models.user_stats import UserStats
from app.infrastructure.database.models.message import Message
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.memory_manager import MemoryManager
from app.domain.services.emotion_engine import EmotionEngine
from app.domain.services.rag_router import RAGRouter
from app.domain.services.context_budget_manager import ContextBudgetManager
from app.domain.services.memory_summarizer import MemorySummarizer
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.infrastructure.database.repositories.emotion_repository import SqlAlchemyEmotionRepository
from app.infrastructure.database.repositories.conversation_repository import SqlAlchemyConversationRepository
import asyncio
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

class ChatEngine:
    """
    Core orchestrator for Multi-User emotional chat interactions.
    Handles Data Fetching, Attachment Growth computation, Prompt Engineering, and saving.
    """
    def __init__(
        self, 
        embedder: IEmbeddingProvider, 
        llm: BaseLLMAdapter,
        context_builder: ContextBuilder,
        memory_manager: MemoryManager
    ):
        self.embedder = embedder
        self.llm = llm
        self.context_builder = context_builder
        self.memory_manager = memory_manager
        self.emotion_engine = EmotionEngine()
        self.memory_summarizer = MemorySummarizer(llm=llm, memory_manager=memory_manager)

    async def get_emotion_state(self, session: AsyncSession, user_id: str) -> EmotionState:
        """Public method to fetch/initialize the current emotional state of Chisa."""
        user_uuid = uuid.UUID(user_id)
        emotion_repo = SqlAlchemyEmotionRepository(session)
        return await emotion_repo.get_emotion_state(user_uuid)

    async def _classify_emotion(self, user_message: str, history: list[dict[str, str]]) -> dict[str, bool]:
        """
        Uses a fast, low-parameter model to perform context-aware sentiment analysis.
        This replaces the fragile Regex keyword matching.
        """
        from app.infrastructure.llm.adapters.base import StructuredPrompt

        # Use only the last 4 messages for classification context
        short_history = history[-4:] if len(history) >= 4 else history
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in short_history])
        
        prompt = StructuredPrompt(
            system="""You are a strict conversational sentiment classifier for an Anime AI Chatbot named Chisa.
Analyze the user's latest message IN CONTEXT of the previous conversation.
You must output a JSON with exactly four boolean flags:

- "is_positive": True if the user is complimenting, showing affection, teasing playfully, or expressing clear happiness/gratitude towards Chisa.
- "is_negative": True if the user is expressing genuine sadness, actual anger, complaining about Chisa, or saying Chisa did something wrong. IMPORTANT: Do NOT mark True for Vietnamese mock-frustration slang (e.g., 'thiệt tình', 'chịu chết', 'bó tay', 'cạn lời', 'hết cứu') used playfully.
- "is_rude": True ONLY if the user is using explicit insults, hate speech, or severe hostility (e.g., "ngu", "chết đi", "rác rưởi").
- "is_neutral": True if the emotional signal—whether positive or negative—is MILD or CASUAL in intensity (e.g., a friendly remark that is only slightly warm, a mild passing complaint, ordinary small talk, a simple question). Set False ONLY when the emotion is CLEARLY INTENSE or HEARTFELT (e.g., explicit love/deep affection, profound gratitude, genuine strong anger, or deeply felt sadness). When in doubt, default to True.

IMPORTANT: is_neutral describes EMOTIONAL INTENSITY, not message category. A message can be is_positive=True AND is_neutral=True (mildly warm), or is_positive=True AND is_neutral=False (strongly heartfelt).

Output purely valid JSON. No markdown wrappers.""",
            history=[],
            user_message=f"Context History:\n{history_text}\n\nLatest User Message: {user_message}",
            response_schema={
                "type": "object",
                "properties": {
                    "is_positive": {"type": "boolean"},
                    "is_negative": {"type": "boolean"},
                    "is_rude": {"type": "boolean"},
                    "is_neutral": {"type": "boolean"}
                },
                "required": ["is_positive", "is_negative", "is_rude", "is_neutral"]
            },
            max_tokens=120,
            temperature=0.0
        )
        
        try:
            # We enforce a specific fast model for classification to save latency
            # We temporarily override the configured model inside the adapter just for this call
            original_model = getattr(self.llm, "_model", getattr(self.llm, "model_name", "llama-3.1-8b-instant"))
            
            from app.config.settings import settings
            fast_model = "gemini-2.5-flash" if settings.LLM_PROVIDER == "gemini" else "llama-3.1-8b-instant"
            
            if hasattr(self.llm, "_model"):
                self.llm._model = fast_model
            elif hasattr(self.llm, "model_name"):
                self.llm.model_name = fast_model
                
            response = await self.llm.generate(prompt)
            
            # Restore model
            if hasattr(self.llm, "_model"):
                self.llm._model = original_model
            elif hasattr(self.llm, "model_name"):
                self.llm.model_name = original_model
                
            return {
                "is_positive": response.parsed.get("is_positive", False),
                "is_negative": response.parsed.get("is_negative", False),
                "is_rude": response.parsed.get("is_rude", False),
                "is_neutral": response.parsed.get("is_neutral", True)
            }
        except Exception as e:
            log.warning("Emotion classification failed, falling back to neutral", error=str(e))
            # Safe Fallback to Neutral
            return {"is_positive": False, "is_negative": False, "is_rude": False, "is_neutral": True}

    async def get_history(self, session: AsyncSession, user_id: str, limit: int = 50) -> list[dict[str, str]]:
        """Public method to fetch conversation history for the Web UI on load."""
        user_uuid = uuid.UUID(user_id)
        user_repo = SqlAlchemyUserRepository(session)
        conv_repo = SqlAlchemyConversationRepository(session)
        
        await user_repo.get_or_create_user(user_uuid)
        conv_id = await conv_repo.get_or_create_conversation(user_uuid)
        return await conv_repo.get_recent_history(user_uuid, conv_id, limit)

    async def chat(self, session: AsyncSession, user_id: str, user_message: str) -> str:
        """
        Orchestrates the entire multi-user chat cycle:
        1. Load User Stats, Emotion, Conversation
        2. Emotion updates & Formulate Attachment Bonus
        3. Retrieve RAG Memories & Lore via Hybrid Scoring
        4. Build Isolated System Prompt
        5. Call LLM
        6. Post-process stats and Save Messages (STM + LTM)
        """
        log.info("Starting ChatEngine cycle", user_id=user_id)
        
        # 1. Initialize repositories & Load context
        user_uuid = uuid.UUID(user_id)
        user_repo = SqlAlchemyUserRepository(session)
        emotion_repo = SqlAlchemyEmotionRepository(session)
        conv_repo = SqlAlchemyConversationRepository(session)
        
        await user_repo.get_or_create_user(user_uuid)
        stats = await user_repo.get_user_stats(user_uuid)
        emotion = await emotion_repo.get_emotion_state(user_uuid)
        conv_id = await conv_repo.get_or_create_conversation(user_uuid)
        
        history = await conv_repo.get_recent_history(user_uuid, conv_id)
        
        # Save user message immediately to STM
        await conv_repo.save_message(conv_id, user_uuid, "user", user_message)
        # 2. Smart RAG Routing & Initial Flags
        # RAG Router first to determine if it's a casual message or requires deep context
        rag_decisions = RAGRouter.should_retrieve(user_message)
        
        # 3. Context-Aware Emotion Classification (Fast LLM Call)
        emotion_flags = await self._classify_emotion(user_message, history)
        
        # Update Emotion State based on LLM Flags & Calculate emergent attachment bonus
        emotion_delta = self.emotion_engine.update(emotion, **emotion_flags)
        attachment_bonus = math.log(max(1, stats.interaction_count)) * 0.05
        
        # Save emotion state changes early
        await emotion_repo.update_emotion(emotion)
        
        # Calculate memory importance from MemoryManager
        importance_score = self.memory_manager.calculate_importance(user_message, emotion_delta)
        
        # Format emotions for system context
        current_emotions = {
            "joy": emotion.joy,
            "sadness": emotion.sadness,
            "trust": emotion.trust,
            "irritation": emotion.irritation,
            "attachment": emotion.attachment + attachment_bonus
        }
        
        lore_chunks = []
        memories = []
        
        if rag_decisions["use_memory"] or rag_decisions["use_lore"]:
            vector = await self.embedder.embed_text(user_message)
            
            if rag_decisions["use_memory"]:
                memories = await rag_retriever.retrieve_memories(
                    collection="emotional_memories",
                    query_vector=vector,
                    user_id=user_id,
                    current_emotion=current_emotions,
                    top_k=5
                )
                
            if rag_decisions["use_lore"]:
                lore_chunks = await rag_retriever.retrieve_lore(
                    query_vector=vector,
                    top_k=4
                )
                log.info(f"Retrieved {len(lore_chunks)} lore chunks")
                if lore_chunks:
                    log.info(f"First chunk snippet: {lore_chunks[0][:100]}")
        
        # Token Budget Management
        trimmed_lore, trimmed_memories, trimmed_history = ContextBudgetManager.enforce_budget(
            lore_chunks=lore_chunks,
            memories=memories,
            history=history
        )
        
        # 4. Prompt Engineering via ContextBuilder using trimmed context
        prompt = self.context_builder.build(
            emotion=emotion,
            attachment_bonus=attachment_bonus,
            memories=trimmed_memories,
            lore_chunks=trimmed_lore,
            history=trimmed_history,
            user_message=user_message
        )
        
        # 5. LLM Generation
        response = await self.llm.generate(prompt)
        chisa_reply = response.parsed.get("response")
        
        # Fallback if the model hallucinated the JSON key but returned valid JSON
        if not chisa_reply and response.parsed:
            # Get the first string value from the dictionary
            for val in response.parsed.values():
                if isinstance(val, str) and val.strip():
                    chisa_reply = val
                    break
                    
        chisa_reply = chisa_reply or ""
        
        # Log Token Consumption
        total_tokens = response.input_tokens + response.output_tokens
        log.info(
            "LLM Token Consumption", 
            user_id=user_id, 
            input_tokens=response.input_tokens, 
            output_tokens=response.output_tokens, 
            total_tokens=total_tokens
        )
        
        # 6. Post-processing
        await conv_repo.save_message(
            conv_id, 
            user_uuid, 
            "assistant", 
            chisa_reply, 
            token_count=total_tokens
        )
        
        # LTM Write: If important enough, save to Qdrant (Fire & Forget but awaited here)
        if importance_score >= 0.65:
            await self.memory_manager.save_emotional_memory(
                user_id=user_id,
                conversation_id=str(conv_id),
                message_content=user_message,
                importance_score=importance_score
            )
        
        stats.interaction_count += 1
        stats.last_seen = int(time.time() * 1000)
        await user_repo.update_stats(stats)
        
        # Background: Trigger long-term summarization every 40 interactions
        if stats.interaction_count > 0 and stats.interaction_count % 40 == 0:
            full_history = await self.get_history(session, user_id, limit=40)
            if len(full_history) >= 20:
                asyncio.create_task(
                    self.memory_summarizer.summarize_and_store(user_id, str(conv_id), full_history)
                )
        
        
        log.info("ChatEngine cycle complete", user_id=user_id, attachment_bonus=attachment_bonus)
        return chisa_reply, current_emotions
