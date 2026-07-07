import uuid
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.services.tools.base import BaseAgentTool
from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.message import Message
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class ConversationSummarizerAgentTool(BaseAgentTool):
    """
    Agent tool for summarizing the active conversation.
    """
    @property
    def name(self) -> str:
        return "summarize_conversation_memory"

    @property
    def description(self) -> str:
        return "Tóm tắt diễn biến cuộc trò chuyện hiện tại của Chisa và Senpai."

    @property
    def anchors(self) -> List[str]:
        return [
            # --- Ra lệnh tóm tắt trực tiếp ---
            "tóm tắt lại nội dung cuộc trò chuyện nãy giờ giúp anh",
            "hãy tổng hợp lại câu chuyện của chúng ta",
            "tóm tắt cuộc hội thoại này đi em",
            "nãy giờ chúng ta nói về những gì rồi nhỉ",
            "em có thể tóm tắt ngắn gọn cuộc trò chuyện này không",
            "hãy ghi lại những điểm chính trong cuộc trò chuyện",
            "tổng kết lại nãy giờ nói gì đi",
            "tóm tắt ký ức của chúng ta lại đi",
            # --- Diễn đạt khác ---
            "em tóm gọn lại những gì chúng ta đã nói đi",
            "anh muốn biết chúng ta đã bàn về gì",
            "em nhắc lại những chủ đề chính trong buổi chat này",
            "liệt kê lại những điểm chính trong cuộc trò chuyện",
            "cho anh xem lại những gì đã xảy ra trong hội thoại này",
            "ghi nhớ và tóm tắt cuộc trò chuyện nãy giờ",
            "tóm tắt session chat này cho anh",
            "cho anh xem tổng quan cuộc hội thoại hôm nay",
        ]

    async def execute(
        self,
        session: AsyncSession,
        user_id: str,
        user_message: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        **kwargs
    ) -> Dict[str, Any]:
        from sqlalchemy import select
        
        user_uuid = uuid.UUID(user_id)
        
        # 1. Fetch active conversation
        stmt = (
            select(Conversation)
            .where(
                Conversation.user_id == user_uuid,
                Conversation.ended_at.is_(None)
            )
            .order_by(Conversation.started_at.desc())
            .limit(1)
        )
        conv = (await session.execute(stmt)).scalar_one_or_none()
        if not conv:
            return {
                "status": "skipped",
                "message": "Không tìm thấy phiên hội thoại hoạt động để tóm tắt."
            }

        # 2. Fetch all messages in this conversation (ordered chronologically)
        msg_stmt = (
            select(Message)
            .where(
                Message.conversation_id == conv.id,
                Message.is_success == True
            )
            .order_by(Message.created_at.asc())
        )
        msgs = (await session.execute(msg_stmt)).scalars().all()
        if not msgs:
            return {
                "status": "skipped",
                "message": "Không có tin nhắn nào trong hội thoại để tóm tắt."
            }

        # 3. Build chat transcript for LLM
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
            response_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"}
                },
                "required": ["summary"]
            },
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={}
        )

        try:
            response = await llm.generate(prompt)
            summary_text = (response.parsed or {}).get("summary", "").strip()
            if not summary_text:
                summary_text = response.raw_content or ""
            
            if summary_text:
                conv.summary = summary_text
                await session.commit()
                log.info("Conversation summary generated and updated successfully", conversation_id=conv.id)
                return {
                    "status": "success",
                    "message": f"Dưới đây là tóm tắt cuộc trò chuyện của chúng ta nãy giờ:\n{summary_text}"
                }
            else:
                return {
                    "status": "error",
                    "message": "Không thể sinh được nội dung tóm tắt từ cuộc trò chuyện."
                }
        except Exception as e:
            log.error("Failed to generate conversation summary in ConversationSummarizerAgentTool", error=str(e))
            return {
                "status": "error",
                "message": f"Gặp lỗi khi tóm tắt cuộc trò chuyện: {str(e)}"
            }
