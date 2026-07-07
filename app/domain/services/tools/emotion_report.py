import uuid
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.llm.adapters.base import BaseLLMAdapter
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.services.tools.base import BaseAgentTool
from app.infrastructure.database.repositories.emotion_repository import SqlAlchemyEmotionRepository
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class EmotionReportAgentTool(BaseAgentTool):
    """
    Agent tool for retrieving Chisa's current emotional state stats.
    """
    @property
    def name(self) -> str:
        return "get_emotion_report"

    @property
    def description(self) -> str:
        return "Lấy chỉ số thống kê trạng thái cảm xúc hiện tại của Chisa."

    @property
    def anchors(self) -> List[str]:
        return [
            # --- Yêu cầu xem số liệu cảm xúc ---
            "cho anh xem chỉ số cảm xúc của em",
            "bảng đo cảm xúc của em đâu rồi",
            "hiển thị bảng đo cảm xúc của em đi",
            "mức độ cảm xúc hiện tại ra sao",
            "xuất báo cáo cảm xúc của em ra",
            "chỉ số tâm lý của em hiện tại",
            "bảng thống kê cảm xúc của chisa đâu",
            # --- Diễn đạt tự nhiên về tâm trạng ---
            "cảm xúc hiện tại của em như thế nào",
            "trạng thái nội tâm của em thế nào",
            "em đang cảm thấy thế nào bây giờ",
            "tâm trạng của em hiện tại thế nào",
            "nội tâm của em đang ra sao",
            "em đang có cảm giác gì vậy",
            "trái tim em đang mách bảo điều gì",
            "cảm xúc nào đang chiếm ưu thế trong em",
            "xúc cảm hiện tại của em là gì",
            "em có vui không báo cáo đi",
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
        try:
            user_uuid = uuid.UUID(user_id)
            emotion_repo = SqlAlchemyEmotionRepository(session)
            emotion = await emotion_repo.get_emotion_state(user_uuid)

            report = (
                f"Vui vẻ (Joy): {emotion.joy:.2f}, "
                f"Buồn bã (Sadness): {emotion.sadness:.2f}, "
                f"Tin tưởng (Trust): {emotion.trust:.2f}, "
                f"Bực dọc (Irritation): {emotion.irritation:.2f}, "
                f"Gắn kết (Attachment): {emotion.attachment:.2f}"
            )
            return {
                "status": "success",
                "message": f"Báo cáo cảm xúc hiện tại của Chisa: {report}."
            }
        except Exception as e:
            log.error("Failed to fetch emotion report in EmotionReportAgentTool", error=str(e), user_id=user_id)
            return {"status": "error", "message": f"Lỗi khi trích xuất cảm xúc: {str(e)}"}
