import asyncio
import time
import uuid
import numpy as np
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client.http import models as qdrant_models

from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service, MemoryPayload, MemoryTier
from app.infrastructure.database.models.message import Message
from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.emotion_state import EmotionState
from app.infrastructure.database.models.user_stats import UserStats
from app.infrastructure.database.repositories.emotion_repository import SqlAlchemyEmotionRepository
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# Tầng 2a – Semantic Tool Router Anchors
# Mỗi tool có tập ví dụ câu nói đặc trưng để so sánh cosine similarity
# ──────────────────────────────────────────────────────────────────
TOOL_ANCHORS: Dict[str, List[str]] = {
    "web_search": [
        # Explicit search commands
        "tra mạng giúp anh tin tức này",
        "tìm kiếm internet xem thế nào",
        "lên mạng tìm hiểu xem sao",
        "search google giúp anh với",
        "tìm thông tin mới nhất trên mạng",
        "tra cứu giúp anh sự kiện này",
        # Implicit real-time / factual queries
        "khi nào game cập nhật phiên bản mới nhất",
        "phiên bản tiếp theo ra mắt bao giờ vậy",
        "banner mới nhất hiện tại là nhân vật nào",
        "lịch sự kiện tháng này thế nào",
        "tin tức mới nhất về wuthering waves",
        "phiên bản 3.5 ra bao giờ vậy",
        "lịch update game tháng tới ra sao",
        "sự kiện game gần đây có gì mới không",
        "thông tin leak về nhân vật sắp ra",
    ],
    "clear_chat_history": [
        "hãy xóa toàn bộ lịch sử trò chuyện của chúng ta",
        "dọn dẹp bộ nhớ của em đi",
        "xóa hết ký ức của chúng ta đi nhé",
        "reset lại cuộc trò chuyện từ đầu",
        "xóa tin nhắn cũ đi",
        "làm mới lại từ đầu đi",
        "xóa ký ức của em đi",
    ],
    "get_emotion_report": [
        "cho anh xem chỉ số cảm xúc của em",
        "bảng đo cảm xúc của em đâu rồi",
        "cảm xúc hiện tại của em như thế nào",
        "mức độ cảm xúc hiện tại ra sao",
        "trạng thái nội tâm của em thế nào",
        "em đang cảm thấy thế nào bây giờ",
        "hiển thị bảng đo cảm xúc của em đi",
    ],
}


class SemanticToolRouter:
    """
    Tầng 2a – Định tuyến tool bằng Cosine Similarity.

    Ưu điểm so với LLM:
    - Tốc độ ~1-5ms (so với 500-2000ms của LLM API)
    - Không tốn token
    - Dễ debug qua cosine score log
    - Tái dụng query_vector đã tính sẵn từ tầng 1
    """
    def __init__(self, embedder: IEmbeddingProvider, threshold: float = 0.50):
        self.embedder = embedder
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
            for tool_name, anchors in TOOL_ANCHORS.items():
                vectors = []
                for text in anchors:
                    try:
                        vec = await self.embedder.embed_text(text)
                        vectors.append(vec)
                    except Exception as e:
                        log.error("Failed to embed tool anchor", tool=tool_name, text=text, error=str(e))
                if vectors:
                    self.tool_embeddings[tool_name] = np.array(vectors)
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


class LLMToolRouter:
    """
    Tầng 2 – Hybrid Tool Router.

    Pipeline:
    ┌─────────────────────────────────────────────────────────┐
    │  Level 2a: SemanticToolRouter                           │
    │  → Chọn tool bằng cosine similarity (không tốn token)  │
    ├─────────────────────────────────────────────────────────┤
    │  Level 2b: LLM nhỏ (chỉ khi tool = web_search)         │
    │  → Extract & clean search_query từ câu nói tự nhiên    │
    └─────────────────────────────────────────────────────────┘
    """

    QUERY_EXTRACT_SCHEMA = {
        "type": "object",
        "properties": {
            "search_query": {"type": "string"}
        },
        "required": ["search_query"]
    }

    def __init__(self, llm: BaseLLMAdapter, embedder: IEmbeddingProvider):
        self.llm = llm
        self.embedder = embedder
        self.semantic_tool_router = SemanticToolRouter(embedder=embedder)

    async def _extract_search_query(self, user_message: str) -> str:
        """
        Tầng 2b – LLM nhỏ: chỉ extract/clean search query từ câu nói tự nhiên.
        Chỉ được gọi khi SemanticToolRouter đã xác định tool là 'web_search'.
        Prompt tối giản để giảm thiểu latency và token cost.
        """
        system_prompt = (
            "Extract the core search query from the user's message. "
            "Return only the clean search query, optimized for a web search engine. "
            "Remove conversational filler (e.g. 'tra giúp anh', 'em tra xem', 'khi nào thế'). "
            "Preserve: game names, character names, version numbers, technical terms."
        )
        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=user_message,
            response_schema=self.QUERY_EXTRACT_SCHEMA,
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={}
        )
        try:
            response = await self.llm.generate(prompt)
            query = (response.parsed or {}).get("search_query", "").strip()
            if query:
                log.info("LLM extracted search query", original=user_message, extracted=query)
                return query
        except Exception as e:
            log.warning("LLM query extraction failed, falling back to raw message", error=str(e))
        return user_message

    async def execute(
        self,
        user_message: str,
        session: AsyncSession,
        user_id: str,
        query_vector: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Thực thi tool routing theo pipeline 2 tầng.

        Args:
            user_message: Tin nhắn gốc của người dùng.
            session: Database session.
            user_id: ID người dùng.
            query_vector: Vector embedding của query (tái dụng từ tầng 1, tránh embed lại).
        """
        # ── Level 2a: Semantic Tool Selection ──────────────────────────────
        if query_vector is not None:
            tool_name, score = await self.semantic_tool_router.route(query_vector)
        else:
            # Fallback: embed lại nếu không có vector truyền vào
            log.warning("No pre-computed query_vector provided to LLMToolRouter, embedding on-the-fly")
            vec = await self.embedder.embed_text(user_message)
            tool_name, score = await self.semantic_tool_router.route(vec)

        log.info("Tool routing decided (semantic)", tool_name=tool_name, score=round(score, 4), user_id=user_id)

        # ── Execute ─────────────────────────────────────────────────────────
        if tool_name == "clear_chat_history":
            return await self._clear_chat_history(session, user_id)

        elif tool_name == "web_search":
            # Level 2b: LLM nhỏ chỉ để extract query — không classify tool nữa
            search_query = await self._extract_search_query(user_message)
            return await self._web_search(search_query)

        elif tool_name == "get_emotion_report":
            return await self._get_emotion_report(session, user_id)

        else:
            return {"status": "skipped", "message": "Không có hành động hệ thống nào cần thực hiện."}

    # ────────────────────────────────────────────────────────────────────────
    # Tool Implementations
    # ────────────────────────────────────────────────────────────────────────

    async def _clear_chat_history(self, session: AsyncSession, user_id: str) -> Dict[str, Any]:
        """Xóa sạch bộ nhớ SQLite và Qdrant của user"""
        from sqlalchemy import delete as sql_delete
        user_uuid = uuid.UUID(user_id)

        try:
            # 1. Delete Postgres STM messages and conversations
            await session.execute(sql_delete(Message).where(Message.user_id == user_uuid).execution_options(synchronize_session=False))
            await session.execute(sql_delete(Conversation).where(Conversation.user_id == user_uuid).execution_options(synchronize_session=False))

            # 2. Reset Emotion and Stats
            await session.execute(sql_delete(EmotionState).where(EmotionState.user_id == user_uuid).execution_options(synchronize_session=False))
            await session.execute(sql_delete(UserStats).where(UserStats.user_id == user_uuid).execution_options(synchronize_session=False))
            await session.commit()

            # 3. Clear Qdrant collections
            collections = ["emotional_memories", "conversation_summaries", "persona_embeddings", "user_facts", "memories"]
            for col in collections:
                try:
                    await qdrant_service._client.delete(
                        collection_name=col,
                        points_selector=qdrant_models.FilterSelector(
                            filter=qdrant_models.Filter(
                                must=[qdrant_models.FieldCondition(
                                    key="user_id",
                                    match=qdrant_models.MatchValue(value=user_id)
                                )]
                            )
                        )
                    )
                except Exception as qe:
                    log.warning("Could not clear Qdrant collection", collection=col, error=str(qe))

            log.info("User memory cleared via LLM Tool Router", user_id=user_id)
            return {
                "status": "success",
                "tool": "clear_chat_history",
                "message": "Tất cả ký ức đã được dọn sạch thành công. Chisa đã quên hết mọi chuyện cũ và sẵn sàng bắt đầu lại!"
            }
        except Exception as e:
            log.error("Failed to clear chat history in LLM Tool Router", error=str(e), user_id=user_id)
            return {"status": "error", "message": f"Lỗi khi xóa ký ức: {str(e)}"}

    async def _web_search(self, query: str) -> Dict[str, Any]:
        """Tìm kiếm thông tin trên internet qua DuckDuckGo HTML"""
        log.info("Running web search in LLM Tool Router", query=query)
        import urllib.parse
        import re
        import httpx

        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        def _parse_snippets(html: str) -> List[str]:
            """Trích xuất snippets từ HTML, thử nhiều pattern khác nhau."""
            patterns = [
                r'<a class="result__snippet"[^>]*>(.*?)</a>',
                r'<div class="result__snippet"[^>]*>(.*?)</div>',
                r'class="result__body"[^>]*>(.*?)</div>',
            ]
            for pattern in patterns:
                raw = re.findall(pattern, html, re.DOTALL)
                if raw:
                    cleaned = []
                    for s in raw:
                        c = re.sub(r'<[^>]+>', '', s)
                        c = (c.replace('&nbsp;', ' ').replace('&amp;', '&')
                               .replace('&lt;', '<').replace('&gt;', '>')
                               .replace('&quot;', '"').replace('&#x27;', "'")
                               .strip())
                        if c:
                            cleaned.append(c)
                    if cleaned:
                        return cleaned
            return []

        try:
            async with httpx.AsyncClient(headers=headers, timeout=12.0, follow_redirects=True) as client:
                response = await client.get(url)
                log.info("DuckDuckGo HTTP response", status_code=response.status_code, query=query)

                # Chấp nhận mọi 2xx response, không chỉ 200
                if not (200 <= response.status_code < 300):
                    log.warning("DuckDuckGo search failed", status_code=response.status_code)
                    return {"status": "error", "message": f"Không thể kết nối dịch vụ tìm kiếm (Mã lỗi: {response.status_code})."}

                snippets = _parse_snippets(response.text)
                results = snippets[:4]

                if not results:
                    return {"status": "success", "tool": "web_search", "message": "Không tìm thấy kết quả tìm kiếm nào phù hợp trên internet."}

                results_str = "\n".join([f"- {r}" for r in results])
                log.info("Web search completed successfully", count=len(results))
                return {
                    "status": "success",
                    "tool": "web_search",
                    "message": f"Dưới đây là kết quả tìm kiếm internet mới nhất cho từ khóa '{query}':\n{results_str}"
                }
        except Exception as e:
            log.error("Failed to execute web search in LLM Tool Router", error=str(e))
            return {"status": "error", "message": f"Gặp lỗi khi tìm kiếm thông tin: {str(e)}"}

    async def _get_emotion_report(self, session: AsyncSession, user_id: str) -> Dict[str, Any]:
        """Lấy báo cáo chi tiết chỉ số cảm xúc của Chisa"""
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
                "tool": "get_emotion_report",
                "message": f"Báo cáo cảm xúc hiện tại của Chisa: {report}."
            }
        except Exception as e:
            log.error("Failed to fetch emotion report in LLM Tool Router", error=str(e), user_id=user_id)
            return {"status": "error", "message": f"Lỗi khi trích xuất cảm xúc: {str(e)}"}
