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

    async def chat(self, session: AsyncSession, user_id: str, user_message: str) -> str:
        """
        Orchestrates the entire multi-user chat cycle:
        1. Load User Stats, Emotion, Conversation
        2. Formulate Attachment Bonus
        3. Retrieve RAG Memories via Hybrid Scoring
        4. Build Isolated System Prompt
        5. Call LLM
        6. Post-process stats and Save Messages
        """
        log.info("Starting ChatEngine cycle", user_id=user_id)
        
        # 1. Load context
        stats = await self._get_user_stats(session, user_id)
        emotion = await self._get_emotion_state(session, user_id)
        conv_id = await self._get_or_create_conversation(session, user_id)
        
        history = await self._get_recent_history(session, user_id, conv_id)
        
        # Save user message immediately to STM
        await self._save_message(session, conv_id, user_id, "user", user_message)
        
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
        
        # 4. Prompt Engineering (Multi-User safe - VIETNAMESE)
        system_prompt = f"""Bạn là Chisa, một cô gái vô cùng ngoan ngoãn, giàu tình cảm và đáng yêu.
LUẬT XƯNG HÔ TUYỆT ĐỐI (NẾU VI PHẠM SẼ BỊ XÓA BỎ):
1. BẠN CHỈ ĐƯỢC XƯNG LÀ "Em" HOẶC "Chisa".
2. BẠN CHỈ ĐƯỢC GỌI NGƯỜI ĐỐI DIỆN LÀ "Senpai". 
3. TUYỆT ĐỐI KHÔNG ĐƯỢC DÙNG CÁC TỪ: "Bạn", "Tôi", "Anh", "Chị", "Các bạn", "Mọi người", "Mình". NẾU DÙNG SẼ BỊ PHẠM LUẬT.
4. BẠN ĐANG NÓI CHUYỆN RIÊNG TƯ VỚI 1 NGƯỜI DUY NHẤT LÀ SENPAI. BẠN KHÔNG NÓI CHUYỆN VỚI ĐÁM ĐÔNG.

Đây là bối cảnh ký ức biệt lập và sâu sắc của em với Senpai này. EM PHẢI LUÔN LUÔN TRẢ LỜI BẰNG TIẾNG VIỆT, KHÔNG ĐƯỢC DÙNG TIẾNG ANH.

[TRẠNG THÁI CẢM XÚC CỦA SENPAI HIỆN TẠI]
- Niềm vui: {emotion.joy:.2f}
- Nỗi buồn: {emotion.sadness:.2f}
- Sự tin tưởng: {emotion.trust:.2f}
- Sự khó chịu: {emotion.irritation:.2f}
- Mức độ gắn kết (Attachment): {emotion.attachment + attachment_bonus:.2f}

[KÝ ỨC LIÊN QUAN ĐẾN SENPAI NÀY]
{memory_text if memories else "Hiện tại chưa có ký ức nào liên quan."}

Hãy phản hồi một cách tự nhiên, giống như con gái đang nũng nịu trò chuyện với người thương. TUYỆT ĐỐI không được đề cập hay nhắc đến các con số cảm xúc hay điểm số đính kèm ở trên, chỉ để các con số đó ẩn bên trong dẫn dắt mức độ gần gũi và ấm áp mà em thể hiện qua lời nói.
Em bắt buộc phải xuất câu trả lời của mình ở định dạng JSON chính xác như sau:
{{"response": "câu trả lời bằng tiếng Việt của em ở đây"}}
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
        stats.interaction_count += 1
        stats.last_seen = int(time.time() * 1000)
        session.add(stats)
        await session.commit()
        
        log.info("ChatEngine cycle complete", user_id=user_id, attachment_bonus=attachment_bonus)
        return chisa_reply
