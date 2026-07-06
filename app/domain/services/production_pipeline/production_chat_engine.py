import time
import math
import uuid
import asyncio
from typing import Optional, Tuple, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.infrastructure.database.models.emotion_state import EmotionState
from app.infrastructure.database.models.user_stats import UserStats
from app.infrastructure.database.models.message import Message
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service, MemoryPayload
from app.domain.services.emotion_engine import EmotionEngine
from app.domain.services.production_pipeline.intent_classifier import IntentClassifier, ChatIntent
from app.domain.services.production_pipeline.tool_router import LLMToolRouter
from app.domain.services.production_pipeline.production_context_builder import ProductionContextBuilder
from app.domain.services.production_pipeline.memory_extractor import MemoryExtractor
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.infrastructure.database.repositories.emotion_repository import SqlAlchemyEmotionRepository
from app.infrastructure.database.repositories.conversation_repository import SqlAlchemyConversationRepository
from app.infrastructure.logging.logger import get_logger
from app.shared.utils.query_cleaner import clean_query_for_rag
from app.domain.services.rag_retriever import rag_retriever

log = get_logger(__name__)

class ProductionChatEngine:
    """
    Production-grade chat orchestrator using Phase 1-10 pipeline.
    """
    def __init__(
        self,
        embedder: IEmbeddingProvider,
        llm: BaseLLMAdapter,
        context_builder: ProductionContextBuilder,
        memory_extractor: MemoryExtractor,
    ):
        self.embedder = embedder
        self.llm = llm
        self.context_builder = context_builder
        self.memory_extractor = memory_extractor
        self.intent_classifier = IntentClassifier(llm=llm, embedder=embedder)
        self.tool_router = LLMToolRouter(llm=llm, embedder=embedder)
        self.emotion_engine = EmotionEngine()

    def _deduplicate_parent_child(self, candidates: List[Dict[str, Any]]) -> List[str]:
        seen_parents = set()
        lore_chunks = []
        for cand in candidates:
            payload = cand.get("payload", {})
            parent_id = payload.get("parent_id")
            parent_text = payload.get("parent_full_text")
            text = parent_text if parent_text else payload.get("text_content", "")
            if not text:
                continue
            if parent_id:
                if parent_id not in seen_parents:
                    seen_parents.add(parent_id)
                    lore_chunks.append(text)
            else:
                lore_chunks.append(text)
        return lore_chunks

    async def get_emotion_state(self, session: AsyncSession, user_id: str) -> EmotionState:
        user_uuid = uuid.UUID(user_id)
        emotion_repo = SqlAlchemyEmotionRepository(session)
        return await emotion_repo.get_emotion_state(user_uuid)

    async def get_history(self, session: AsyncSession, user_id: str, limit: int = 50) -> list[dict[str, str]]:
        user_uuid = uuid.UUID(user_id)
        user_repo = SqlAlchemyUserRepository(session)
        conv_repo = SqlAlchemyConversationRepository(session)
        
        await user_repo.get_or_create_user(user_uuid)
        conv_id = await conv_repo.get_or_create_conversation(user_uuid)
        return await conv_repo.get_recent_history(user_uuid, conv_id, limit)

    async def chat(self, session: AsyncSession, user_id: str, user_message: str) -> Tuple[str, Dict[str, float]]:
        log.info("Starting ProductionChatEngine cycle", user_id=user_id)
        
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
        
        try:
            # 2. Formulate Attachment Bonus and current emotions snapshot
            attachment_bonus_raw = math.log(max(1, stats.interaction_count)) * 0.05
            current_emotions = {
                "joy": emotion.joy,
                "sadness": emotion.sadness,
                "trust": emotion.trust,
                "irritation": emotion.irritation,
                "attachment": emotion.attachment + attachment_bonus_raw
            }

            # 3. Classify intent (Checking small talk regex fast-path first)
            from app.domain.services.rag_router import RAGRouter
            is_st = RAGRouter.is_small_talk(user_message)
            
            query_vector = None
            cleaned_query = ""
            if not is_st:
                cleaned_query = clean_query_for_rag(user_message)
                query_vector = await self.embedder.embed_text(cleaned_query)
                
            intents = await self.intent_classifier.classify(user_message, query_vector)
            intent_values = [i.value for i in intents]
            log.info("Production query classified", intents=intent_values, user_id=user_id)
            
            # 4. Check for System Actions (Tầng 2 - LLM Tool Router)
            tool_output_msg = None
            if ChatIntent.SYSTEM_ACTION in intents:
                tool_res = await self.tool_router.execute(
                    user_message=cleaned_query or user_message,  # dùng cleaned để tránh Discord emoji
                    session=session,
                    user_id=user_id,
                    query_vector=query_vector
                )
                tool_output_msg = tool_res.get("message")
                log.info("Tool executed from SYSTEM_ACTION intent", tool_res=tool_res)
                
                # Reset local memory variables if database was cleared
                if tool_res.get("tool") == "clear_chat_history":
                    stats = await user_repo.get_user_stats(user_uuid)
                    emotion = await emotion_repo.get_emotion_state(user_uuid)
                    conv_id = await conv_repo.get_or_create_conversation(user_uuid)
                    history = []
                    current_emotions = {
                        "joy": emotion.joy,
                        "sadness": emotion.sadness,
                        "trust": emotion.trust,
                        "irritation": emotion.irritation,
                        "attachment": emotion.attachment + attachment_bonus_raw
                    }
            
            # 5. Retrieve RAG context based on classified intents
            lore_chunks: List[str] = []
            memories: List[str] = []
            
            # Skip RAG retrieve entirely if it is only small talk (ChatIntent.OTHER)
            if query_vector and any(i not in [ChatIntent.OTHER, ChatIntent.SYSTEM_ACTION] for i in intents):
                # Set up retrieval tasks to run concurrently
                retrieval_tasks = []
                active_intents = []
                
                if ChatIntent.CHARACTER_LORE in intents:
                    active_intents.append(ChatIntent.CHARACTER_LORE)
                    retrieval_tasks.append(
                        rag_retriever.retrieve_lore_parent_child(
                            collection="character_lore",
                            query_vector=query_vector,
                            query_text=cleaned_query,
                            top_k=6,
                            score_threshold=0.35
                        )
                    )
                if ChatIntent.WORLD_LORE in intents:
                    active_intents.append(ChatIntent.WORLD_LORE)
                    retrieval_tasks.append(
                        rag_retriever.retrieve_lore_parent_child(
                            collection="world_lore",
                            query_vector=query_vector,
                            query_text=cleaned_query,
                            top_k=6,
                            score_threshold=0.35
                        )
                    )
                if ChatIntent.STORY_LORE in intents:
                    active_intents.append(ChatIntent.STORY_LORE)
                    retrieval_tasks.append(
                        rag_retriever.retrieve_lore_parent_child(
                            collection="story_lore",
                            query_vector=query_vector,
                            query_text=cleaned_query,
                            top_k=6,
                            score_threshold=0.35
                        )
                    )
                if ChatIntent.MEMORY in intents:
                    active_intents.append(ChatIntent.MEMORY)
                    retrieval_tasks.append(
                        rag_retriever.retrieve_memories(
                            collection="memories",
                            query_vector=query_vector,
                            user_id=user_id,
                            current_emotion=current_emotions,
                            limit=10,
                            top_k=5
                        )
                    )
                
                if retrieval_tasks:
                    results = await asyncio.gather(*retrieval_tasks)
                    for intent_type, retrieved_data in zip(active_intents, results):
                        if intent_type == ChatIntent.MEMORY:
                            memories.extend([m.text_content for m in retrieved_data if m.text_content])
                        else:
                            lore_chunks.extend(retrieved_data)
            
            # 6. Pass search results / tool output through context builder (NOT as user message)
            # Injecting into user_message would confuse the LLM — it would treat results as user input.
            # Instead, we pass it separately and let the context builder place it in the system prompt.
            final_user_message = user_message

            # 7. Build prompt context using ProductionContextBuilder
            prompt = self.context_builder.build(
                emotion=emotion,
                attachment_bonus=attachment_bonus_raw,
                memories=memories,
                lore=lore_chunks,
                history=history,
                user_message=final_user_message,
                intent_name=", ".join(intent_values),
                tool_result=tool_output_msg or "",
            )
            
            # 6. LLM Generation
            response = await self.llm.generate(prompt)
            chisa_reply = response.parsed.get("response")
            
            # Fallback if parsing has mismatched JSON key but correct raw JSON string
            if not chisa_reply and response.parsed:
                for val in response.parsed.values():
                    if isinstance(val, str) and val.strip():
                        chisa_reply = val
                        break
                        
            chisa_reply = chisa_reply or ""
            if not chisa_reply.strip():
                log.warning("LLM returned empty response or failed to parse JSON in production pipeline", user_id=user_id)
                raise ValueError("Empty response from LLM")
                
            # Extract sentiment flags safely with defensive type checking
            user_sentiment = response.parsed.get("user_sentiment")
            if not isinstance(user_sentiment, dict):
                user_sentiment = {}
            is_positive = user_sentiment.get("is_positive", False)
            is_negative = user_sentiment.get("is_negative", False)
            is_rude = user_sentiment.get("is_rude", False)
            is_neutral = user_sentiment.get("is_neutral", True)
            
            chisa_sentiment = response.parsed.get("chisa_sentiment")
            if not isinstance(chisa_sentiment, dict):
                chisa_sentiment = {}
            chisa_sad = chisa_sentiment.get("is_sad", False)
            chisa_happy = chisa_sentiment.get("is_happy", False)
            chisa_annoyed = chisa_sentiment.get("is_annoyed", False)
            chisa_flustered = chisa_sentiment.get("is_flustered", False)
            
            # 7. Update Emotion State
            self.emotion_engine.update(
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
            
            # 8. Save messages to Postgres
            total_tokens = response.input_tokens + response.output_tokens
            await conv_repo.save_message(conv_id, user_uuid, "user", user_message, is_success=True)
            await conv_repo.save_message(
                conv_id,
                user_uuid,
                "assistant",
                chisa_reply,
                token_count=total_tokens,
                is_success=True
            )
            
            stats.interaction_count += 1
            stats.last_seen = int(time.time() * 1000)
            await user_repo.update_stats(stats)
            
            # 9. Trigger background fact extraction (asynchronous task)
            asyncio.create_task(
                self.memory_extractor.extract_and_store(
                    user_id=user_id,
                    conversation_id=str(conv_id),
                    user_message=user_message
                )
            )
            
            # 10. Periodically trigger background summarization (every 50 interactions)
            if stats.interaction_count > 0 and stats.interaction_count % 50 == 0:
                asyncio.create_task(
                    self._summarize_and_store_memories(
                        user_id=user_id,
                        conv_id=str(conv_id),
                        history=history[-40:]
                    )
                )
                
            # Recompute dampening details for return
            attachment_bonus = attachment_bonus_raw
            if emotion.sadness > 0.15 and emotion.irritation > 0.10:
                dampen_factor = max(0.0, 1.0 - (emotion.sadness * emotion.irritation * 3.0))
                attachment_bonus = attachment_bonus_raw * dampen_factor
                
            updated_emotions = {
                "joy": emotion.joy,
                "sadness": emotion.sadness,
                "trust": emotion.trust,
                "irritation": emotion.irritation,
                "attachment": emotion.attachment + attachment_bonus
            }
            
            log.info("ProductionChatEngine cycle complete", user_id=user_id)
            return chisa_reply, updated_emotions
            
        except Exception as e:
            log.warning("Production chat generation failed, saving user message as failed", user_id=user_id, error=str(e))
            try:
                await session.rollback()
                await conv_repo.save_message(conv_id, user_uuid, "user", user_message, is_success=False)
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
                            await qdrant_service.upsert_memory(
                                collection="memories",
                                point_id=point_id,
                                vector=vector,
                                payload=payload
                            )
                    log.info("Successfully summarized conversation and saved points to memories collection", user_id=user_id)
        except Exception as e:
            log.error("Failed to run background summarization for memories collection", error=str(e), user_id=user_id)
