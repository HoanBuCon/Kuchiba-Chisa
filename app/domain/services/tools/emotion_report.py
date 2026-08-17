import uuid
from typing import Any, Dict, List
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.services.tools.base import BaseAgentTool
from app.domain.interfaces.repositories import IEmotionRepository
from app.shared.utils.logger import get_logger

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
            "em đo tâm trạng của em hiện tại xem nào",
            "chỉ số tình cảm của em với anh",
            "kiểm tra cảm xúc của chisa",
            "cho xem chỉ số cảm xúc",
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
            "em đang thấy thế nào rồi",
            "hiện tại tâm lý em ổn không",
        ]

    async def execute(
        self,
        user_id: str,
        user_message: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        **kwargs
    ) -> Dict[str, Any]:
        emotion_repo = kwargs.get("emotion_repo")
        if not emotion_repo:
            return {
                "status": "error",
                "message": "Thiếu emotion_repo để đọc cảm xúc."
            }

        try:
            from app.shared.utils.user_identity import normalize_user_id
            user_uuid = normalize_user_id(user_id)
            emotion = await emotion_repo.get_emotion_state(user_uuid)

            report = (
                f"Tin tưởng: {emotion.trust:.2f}, "
                f"Gắn bó: {emotion.attachment:.2f}, "
                f"Ngại ngùng: {getattr(emotion, 'shyness', 0.0):.2f}, "
                f"Hiếu kỳ: {getattr(emotion, 'curiosity', 0.20):.2f}, "
                f"Bình yên: {getattr(emotion, 'comfort', 0.50):.2f}, "
                f"Vui vẻ: {emotion.joy:.2f}, "
                f"Buồn bã: {emotion.sadness:.2f}, "
                f"Khó chịu: {emotion.irritation:.2f}"
            )
            return {
                "status": "success",
                "message": f"Báo cáo cảm xúc hiện tại của Chisa: {report}."
            }
        except Exception as e:
            log.error("Failed to fetch emotion report in EmotionReportAgentTool", error=str(e), user_id=user_id)
            return {"status": "error", "message": f"Lỗi khi trích xuất cảm xúc: {str(e)}"}
