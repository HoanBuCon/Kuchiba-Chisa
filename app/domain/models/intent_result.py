from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class ChatIntent(str, Enum):
    SMALL_TALK = "SMALL_TALK"                               # Lời chào, phản hồi ngắn, xã giao (Bypass RAG)
    KNOWLEDGE_OR_TASK = "KNOWLEDGE_OR_TASK"                 # Câu hỏi tri thức, thực thể, code, sự kiện, lore, lệnh bot
    LORE = "LORE"                                           # Hỏi về nhân vật, thế giới game, cốt truyện
    MEMORY = "MEMORY"                                       # Hỏi về thông tin cá nhân Senpai
    CONVERSATIONAL = "CONVERSATIONAL"                       # Trò chuyện tự do, tán gẫu sâu
    SYSTEM_ACTION = "SYSTEM_ACTION"                         # Lệnh hệ thống
    IMAGE_ANALYSIS = "IMAGE_ANALYSIS"                       # Phân tích, nhận diện và miêu tả hình ảnh
    GAMEPLAY_STATS_EVALUATION = "GAMEPLAY_STATS_EVALUATION" # Đánh giá build đồ, Echo, vũ khí, chỉ số game
    MEME_REACTION = "MEME_REACTION"                         # Phản hồi ảnh chế, meme, troll
    DOCUMENT_OCR = "DOCUMENT_OCR"                           # Đọc văn bản, hóa đơn, dịch thuật, giải mã chữ trong ảnh
    CODE_ANALYSIS = "CODE_ANALYSIS"                         # Phân tích ảnh chụp màn hình code, debug lỗi IDE/terminal
    ARTWORK_EVALUATION = "ARTWORK_EVALUATION"               # Nhận xét tranh vẽ, fanart, cosplay, tạo hình nhân vật
    OTHER = "OTHER"                                         # Không xác định được ý định


@dataclass
class IntentResult:
    """Kết quả phân loại Intent có cấu trúc."""

    intents: List[ChatIntent]
    confidence: float  # 0.0 -> 1.0
    routing_method: str  # "L1_SMALL_TALK" | "L2_KEYWORD" | "L3_SEMANTIC" | "L4_LLM_FALLBACK"
    query_vector: Optional[List[float]] = None  # Vector đã tính, tái sử dụng cho RAG
    semantic_scores: Optional[Dict[str, float]] = None  # {"LORE": 0.82, "MEMORY": 0.45, ...}
    routing_reason: str = ""

    def __iter__(self):
        """Hỗ trợ tương thích ngược với cú pháp unpacking: intents, conf = classify(...)"""
        yield self.intents
        yield self.confidence
