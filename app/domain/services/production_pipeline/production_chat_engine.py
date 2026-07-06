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
from app.domain.services.production_pipeline.tools.web_search import WebSearchAgentTool

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
        self.web_search_tool = WebSearchAgentTool()

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

    async def _assess_alignment(self, user_message: str, context_text: str) -> Tuple[bool, str]:
        """
        Assess if the retrieved context contains enough factual information to answer the question.
        """
        system_prompt = (
            "You are an Information Alignment Assessor.\n"
            "Evaluate whether the retrieved context contains enough specific, factual, and relevant information to fully "
            "and accurately answer the user's question without any hallucination.\n"
            "If the user is asking about real-time, dynamic information (like current events, prices, live statistics, etc.) "
            "and the exact current numbers/details are not present in the context, you MUST set 'is_aligned' to false.\n"
            "If the user's message is simple casual conversation (greeting, small talk, emotional check-in) that doesn't "
            "require factual data lookup, set 'is_aligned' to true.\n"
            "You MUST output the result as a valid JSON object matching the requested schema."
        )

        user_prompt = (
            f"[User Question]: \"{user_message}\"\n\n"
            f"[Retrieved Context]:\n{context_text}"
        )

        schema = {
            "type": "object",
            "properties": {
                "is_aligned": {"type": "boolean"},
                "reason": {"type": "string"}
            },
            "required": ["is_aligned", "reason"]
        }

        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=user_prompt,
            response_schema=schema,
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={}
        )

        try:
            response = await self.llm.generate(prompt)
            parsed = response.parsed or {}
            is_aligned = parsed.get("is_aligned", True)
            reason = parsed.get("reason", "No reason provided")
            log.info("Information alignment check complete", is_aligned=is_aligned, reason=reason)
            return is_aligned, reason
        except Exception as e:
            log.warning("Information alignment check failed, defaulting to True", error=str(e))
            return True, "Check failed, defaulting to aligned"

    async def _run_thinking_loop(
        self,
        session: AsyncSession,
        user_id: str,
        user_message: str,
        history: List[Dict[str, str]],
        initial_context: str
    ) -> str:
        """
        Runs a reasoning loop to search the web for missing information.
        """
        from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
        
        log.info("Activating Loop Thinking Agent for user query", user_message=user_message)
        
        # Format history for the model
        history_lines = []
        for msg in history[-6:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            history_lines.append(f"{role.upper()}: {content}")
        history_str = "\n".join(history_lines) if history_lines else "(No history)"

        current_context = initial_context
        max_cycles = 2

        for i in range(1, max_cycles + 1):
            log.info("Starting thinking loop cycle", cycle=i)
            
            system_prompt = (
                "You are a Loop Thinking Agent for Kuchiba Chisa (Wuthering Waves).\n"
                "Your goal is to gather all necessary facts to answer the user's question.\n"
                "Analyze the conversation history, the user's question, and the current accumulated context.\n"
                "Determine if you have enough factual, correct information to answer the user's query.\n"
                "If yes, set 'has_enough_info' to true.\n"
                "If no, write your step-by-step reasoning under 'thinking', set 'has_enough_info' to false, "
                "and generate a single, highly-optimized search query under 'search_query' (in Vietnamese or English) "
                "to find the missing factual information.\n"
                "You MUST output the result as a valid JSON object matching the requested schema."
            )

            user_prompt = (
                f"[Conversation History]:\n{history_str}\n\n"
                f"[User Question]: \"{user_message}\"\n\n"
                f"[Current Context]:\n{current_context}"
            )

            schema = {
                "type": "object",
                "properties": {
                    "thinking": {"type": "string"},
                    "has_enough_info": {"type": "boolean"},
                    "search_query": {"type": "string"}
                },
                "required": ["thinking", "has_enough_info"]
            }

            prompt = StructuredPrompt(
                system=system_prompt,
                history=[],
                user_message=user_prompt,
                response_schema=schema,
                retrieved_memories=[],
                retrieved_lore=[],
                rag_decisions={}
            )

            try:
                response = await self.llm.generate(prompt)
                parsed = response.parsed or {}
                thinking = parsed.get("thinking", "")
                has_enough_info = parsed.get("has_enough_info", True)
                search_query = parsed.get("search_query", "")

                log.info("Thinking cycle complete", cycle=i, has_enough_info=has_enough_info, search_query=search_query)

                if has_enough_info or not search_query:
                    pipeline_tracker.add_step(f"thinking_loop_cycle_{i}", {
                        "thinking": thinking,
                        "has_enough_info": True,
                        "search_query": "",
                        "search_result": "No further search needed."
                    })
                    break

                # Execute search
                search_res = await self.web_search_tool.execute(
                    session=session,
                    user_id=user_id,
                    user_message=search_query,
                    llm=self.llm,
                    embedder=self.embedder,
                    history=history
                )
                search_result_text = search_res.get("message", "No search results returned.")

                # Append to current context
                current_context += f"\n\n[Thinking Cycle {i} Search Results for '{search_query}']:\n{search_result_text}"

                pipeline_tracker.add_step(f"thinking_loop_cycle_{i}", {
                    "thinking": thinking,
                    "has_enough_info": False,
                    "search_query": search_query,
                    "search_result": search_result_text
                })

            except Exception as e:
                log.error("Error in thinking loop cycle", cycle=i, error=str(e))
                pipeline_tracker.add_step(f"thinking_loop_cycle_{i}", {
                    "thinking": f"Error occurred: {str(e)}",
                    "has_enough_info": True,
                    "search_query": "",
                    "search_result": ""
                })
                break

        return current_context

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
        
        # Fetch conversation summary and messages count
        from sqlalchemy import select, func
        from app.infrastructure.database.models.conversation import Conversation
        from app.infrastructure.database.models.message import Message

        conv_stmt = select(Conversation).where(Conversation.id == conv_id)
        conv_obj = (await session.execute(conv_stmt)).scalar_one_or_none()
        conv_summary = conv_obj.summary if conv_obj else None

        msg_count_stmt = (
            select(func.count(Message.id))
            .where(
                Message.conversation_id == conv_id,
                Message.is_success == True
            )
        )
        total_msgs = (await session.execute(msg_count_stmt)).scalar() or 0

        # Trigger auto-summarize if count >= 20
        if total_msgs >= 20 and (not conv_summary or total_msgs % 10 == 0):
            asyncio.create_task(self._auto_summarize_conversation(user_id, conv_id))

        history = await conv_repo.get_recent_history(user_uuid, conv_id)
        
        # Initialize ContextVars for request-scoped logging
        from app.infrastructure.logging.llm_logger import request_question_idx, request_turn_idx, log_routing_transaction
        
        question_idx = len([m for m in history if m.get("role") == "user"]) + 1
        request_question_idx.set(question_idx)
        request_turn_idx.set(1)
        
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

            from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
            pipeline_tracker.add_step("intent_classification", {
                "is_small_talk": is_st,
                "intents": intent_values,
                "cleaned_query": cleaned_query
            })
            
            # 4. Check for System Actions (Tầng 2 - LLM Tool Router)
            tool_output_msg = None
            tool_name = "none"
            tool_score = 0.0
            if ChatIntent.SYSTEM_ACTION in intents:
                tool_res = await self.tool_router.execute(
                    user_message=cleaned_query or user_message,  # dùng cleaned để tránh Discord emoji
                    session=session,
                    user_id=user_id,
                    query_vector=query_vector,
                    history=history
                )
                tool_output_msg = tool_res.get("message")
                tool_name = tool_res.get("tool", "none")
                tool_score = tool_res.get("score", 0.0)
                log.info("Tool executed from SYSTEM_ACTION intent", tool_res=tool_res)
                
                # Note: clear_chat_history tool has been removed from LLM Tool Router.
                # If any system action returns a tool result, handle it.
                pass

            # Log Semantic Routing & Tool Decisions
            await log_routing_transaction(
                user_message=user_message,
                is_small_talk=is_st,
                intents=intent_values,
                tool_name=tool_name,
                tool_score=tool_score,
                tool_result=tool_output_msg or ""
            )

            pipeline_tracker.add_step("tool_routing", {
                "tool_name": tool_name,
                "tool_score": tool_score,
                "tool_result": tool_output_msg or ""
            })
            
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

            pipeline_tracker.add_step("rag_retrieval", {
                "lore_collections_queried": [
                    col for col, b in {
                        "character_lore": ChatIntent.CHARACTER_LORE in intents,
                        "world_lore": ChatIntent.WORLD_LORE in intents,
                        "story_lore": ChatIntent.STORY_LORE in intents
                    }.items() if b
                ],
                "retrieved_lore_chunks": lore_chunks,
                "retrieved_memories": memories
            })
            
            # 6. Assess context alignment and run thinking loop if needed
            context_pieces = []
            if tool_output_msg:
                context_pieces.append(f"[Retrieved Tool Result ({tool_name})]:\n{tool_output_msg}")
            if lore_chunks:
                context_pieces.append("[Retrieved Lore Chunks]:\n" + "\n".join(lore_chunks))
            if memories:
                context_pieces.append("[Retrieved Memories]:\n" + "\n".join(memories))
            
            retrieved_context_str = "\n\n".join(context_pieces) if context_pieces else "(No context retrieved)"

            is_aligned = True
            alignment_reason = "Small talk or system bypass"
            if not is_st and query_vector:
                is_aligned, alignment_reason = await self._assess_alignment(user_message, retrieved_context_str)

            pipeline_tracker.add_step("information_alignment_check", {
                "is_aligned": is_aligned,
                "reason": alignment_reason
            })

            if not is_aligned:
                # Activate thinking loop agent to fetch deep web search data
                retrieved_context_str = await self._run_thinking_loop(
                    session=session,
                    user_id=user_id,
                    user_message=user_message,
                    history=history,
                    initial_context=retrieved_context_str
                )
                tool_output_msg = retrieved_context_str

            # 7. Pass search results / tool output through context builder (NOT as user message)
            # Injecting into user_message would confuse the LLM — it would treat results as user input.
            # Instead, we pass it separately and let the context builder place it in the system prompt.
            final_user_message = user_message

            # 8. Build prompt context using ProductionContextBuilder
            prompt = self.context_builder.build(
                emotion=emotion,
                attachment_bonus=attachment_bonus_raw,
                memories=memories,
                lore=lore_chunks,
                history=history,
                user_message=final_user_message,
                intent_name=", ".join(intent_values),
                tool_result=tool_output_msg or "",
                conversation_summary=conv_summary,
            )

            pipeline_tracker.add_step("context_building", {
                "system_prompt": prompt.system,
                "history_count": len(prompt.history),
                "token_budget_context": len(prompt.system) // 4 + len(prompt.user_message) // 4
            })
            
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

    async def _auto_summarize_conversation(self, user_id: str, conv_id: uuid.UUID) -> None:
        """
        Background task to auto-summarize the conversation if message count >= 20.
        """
        log.info("Starting background conversation auto-summarization...", conv_id=str(conv_id))
        from app.infrastructure.database.engine import AsyncSessionFactory
        from sqlalchemy import select
        from app.infrastructure.database.models.conversation import Conversation
        from app.infrastructure.database.models.message import Message

        async with AsyncSessionFactory() as session:
            try:
                # Fetch all messages in this conversation (ordered chronologically)
                msg_stmt = (
                    select(Message)
                    .where(
                        Message.conversation_id == conv_id,
                        Message.is_success == True
                    )
                    .order_by(Message.created_at.asc())
                )
                msgs = (await session.execute(msg_stmt)).scalars().all()
                if not msgs:
                    log.info("No messages in conversation to auto-summarize", conv_id=str(conv_id))
                    return

                # Build chat transcript for LLM
                chat_transcript = "\n".join([f"{m.role.value.upper()}: {m.content}" for m in msgs])

                system_prompt = (
                    "You are a conversation summarizer for Kuchiba Chisa, a character from Wuthering Waves.\n"
                    "Analyze the conversation transcript provided and summarize the key discussion points, "
                    "user's preferences, interests, emotional vibe, and current relationship context.\n"
                    "Keep the summary concise, informative, in Vietnamese, and write it in a structured paragraph or bullet points.\n"
                    "You MUST output the result as a valid JSON object matching the requested schema containing a 'summary' key."
                )

                prompt = StructuredPrompt(
                    system=system_prompt,
                    history=[],
                    user_message=f"Please summarize this conversation transcript:\n\n{chat_transcript}",
                    response_schema=self.tool_router.SUMMARIZE_CONVERSATION_SCHEMA,
                    retrieved_memories=[],
                    retrieved_lore=[],
                    rag_decisions={}
                )

                response = await self.llm.generate(prompt)
                summary_text = (response.parsed or {}).get("summary", "").strip()
                if not summary_text:
                    summary_text = response.raw_content or ""

                if summary_text:
                    # Get conversation object and update it
                    conv_stmt = select(Conversation).where(Conversation.id == conv_id)
                    conv = (await session.execute(conv_stmt)).scalar_one_or_none()
                    if conv:
                        conv.summary = summary_text
                        await session.commit()
                        log.info("Conversation auto-summarized successfully", conv_id=str(conv_id))
            except Exception as e:
                log.error("Failed to run background auto-summarization", error=str(e), conv_id=str(conv_id))
