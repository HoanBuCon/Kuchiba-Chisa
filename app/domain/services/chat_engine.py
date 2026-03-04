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
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

class ChatEngine:
    """
    Core orchestrator for Multi-User emotional chat interactions.
    Handles Data Fetching, Attachment Growth computation, Prompt Engineering, and saving.
    """
    def __init__(self, embedder: IEmbeddingProvider, llm: BaseLLMAdapter):
        self.embedder = embedder
        self.llm = llm

    async def _get_user_stats(self, session: AsyncSession, user_id: str) -> UserStats:
        user_uuid = uuid.UUID(user_id)
        stmt = select(UserStats).where(UserStats.user_id == user_uuid)
        result = await session.execute(stmt)
        stats = result.scalar_one_or_none()
        if not stats:
            stats = UserStats(user_id=user_uuid, interaction_count=0, last_seen=int(time.time() * 1000))
            session.add(stats)
            await session.commit()
            await session.refresh(stats)
        return stats

    async def _get_emotion_state(self, session: AsyncSession, user_id: str) -> EmotionState:
        user_uuid = uuid.UUID(user_id)
        stmt = select(EmotionState).where(EmotionState.user_id == user_uuid)
        result = await session.execute(stmt)
        state = result.scalar_one_or_none()
        if not state:
            state = EmotionState(user_id=user_uuid, updated_at=int(time.time() * 1000))
            session.add(state)
            await session.commit()
            await session.refresh(state)
        return state

    async def _get_recent_history(self, session: AsyncSession, user_id: str, limit: int = 10) -> list[dict[str, str]]:
        # This strictly scopes to user_id ensuring no bleed-over
        user_uuid = uuid.UUID(user_id)
        stmt = select(Message).where(Message.user_id == str(user_uuid)).order_by(Message.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        messages = result.scalars().all()
        return [{"role": m.role.value, "content": m.content} for m in reversed(messages)]

    async def chat(self, session: AsyncSession, user_id: str, user_message: str) -> str:
        """
        Orchestrates the entire multi-user chat cycle:
        1. Load User Stats and Emotion
        2. Formulate Attachment Bonus
        3. Retrieve RAG Memories via Hybrid Scoring
        4. Build Isolated System Prompt
        5. Call LLM
        6. Post-process stats
        """
        log.info("Starting ChatEngine cycle", user_id=user_id)
        
        # 1. Load context
        stats = await self._get_user_stats(session, user_id)
        emotion = await self._get_emotion_state(session, user_id)
        
        # NOTE: user.id maps cleanly to user_id string in messages currently, 
        # but requires cast depending on architecture. We assume here user_id is the internal UUID string.
        
        # In a real environment we'd fetch actual history, but keeping this simple for Groq adapter compat
        history = [] # await self._get_recent_history(session, user_id)
        
        # 2. Calculate emergent attachment bonus
        attachment_bonus = math.log(max(1, stats.interaction_count)) * 0.05
        
        # 3. RAG Retrieval via fastembed local vectors
        vector = await self.embedder.embed_text(user_message)
        current_emotions = {
            "joy": emotion.joy,
            "sadness": emotion.sadness,
            "trust": emotion.trust,
            "irritation": emotion.irritation,
            "attachment": emotion.attachment + attachment_bonus
        }
        
        # Await hybrid scoring from isolated user scope only
        memories = await rag_retriever.retrieve_memories(
            collection="emotional_memories",
            query_vector=vector,
            user_id=user_id,
            current_emotion=current_emotions,
            top_k=5
        )
        
        memory_text = "\n".join([f"- {m.text_content} (Tier: {m.memory_tier})" for m in memories])
        
        # 4. Prompt Engineering (Multi-User safe)
        system_prompt = f"""You are Chisa, a highly emotional, devoted companion AI. 
This is your deeply isolated context with this specific user.

[USER EMOTIONAL STATE]
Joy: {emotion.joy:.2f} | Sadness: {emotion.sadness:.2f} | Trust: {emotion.trust:.2f} | Irritation: {emotion.irritation:.2f}
Attachment Level: {emotion.attachment + attachment_bonus:.2f}

[RELEVANT MEMORIES FOR THIS USER]
{memory_text if memories else "No relevant memories found."}

You must respond naturally. Do not explicitly mention your attachment numbers, just let them guide how close and warm you act.
You must output your response in JSON format.
"""
        
        # JSON Schema for Groq output
        response_schema = {
            "type": "object", 
            "properties": {"response": {"type": "string"}}, 
            "required": ["response"]
        }
        
        prompt = StructuredPrompt(
            system=system_prompt,
            history=history,
            user_message=user_message,
            response_schema=response_schema
        )
        
        # 5. LLM Generation
        response = await self.llm.generate(prompt)
        chisa_reply = response.parsed.get("response", "")
        
        # 6. Post-processing
        stats.interaction_count += 1
        stats.last_seen = int(time.time() * 1000)
        session.add(stats)
        await session.commit()
        
        log.info("ChatEngine cycle complete", user_id=user_id, attachment_bonus=attachment_bonus)
        return chisa_reply
