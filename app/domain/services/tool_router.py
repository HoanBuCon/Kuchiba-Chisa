import asyncio
import re
import numpy as np
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.logging.logger import get_logger

# Import modular tools
from app.domain.services.tools import (
    BaseAgentTool,
    WebSearchAgentTool,
    ConversationSummarizerAgentTool,
    EmotionReportAgentTool
)

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# Tầng 2a – Semantic Tool Router
# ──────────────────────────────────────────────────────────────────

class SemanticToolRouter:
    """
    Tầng 2a – Định tuyến tool bằng Cosine Similarity.
    """
    def __init__(self, embedder: IEmbeddingProvider, tools: List[BaseAgentTool], threshold: float = 0.50):
        self.embedder = embedder
        self.tools = tools
        self.threshold = threshold
        self.tool_embeddings: Dict[str, np.ndarray] = {}
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Sinh và cache vector embedding của anchors vào RAM khi khởi động."""
        async with self._lock:
            if self._initialized:
                return
            log.info("Initializing SemanticToolRouter anchors...")
            for tool in self.tools:
                vectors = []
                for text in tool.anchors:
                    try:
                        vec = await self.embedder.embed_text(text)
                        vectors.append(vec)
                    except Exception as e:
                        log.error("Failed to embed tool anchor", tool=tool.name, text=text, error=str(e))
                if vectors:
                    self.tool_embeddings[tool.name] = np.array(vectors)
            self._initialized = True
            log.info("SemanticToolRouter anchors initialized ✓", tools=list(self.tool_embeddings.keys()))

    def _cosine_similarity(self, q_vec: np.ndarray, anchor_matrix: np.ndarray) -> np.ndarray:
        """Tính cosine similarity giữa query vector và ma trận anchors."""
        dot = np.dot(anchor_matrix, q_vec)
        norm_q = np.linalg.norm(q_vec)
        norm_a = np.linalg.norm(anchor_matrix, axis=1)
        return dot / (norm_q * norm_a + 1e-9)

    async def route(self, query_vector: List[float]) -> Tuple[str, float]:
        """
        Trả về (tool_name, confidence_score).
        tool_name = 'none' nếu không có tool nào vượt ngưỡng threshold.
        """
        if not self._initialized:
            await self.initialize()

        q_vec = np.array(query_vector)
        best_tool = "none"
        best_score = 0.0

        for tool_name, anchor_matrix in self.tool_embeddings.items():
            sims = self._cosine_similarity(q_vec, anchor_matrix)
            max_sim = float(np.max(sims))
            log.debug("SemanticToolRouter score", tool=tool_name, score=round(max_sim, 4))
            if max_sim > best_score:
                best_score = max_sim
                best_tool = tool_name

        if best_score < self.threshold:
            log.info(
                "SemanticToolRouter: no tool above threshold, skipping",
                best_tool=best_tool,
                best_score=round(best_score, 4),
                threshold=self.threshold,
            )
            return "none", best_score

        log.info("SemanticToolRouter: tool selected", tool=best_tool, score=round(best_score, 4))
        return best_tool, best_score


class KeywordToolRouter:
    """
    Fast-path regex guard cho định tuyến tool.
    Nếu khớp cứng theo mẫu tường minh thì bỏ qua embedding routing.
    """

    PATTERNS: Dict[str, List[str]] = {
        "web_search": [
            r"(tra mạng|lên mạng|search google|tra cứu trên internet)",
            r"(em tìm kiếm|em tra|em tìm).{0,10}(trên internet|trên mạng|giúp anh)",
            r"(lên web|kiểm tra xem|tìm hiểu xem|tra giúp|tìm giúp).{0,20}",
        ],
        # Map về tên tool thực tế trong codebase để giữ backward compatibility.
        "summarize_conversation_memory": [
            r"tóm tắt.{0,15}(cuộc trò chuyện|hội thoại|nãy giờ|buổi chat|session)",
            r"(tổng hợp|tổng kết).{0,15}(cuộc trò chuyện|những gì|điểm chính|nãy giờ)",
            r"(ghi lại|nhắc lại|liệt kê lại).{0,15}(điểm chính|cuộc trò chuyện|hội thoại)",
        ],
        "get_emotion_report": [
            r"(cho anh xem|xuất|hiển thị|xem).{0,15}(cảm xúc|chỉ số|bảng đo|báo cáo)",
            r"(báo cáo cảm xúc|tâm trạng theo số liệu|chỉ số cảm xúc)",
        ],
    }

    @classmethod
    def match(cls, msg_lower: str) -> Optional[str]:
        for tool_name, patterns in cls.PATTERNS.items():
            if any(re.search(pattern, msg_lower) for pattern in patterns):
                return tool_name
        return None


# ──────────────────────────────────────────────────────────────────
# Tầng 2 – Hybrid Tool Router Coordinator
# ──────────────────────────────────────────────────────────────────

class LLMToolRouter:
    """
    Tầng 2 – Hybrid Tool Router.
    Điều phối định tuyến và thực thi các Agent Tools đã đăng ký.
    """
    # Exposing schemas for backward compatibility
    QUERY_EXTRACT_SCHEMA = {
        "type": "object",
        "properties": {
            "search_query": {"type": "string"}
        },
        "required": ["search_query"]
    }

    SUMMARIZE_CONVERSATION_SCHEMA = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"}
        },
        "required": ["summary"]
    }

    def __init__(self, llm: BaseLLMAdapter, embedder: IEmbeddingProvider):
        self.llm = llm
        self.embedder = embedder
        
        # Đăng ký danh sách các công cụ hệ thống (Agent Tools)
        self.tools: List[BaseAgentTool] = [
            WebSearchAgentTool(),
            ConversationSummarizerAgentTool(),
            EmotionReportAgentTool()
        ]
        self.tool_map = {tool.name: tool for tool in self.tools}
        self.semantic_tool_router = SemanticToolRouter(embedder=embedder, tools=self.tools)

    async def execute(
        self,
        user_message: str,
        user_id: str,
        query_vector: Optional[List[float]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Thực thi định tuyến và xử lý tác vụ tương ứng.
        """
        # ── Level 2a.0: Keyword fast-path (bypass embedding)
        keyword_match = KeywordToolRouter.match(user_message.strip().lower())
        if keyword_match:
            tool_name, score = keyword_match, 1.0
            log.info("Tool routing via keyword fast-path", tool=tool_name)
        else:
            # ── Level 2a: Định tuyến tool bằng Cosine Similarity
            if query_vector is not None:
                tool_name, score = await self.semantic_tool_router.route(query_vector)
            else:
                log.warning("No pre-computed query_vector provided to LLMToolRouter, embedding on-the-fly")
                vec = await self.embedder.embed_text(user_message)
                tool_name, score = await self.semantic_tool_router.route(vec)

        log.info("Tool routing decided", tool_name=tool_name, score=round(score, 4), user_id=user_id)

        # ── Thực thi Tool logic được tìm thấy
        tool = self.tool_map.get(tool_name)
        if tool:
            try:
                res = await tool.execute(
                    user_id=user_id,
                    user_message=user_message,
                    llm=self.llm,
                    embedder=self.embedder,
                    **kwargs,
                )
                res["tool"] = tool_name
                res["score"] = score
                return res
            except Exception as e:
                log.error("Failed to execute agent tool", tool=tool_name, error=str(e))
                return {
                    "status": "error",
                    "message": f"Gặp lỗi khi thực thi công cụ {tool_name}: {str(e)}",
                    "tool": tool_name,
                    "score": score
                }
        else:
            return {
                "status": "skipped",
                "message": "Không có hành động hệ thống nào cần thực hiện.",
                "tool": "none",
                "score": score
            }
