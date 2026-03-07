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

from app.domain.services.context_builder import ContextBuilder
from app.domain.services.memory_manager import MemoryManager
from app.domain.services.emotion_engine import EmotionEngine

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

    async def _get_or_create_user(self, session: AsyncSession, user_id: str) -> None:
        from app.infrastructure.database.models.user import User
        user_uuid = uuid.UUID(user_id)
        stmt = select(User).where(User.id == user_uuid)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            user = User(id=user_uuid, username=f"web_user_{user_id[:6]}")
            session.add(user)
            await session.commit()

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

    async def _get_or_create_conversation(self, session: AsyncSession, user_id: str) -> uuid.UUID:
        user_uuid = uuid.UUID(user_id)
        # Get the most recent active conversation
        from app.infrastructure.database.models.conversation import Conversation
        stmt = select(Conversation).where(
            Conversation.user_id == user_uuid,
            Conversation.ended_at.is_(None)
        ).order_by(Conversation.started_at.desc()).limit(1)
        
        conv = (await session.execute(stmt)).scalar_one_or_none()
        if not conv:
            conv = Conversation(id=uuid.uuid4(), user_id=user_uuid)
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
        return conv.id

    async def _save_message(self, session: AsyncSession, conv_id: uuid.UUID, user_id: str, role: str, content: str) -> None:
        from app.infrastructure.database.models.message import Message, MessageRole
        # role string to enum
        enum_role = MessageRole.USER if role == "user" else MessageRole.ASSISTANT
        msg = Message(
            id=uuid.uuid4(),
            conversation_id=conv_id,
            user_id=uuid.UUID(user_id),
            role=enum_role,
            content=content
        )
        session.add(msg)
        await session.commit()

    async def _get_recent_history(self, session: AsyncSession, user_id: str, conv_id: uuid.UUID, limit: int = 15) -> list[dict[str, str]]:
        # This strictly scopes to user_id and active conversation
        user_uuid = uuid.UUID(user_id)
        from app.infrastructure.database.models.message import Message
        stmt = select(Message).where(
            Message.user_id == user_uuid,
            Message.conversation_id == conv_id
        ).order_by(Message.created_at.desc()).limit(limit)
        
        result = await session.execute(stmt)
        messages = result.scalars().all()
        # Ensure correct chronological order for the LLM
        return [{"role": m.role.value, "content": m.content} for m in reversed(messages)]

    async def get_history(self, session: AsyncSession, user_id: str, limit: int = 50) -> list[dict[str, str]]:
        """Public method to fetch conversation history for the Web UI on load."""
        await self._get_or_create_user(session, user_id)
        conv_id = await self._get_or_create_conversation(session, user_id)
        return await self._get_recent_history(session, user_id, conv_id, limit)

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
        
        # 1. Ensure root user exists, then Load context
        await self._get_or_create_user(session, user_id)
        stats = await self._get_user_stats(session, user_id)
        emotion = await self._get_emotion_state(session, user_id)
        conv_id = await self._get_or_create_conversation(session, user_id)
        
        history = await self._get_recent_history(session, user_id, conv_id)
        
        # Save user message immediately to STM
        await self._save_message(session, conv_id, user_id, "user", user_message)
        
        # 2. Update Emotion State based on User Message & Calculate emergent attachment bonus
        emotion_delta = self.emotion_engine.update(emotion, user_message)
        attachment_bonus = math.log(max(1, stats.interaction_count)) * 0.05
        
        # Save emotion state changes early
        session.add(emotion)
        await session.commit()
        await session.refresh(emotion)
        
        # Calculate memory importance (length + absolute emotion changes)
        emotion_magnitude = abs(emotion_delta.joy) + abs(emotion_delta.sadness) + abs(emotion_delta.irritation)
        importance_score = min(1.0, 0.4 + (len(user_message) / 500.0) + (emotion_magnitude * 2.0))
        
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
        
        # Retrieve strict global character lore chunks
        lore_chunks = await rag_retriever.retrieve_lore(
            query_vector=vector,
            top_k=4
        )
        log.info(f"Retrieved {len(lore_chunks)} lore chunks")
        if lore_chunks:
            log.info(f"First chunk: {lore_chunks[0][:100]}")
        
        # 4. Prompt Engineering via ContextBuilder
        prompt = self.context_builder.build(
            emotion=emotion,
            attachment_bonus=attachment_bonus,
            memories=memories,
            lore_chunks=lore_chunks,
            history=history,
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
        
        # 6. Post-processing
        await self._save_message(session, conv_id, user_id, "assistant", chisa_reply)
        
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
        session.add(stats)
        await session.commit()
        
        log.info("ChatEngine cycle complete", user_id=user_id, attachment_bonus=attachment_bonus)
        return chisa_reply
