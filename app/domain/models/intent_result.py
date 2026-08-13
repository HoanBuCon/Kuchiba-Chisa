from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class ChatIntent(str, Enum):
    SMALL_TALK = "SMALL_TALK"         # Lời chào, phản hồi ngắn, xã giao
    LORE = "LORE"                     # Hỏi về nhân vật, thế giới game, cốt truyện
    MEMORY = "MEMORY"                 # Hỏi về thông tin cá nhân Senpai
    CONVERSATIONAL = "CONVERSATIONAL" # Trò chuyện tự do, tán gẫu dài
    SYSTEM_ACTION = "SYSTEM_ACTION"   # Lệnh hệ thống (tóm tắt, báo cáo, web search)
    OTHER = "OTHER"                   # Không xác định được ý định


@dataclass
class IntentResult:
    """Kết quả phân loại Intent có cấu trúc."""

    intents: List[ChatIntent]
    confidence: float  # 0.0 -> 1.0
    routing_method: str  # "L1_SMALL_TALK" | "L2_KEYWORD" | "L3_SEMANTIC" | "L4_LLM_FALLBACK"
    query_vector: Optional[List[float]] = None  # Vector đã tính, tái sử dụng cho RAG
    semantic_scores: Optional[Dict[str, float]] = None  # {"LORE": 0.82, "MEMORY": 0.45, ...}
    routing_reason: str = ""
