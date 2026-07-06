import asyncio
import numpy as np
from typing import List, Dict, Optional
from app.domain.services.production_pipeline.intent_classifier import ChatIntent
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

# Anchors definition for semantic routing
ROUTER_ANCHORS = {
    ChatIntent.CHARACTER_LORE: [
        "vũ khí của em là gì", "vòng ở cổ em để làm gì", "chisa thích ăn món gì",
        "sở thích của em là gì", "em bao nhiêu tuổi thế", "em học trường nào",
        "kéo của em để làm gì", "món tủ của chisa", "chisa thích ăn vặt gì"
    ],
    ChatIntent.WORLD_LORE: [
        "sonoro sphere là gì", "tacet discord xuất hiện từ đâu",
        "resonator là gì giải thích giúp anh", "thành phố Jinzhou ở đâu",
        "năng lượng tacet field hoạt động thế nào", "mutant resonator là gì",
        "lahai-roi ở đâu", "tacet field là gì"
    ],
    ChatIntent.STORY_LORE: [
        "cốt truyện chapter 3", "vòng lặp của honami là gì", "lễ hội startorch",
        "làm sao em sống sót qua vòng lặp", "nhật ký của sumika nói gì",
        "sự kiện startorch school festival", "câu chuyện của sumika"
    ],
    ChatIntent.MEMORY: [
        "anh tên là gì em nhớ không", "ngày mai anh có bài phỏng vấn ở đâu",
        "biệt danh của anh là gì", "hôm qua anh đã hứa gì với em",
        "ngày trước anh kể cho em nghe về sở thích của anh chưa",
        "chúng ta gặp nhau thế nào", "sở thích của anh là gì", "tên của anh là gì"
    ],
    ChatIntent.SYSTEM_ACTION: [
        # Explicit system commands
        "hãy xóa toàn bộ lịch sử trò chuyện", "dọn dẹp bộ nhớ giúp anh nhé",
        "hiển thị bảng đo cảm xúc của em đi", "xóa hết ký ức của chúng ta đi",
        "reset lại cuộc trò chuyện", "xóa tin nhắn cũ đi",
        # Explicit web search commands
        "tra mạng giúp anh tin tức này", "tìm kiếm internet xem thế nào",
        "lên mạng tìm hiểu xem sao", "search google giúp anh với",
        "tìm thông tin mới nhất trên mạng", "tra cứu giúp anh sự kiện này",
        # Implicit real-time / factual queries (no explicit search command needed)
        "khi nào game cập nhật phiên bản mới", "phiên bản tiếp theo ra mắt bao giờ",
        "banner mới nhất hiện tại là nhân vật nào", "lịch sự kiện tháng này thế nào",
        "có bản cập nhật mới chưa vậy", "ngày ra mắt phiên bản mới là khi nào",
        "tin tức mới nhất về wuthering waves", "sự kiện game gần đây có gì mới",
        "phiên bản 3.5 ra bao giờ vậy", "lịch update game tháng tới"
    ]
}


class SemanticRouter:
    """
    Tầng 1 - Định tuyến ngữ nghĩa dựa trên Cosine Similarity sử dụng NumPy.
    Tái sử dụng vector embedding của câu hỏi người dùng để tối ưu tài nguyên.
    """
    def __init__(self, embedder: IEmbeddingProvider, threshold: float = 0.65):
        self.embedder = embedder
        self.threshold = threshold
        self.route_embeddings: Dict[ChatIntent, np.ndarray] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Sinh và cache các vector embedding của các Anchors vào bộ nhớ RAM"""
        async with self._lock:
            if self._initialized:
                return

            log.info("Initializing Semantic Router anchors...")
            for intent, anchors in ROUTER_ANCHORS.items():
                vectors = []
                for text in anchors:
                    try:
                        vec = await self.embedder.embed_text(text)
                        vectors.append(vec)
                    except Exception as e:
                        log.error("Failed to embed anchor text", text=text, error=str(e))
                if vectors:
                    # Chuyển thành ma trận NumPy (N x D)
                    self.route_embeddings[intent] = np.array(vectors)
            
            self._initialized = True
            log.info("Semantic Router anchors initialized successfully ✓")

    def _cosine_similarity(self, q_vec: np.ndarray, anchor_matrix: np.ndarray) -> np.ndarray:
        """Tính cosine similarity giữa vector truy vấn và ma trận anchors"""
        dot_product = np.dot(anchor_matrix, q_vec)
        norm_q = np.linalg.norm(q_vec)
        norm_anchors = np.linalg.norm(anchor_matrix, axis=1)
        # Tránh chia cho 0
        return dot_product / (norm_q * norm_anchors + 1e-9)

    async def classify(self, user_message: str, query_vector: Optional[List[float]] = None) -> List[ChatIntent]:
        """Phân loại tin nhắn dựa trên khoảng cách vector ngữ nghĩa"""
        if not self._initialized:
            await self.initialize()

        if query_vector is None:
            # Fallback nếu vector chưa được sinh ở ngoài
            log.debug("No pre-computed query vector provided to SemanticRouter, generating one now")
            query_vector = await self.embedder.embed_text(user_message)

        q_vec = np.array(query_vector)
        matched_intents = []

        for intent, anchor_matrix in self.route_embeddings.items():
            similarities = self._cosine_similarity(q_vec, anchor_matrix)
            max_sim = float(np.max(similarities))
            
            log.debug("Semantic router score check", intent=intent.value, max_similarity=max_sim)
            if max_sim >= self.threshold:
                matched_intents.append(intent)

        return matched_intents
