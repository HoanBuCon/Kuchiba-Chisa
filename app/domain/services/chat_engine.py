import time
import math
import uuid
import asyncio
from typing import Tuple, Dict, Any, List, Optional, Callable
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings

from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.infrastructure.database.models.emotion_state import EmotionState
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service, MemoryPayload
from app.domain.services.emotion_engine import EmotionEngine
from app.domain.services.intent_classifier import IntentClassifier, ChatIntent
from app.domain.services.tool_router import LLMToolRouter
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.budget_mode import BudgetMode
from app.domain.services.memory_extractor import MemoryExtractor
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.infrastructure.database.repositories.emotion_repository import SqlAlchemyEmotionRepository
from app.infrastructure.database.repositories.conversation_repository import SqlAlchemyConversationRepository
from app.infrastructure.logging.logger import get_logger
from app.shared.utils.query_cleaner import clean_query_for_rag
from app.shared.utils.user_identity import normalize_user_id
from app.domain.services.rag import rag_pipeline

log = get_logger(__name__)

class ChatEngine:
    """
    Production-grade chat orchestrator using Phase 1-10 pipeline.
    """
    def __init__(
        self,
        embedder: IEmbeddingProvider,
        llm: BaseLLMAdapter,
        context_builder: ContextBuilder,
        memory_extractor: MemoryExtractor,
    ):
        self.embedder = embedder
        self.llm = llm
        self.context_builder = context_builder
        self.memory_extractor = memory_extractor
        self.intent_classifier = IntentClassifier(llm=llm, embedder=embedder)
        self.tool_router = LLMToolRouter(llm=llm, embedder=embedder)
        self.emotion_engine = EmotionEngine()

    async def get_emotion_state(self, session: AsyncSession, user_id: str) -> EmotionState:
        user_uuid = normalize_user_id(user_id)
        emotion_repo = SqlAlchemyEmotionRepository(session)
        return await emotion_repo.get_emotion_state(user_uuid)

    async def get_history(self, session: AsyncSession, user_id: str, limit: int = 50) -> list[dict[str, str]]:
        user_uuid = normalize_user_id(user_id)
        user_repo = SqlAlchemyUserRepository(session)
        conv_repo = SqlAlchemyConversationRepository(session)
        
        await user_repo.get_or_create_user(user_uuid)
        conv_id = await conv_repo.get_or_create_conversation(user_uuid)
        return await conv_repo.get_recent_history(user_uuid, conv_id, limit)

    async def chat(self, session: AsyncSession, user_id: str, user_message: str, on_token: Optional[Callable[[str], Any]] = None) -> Tuple[str, Dict[str, float]]:
        log.info("Starting ChatEngine cycle", user_id=user_id)
        
        # 1. Initialize repositories & Load context
        user_uuid = normalize_user_id(user_id)
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

        history = await conv_repo.get_recent_history(user_uuid, conv_id, limit=40)

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
            is_st = IntentClassifier.is_small_talk(user_message)
            
            query_vector = None
            cleaned_query = ""
            if not is_st:
                cleaned_query = clean_query_for_rag(user_message)
                
            intents, query_vector = await self.intent_classifier.classify(user_message, query_vector)
            intent_values = [i.value for i in intents]

            # If RAG is triggered but we skipped semantic routing (fast-path rules matched), generate query_vector now
            if not is_st and query_vector is None:
                rag_intents = {ChatIntent.CHARACTER_LORE, ChatIntent.WORLD_LORE, ChatIntent.STORY_LORE, ChatIntent.MEMORY}
                if any(intent in rag_intents for intent in intents):
                    query_vector = await self.embedder.embed_text(cleaned_query)
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
            tool_res = None
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

            if tool_name == "web_search" and tool_res:
                from app.domain.services.tools.web_search import web_search_trace_payload
                pipeline_tracker.add_step(
                    "web_search",
                    web_search_trace_payload(
                        tool_res,
                        source="system_action",
                        original_message=user_message,
                    ),
                )
            
            # 5. E2E RAG Pipeline (Retrieval, Context Assessment, and Loop Thinking)
            rag_context = await rag_pipeline.retrieve_and_align(
                session=session,
                user_id=user_id,
                user_message=user_message,
                query_vector=query_vector,
                cleaned_query=cleaned_query,
                intents=intents,
                current_emotions=current_emotions,
                history=history,
                llm=self.llm,
                embedder=self.embedder,
                web_search_tool=self.tool_router.tool_map.get("web_search"),
                is_small_talk=is_st,
                conversation_summary=conv_summary,
            )
            
            lore_chunks = rag_context.lore_chunks
            memories = rag_context.memories
            tool_output_msg = rag_context.tool_output_msg
            is_aligned = rag_context.is_aligned
            alignment_reason = rag_context.alignment_reason



            # 7. Pass search results / tool output through context builder (NOT as user message)
            # Injecting into user_message would confuse the LLM — it would treat results as user input.
            # Instead, we pass it separately and let the context builder place it in the system prompt.
            final_user_message = user_message

            budget_mode = BudgetMode.resolve(
                is_small_talk=is_st,
                has_thinking_steps=len(rag_context.thinking_steps) > 0,
            )

            build_result = self.context_builder.build(
                emotion=emotion,
                attachment_bonus=attachment_bonus_raw,
                memories=memories,
                lore=lore_chunks,
                history=history,
                user_message=final_user_message,
                intent_name=", ".join(intent_values),
                tool_result=tool_output_msg or "",
                conversation_summary=conv_summary,
                budget_mode=budget_mode,
            )
            prompt = build_result.prompt
            budget_audit = build_result.audit

            pipeline_tracker.add_step("context_building", {
                "system_prompt": prompt.system,
                "history_count": len(prompt.history),
                "budget_mode": budget_mode.value,
                "budget_audit": budget_audit.to_dict(),
                "total_estimated_tokens": budget_audit.total_used,
                "effective_ceiling": budget_audit.effective_ceiling,
                "within_budget": budget_audit.within_budget,
                "token_source": "budget_estimate",
                "token_source_note": "Ước lượng nội bộ (2 ký tự/token + headroom). Khác số Input API ở bước LLM · Trả lời Chisa.",
            })
            
            # 6. LLM Generation
            from app.infrastructure.logging.llm_logger import llm_call_purpose
            llm_call_purpose.set("chat_response")
            
            if on_token:
                class IncrementalJsonParser:
                    def __init__(self):
                        self.buffer = ""
                        self.found_key = False
                        self.in_string = False
                        self.escaped = False
                        self.finished = False

                    def feed(self, chunk: str) -> str:
                        if self.finished:
                            return ""
                        
                        output = []
                        if not self.found_key:
                            self.buffer += chunk
                            import re
                            match = re.search(r'"response"\s*:\s*"', self.buffer)
                            if match:
                                self.found_key = True
                                self.in_string = True
                                remaining = self.buffer[match.end():]
                                self.buffer = ""
                                for char in remaining:
                                    if self.escaped:
                                        if char == 'n':
                                            output.append('\n')
                                        elif char == 't':
                                            output.append('\t')
                                        else:
                                            output.append(char)
                                        self.escaped = False
                                    elif char == '\\':
                                        self.escaped = True
                                    elif char == '"':
                                        self.in_string = False
                                        self.finished = True
                                        break
                                    else:
                                        output.append(char)
                        else:
                            if self.in_string:
                                for char in chunk:
                                    if self.escaped:
                                        if char == 'n':
                                            output.append('\n')
                                        elif char == 't':
                                            output.append('\t')
                                        else:
                                            output.append(char)
                                        self.escaped = False
                                    elif char == '\\':
                                        self.escaped = True
                                    elif char == '"':
                                        self.in_string = False
                                        self.finished = True
                                        break
                                    else:
                                        output.append(char)
                        return "".join(output)

                parser = IncrementalJsonParser()
                raw_chunks = []
                async for chunk in self.llm.stream(prompt):
                    raw_chunks.append(chunk)
                    parsed_token = parser.feed(chunk)
                    if parsed_token:
                        if asyncio.iscoroutinefunction(on_token):
                            await on_token(parsed_token)
                        else:
                            on_token(parsed_token)
                
                raw_response = "".join(raw_chunks)
                parsed = await self.llm.validate_response(raw_response, prompt.response_schema)
                from app.shared.utils.token_estimator import TokenEstimator
                est_input = (
                    TokenEstimator.estimate(prompt.system)
                    + TokenEstimator.estimate_messages(prompt.history)
                    + TokenEstimator.estimate(prompt.user_message)
                )
                est_output = TokenEstimator.estimate(raw_response)

                from app.infrastructure.llm.adapters.base import LLMResponse
                response = LLMResponse(
                    raw_content=raw_response,
                    parsed=parsed,
                    input_tokens=est_input,
                    output_tokens=est_output,
                    model=self.llm._model,
                    finish_reason="stop",
                )

                try:
                    from app.infrastructure.logging.llm_logger import log_llm_transaction
                    await log_llm_transaction(prompt, response)
                except Exception as log_ex:
                    log.warning("Failed to log streaming transaction", error=str(log_ex))
            else:
                response = await self.llm.generate(prompt)

            chisa_reply = response.parsed.get("response")
            
            # Fallback if parsing has mismatched JSON key but correct raw JSON string
            if not chisa_reply and response.parsed:
                for val in response.parsed.values():
                    if isinstance(val, str) and val.strip():
                        chisa_reply = val
                        break
                        
            chisa_reply = chisa_reply or ""
            
            # Enforce output token limit control
            from app.shared.utils.token_estimator import TokenEstimator
            estimated_tokens = TokenEstimator.estimate(chisa_reply)
            if estimated_tokens > settings.MAX_RESPONSE_TOKENS:
                log.warning(
                    "Bot response exceeded maximum output token limit. Truncating.",
                    user_id=user_id,
                    estimated_tokens=estimated_tokens,
                    limit=settings.MAX_RESPONSE_TOKENS
                )
                chisa_reply = TokenEstimator.trim_to_budget(
                    chisa_reply,
                    settings.MAX_RESPONSE_TOKENS,
                    suffix="... (phản hồi bị cắt ngắn do vượt quá giới hạn độ dài)"
                )

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
            
            log.info("ChatEngine cycle complete", user_id=user_id)
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
