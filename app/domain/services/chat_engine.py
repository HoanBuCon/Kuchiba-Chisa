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
from app.shared.utils.query_cleaner import clean_query_for_rag

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

    async def get_history(self, session: AsyncSession, user_id: str, limit: int = 50) -> list[dict[str, str]]:
        """Public method to fetch conversation history for the Web UI on load."""
        user_uuid = uuid.UUID(user_id)
        user_repo = SqlAlchemyUserRepository(session)
        conv_repo = SqlAlchemyConversationRepository(session)
        
        await user_repo.get_or_create_user(user_uuid)
        conv_id = await conv_repo.get_or_create_conversation(user_uuid)
        return await conv_repo.get_recent_history(user_uuid, conv_id, limit)

    async def chat(self, session: AsyncSession, user_id: str, user_message: str) -> tuple[str, dict]:
        """
        Orchestrates the entire multi-user chat cycle using Single-Call Joint Orchestration:
        1. Load User Stats, Emotion, Conversation History
        2. Format Emotions & Calculate Attachment Bonus
        3. Retrieve RAG Memories & Lore via Hybrid Scoring
        4. Build Joint System Prompt Context (incorporating emotional states)
        5. Call LLM (Single-call parses Chisa's response AND user sentiment jointly)
        6. Perform single Emotion update based on parsed sentiment flags
        7. Save Assistant Message, update interaction count & trigger background summarizers
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
        
        # NOTE: User message is saved AFTER successful LLM generation (see below)
        # to prevent duplicate entries when the client retries on 500 errors.

        try:
            # 2. Smart RAG Retrieval
            # RAG Router only needed for memory (keyword-based triggers remain useful for memory recall)
            rag_decisions = RAGRouter.should_retrieve(user_message)
            
            # Attachment bonus formulation (raw value based on interaction history)
            # This bonus is dampened later based on final emotional state
            attachment_bonus_raw = math.log(max(1, stats.interaction_count)) * 0.05
            
            # Format emotions for system context
            current_emotions = {
                "joy": emotion.joy,
                "sadness": emotion.sadness,
                "trust": emotion.trust,
                "irritation": emotion.irritation,
                "attachment": emotion.attachment + attachment_bonus_raw
            }
            
            lore_chunks = []
            memories = []
            
            # Lore: Always search with vector similarity + threshold filtering
            LORE_THRESHOLD = 0.35
            is_small_talk = RAGRouter.is_small_talk(user_message)

            from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
            pipeline_tracker.add_step("intent_classification", {
                "is_small_talk": is_small_talk,
                "should_retrieve_memory": rag_decisions.get("use_memory", False)
            })
            
            if not is_small_talk:
                cleaned_query = clean_query_for_rag(user_message)
                vector = await self.embedder.embed_text(cleaned_query)
                
                # Always search lore — let the score decide relevance
                raw_lore = await rag_retriever.retrieve_lore(
                    query_vector=vector,
                    query_text=cleaned_query,
                    top_k=10,
                    score_threshold=0.3,  # Qdrant pre-filter (loose)
                )
                # Apply quality threshold — only keep genuinely relevant chunks
                lore_chunks = [text for text, score in raw_lore if score >= LORE_THRESHOLD]
                
                log.info(
                    "Lore vector search results",
                    total_candidates=len(raw_lore),
                    above_threshold=len(lore_chunks),
                    threshold=LORE_THRESHOLD,
                    scores=[f"{score:.3f}" for _, score in raw_lore[:5]],
                )
                
                # Memory: Still uses keyword triggers (memory recall is inherently intent-driven)
                if rag_decisions["use_memory"]:
                    memories = await rag_retriever.retrieve_memories(
                        collection="emotional_memories",
                        query_vector=vector,
                        user_id=user_id,
                        current_emotion=current_emotions,
                        top_k=5
                    )
            
            # Update rag_decisions to reflect actual retrieval results (for logging)
            rag_decisions["use_lore"] = len(lore_chunks) > 0

            pipeline_tracker.add_step("rag_retrieval", {
                "lore_collections_queried": ["character_lore", "world_lore", "story_lore"] if not is_small_talk else [],
                "retrieved_lore_chunks": lore_chunks,
                "retrieved_memories": [m.text_content if hasattr(m, "text_content") else str(m) for m in memories]
            })
            
            # RAG Emotion Seeding based on retrieved context
            SAD_LORE_TERMS = {"buồn", "cô đơn", "cô độc", "sợ hãi", "buồn bã", "đau thương", "vòng lặp", "mất mát", "chia ly", "sonoro sphere", "honami", "overclock"}
            user_message_lower = user_message.lower()
            
            # Only scan and seed emotions if the user's message itself touches upon tragic/sad terms
            if any(term in user_message_lower for term in SAD_LORE_TERMS):
                matches_count = 0
                for chunk in lore_chunks:
                    chunk_lower = chunk.lower()
                    for term in SAD_LORE_TERMS:
                        matches_count += chunk_lower.count(term)
                for m in memories:
                    text = m.text_content if hasattr(m, "text_content") else str(m)
                    text_lower = text.lower()
                    for term in SAD_LORE_TERMS:
                        matches_count += text_lower.count(term)
    
                if matches_count > 0:
                    seeding_sadness = min(0.35, matches_count * 0.06)
                    seeding_irritation = min(0.20, matches_count * 0.03)
                    emotion.sadness = min(1.0, emotion.sadness + seeding_sadness)
                    emotion.irritation = min(1.0, emotion.irritation + seeding_irritation)
                    emotion.updated_at = int(time.time() * 1000)
                    log.info(
                        "RAG Emotion Seeding applied",
                        matches_count=matches_count,
                        seeding_sadness=seeding_sadness,
                        seeding_irritation=seeding_irritation,
                        new_sadness=emotion.sadness,
                        new_irritation=emotion.irritation
                    )
    
            # Token Budget Management
            trimmed_lore, trimmed_memories, trimmed_history = ContextBudgetManager.enforce_budget(
                lore_chunks=lore_chunks,
                memories=memories,
                history=history
            )
            
            # 3. Prompt Engineering via ContextBuilder using trimmed context
            prompt = self.context_builder.build(
                emotion=emotion,
                attachment_bonus=attachment_bonus_raw,
                memories=trimmed_memories,
                lore_chunks=trimmed_lore,
                history=trimmed_history,
                user_message=user_message,
                rag_decisions=rag_decisions
            )

            pipeline_tracker.add_step("context_building", {
                "system_prompt": prompt.system,
                "history_count": len(prompt.history),
                "token_budget_context": len(prompt.system) // 4 + len(prompt.user_message) // 4
            })
            
            # 4. LLM Generation (Unified Single-Call)
            response = await self.llm.generate(prompt)
            chisa_reply = response.parsed.get("response")
            
            # Fallback if the model hallucinated the JSON key but returned valid JSON
            if not chisa_reply and response.parsed:
                for val in response.parsed.values():
                    if isinstance(val, str) and val.strip():
                        chisa_reply = val
                        break
                        
            chisa_reply = chisa_reply or ""
            if not chisa_reply.strip():
                log.warning("LLM returned empty response or failed to parse", user_id=user_id)
                raise ValueError("Empty response from LLM")
            
            # Extract sentiment flags safely from the unified response
            user_sentiment = response.parsed.get("user_sentiment") or {}
            if not isinstance(user_sentiment, dict):
                user_sentiment = {}
                
            is_positive = user_sentiment.get("is_positive", False)
            is_negative = user_sentiment.get("is_negative", False)
            is_rude = user_sentiment.get("is_rude", False)
            is_neutral = user_sentiment.get("is_neutral", True)
            
            chisa_sentiment = response.parsed.get("chisa_sentiment") or {}
            if not isinstance(chisa_sentiment, dict):
                chisa_sentiment = {}
                
            chisa_sad = chisa_sentiment.get("is_sad", False)
            chisa_happy = chisa_sentiment.get("is_happy", False)
            chisa_annoyed = chisa_sentiment.get("is_annoyed", False)
            chisa_flustered = chisa_sentiment.get("is_flustered", False)
            
            # 5. Cập nhật Emotion State based on LLM Flags & Save to database for next turn
            emotion_delta = self.emotion_engine.update(
                emotion,
                is_positive=is_positive,
                is_negative=is_negative,
                is_rude=is_rude,
                is_neutral=is_neutral,
                chisa_sad=chisa_sad,
                chisa_happy=chisa_happy,
                chisa_annoyed=chisa_annoyed,
                chisa_flustered=chisa_flustered
            )
            await emotion_repo.update_emotion(emotion)

            pipeline_tracker.add_step("emotion_update", {
                "old_emotions": current_emotions,
                "new_emotions": {
                    "joy": emotion.joy,
                    "sadness": emotion.sadness,
                    "trust": emotion.trust,
                    "irritation": emotion.irritation,
                    "attachment": emotion.attachment + attachment_bonus_raw
                },
                "user_sentiment": {
                    "is_positive": is_positive,
                    "is_negative": is_negative,
                    "is_rude": is_rude,
                    "is_neutral": is_neutral
                },
                "chisa_sentiment": {
                    "is_sad": chisa_sad,
                    "is_happy": chisa_happy,
                    "is_annoyed": chisa_annoyed,
                    "is_flustered": chisa_flustered
                }
            })
            
            # Calculate memory importance from MemoryManager
            importance_score = self.memory_manager.calculate_importance(user_message, emotion_delta)
            
            # 6. Post-processing
            total_tokens = response.input_tokens + response.output_tokens
            log.info(
                "LLM Token Consumption", 
                user_id=user_id, 
                input_tokens=response.input_tokens, 
                output_tokens=response.output_tokens, 
                total_tokens=total_tokens
            )
    
            # Save user message AFTER successful LLM call (prevents duplicates on retry)
            await conv_repo.save_message(conv_id, user_uuid, "user", user_message, is_success=True)
            
            await conv_repo.save_message(
                conv_id, 
                user_uuid, 
                "assistant", 
                chisa_reply, 
                token_count=total_tokens,
                is_success=True
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
            
            
            # Re-compute emotions after update so the frontend gets the true post-chat/time-decayed emotional state
            # Dampen attachment_bonus when Chisa is emotionally withdrawing (hurt + irritated)
            # This prevents the interaction-count bonus from overriding genuine emotional distress
            attachment_bonus = attachment_bonus_raw
            if emotion.sadness > 0.15 and emotion.irritation > 0.10:
                # Dampening scales with severity: mild hurt = 70% bonus, severe = near-0% bonus
                dampen_factor = max(0.0, 1.0 - (emotion.sadness * emotion.irritation * 3.0))
                attachment_bonus = attachment_bonus_raw * dampen_factor
                log.debug(
                    "Attachment bonus dampened",
                    raw=f"{attachment_bonus_raw:.4f}",
                    dampened=f"{attachment_bonus:.4f}",
                    dampen_factor=f"{dampen_factor:.3f}",
                    sadness=f"{emotion.sadness:.3f}",
                    irritation=f"{emotion.irritation:.3f}",
                )
            
            updated_emotions = {
                "joy": emotion.joy,
                "sadness": emotion.sadness,
                "trust": emotion.trust,
                "irritation": emotion.irritation,
                "attachment": emotion.attachment + attachment_bonus
            }
            
            log.info("ChatEngine cycle complete", user_id=user_id, attachment_bonus=attachment_bonus, attachment_bonus_raw=attachment_bonus_raw)
            return chisa_reply, updated_emotions
        except Exception as e:
            log.warning("Chat generation failed, saving user message as failed/unsuccessful", user_id=user_id, error=str(e))
            try:
                await session.rollback()
                await conv_repo.save_message(conv_id, user_uuid, "user", user_message, is_success=False)
            except Exception as db_err:
                log.error("Failed to save failed message to database", error=str(db_err))
            raise e
