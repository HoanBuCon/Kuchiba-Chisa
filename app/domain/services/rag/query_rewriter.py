import asyncio
import json
import re
from typing import Any, Dict, Optional, Tuple

from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.shared.utils.logger import get_logger
from app.shared.utils.query_cleaner import (
    clean_query_for_rag,
    enrich_query_with_entities,
    has_coreference_markers,
    strip_platform_mentions,
)

log = get_logger(__name__)

from dataclasses import dataclass

@dataclass
class RewriteResult:
    rewritten_query: str
    method: str
    needs_vector_search: bool
    needs_web_search: bool
    needs_image_retrieval: bool = False

    def __iter__(self):
        yield self.rewritten_query
        yield self.method
        yield self.needs_vector_search
        yield self.needs_web_search


REWRITE_SYSTEM_PROMPT = (
    "Bạn là bộ Query Rewriter & Tri-State Knowledge Router thông minh cho trợ lý AI Kuchiba Chisa (game Wuthering Waves).\n\n"
    "NHIỆM VỤ 1: ĐỊNH TUYẾN NGUỒN TRI THỨC (Đánh các cờ boolean độc lập):\n"
    "1. LORE GAME NỘI BỘ (needs_vector_search = true, needs_web_search = false):\n"
    "   - Câu hỏi cần tra cứu dữ liệu game Wuthering Waves (nhân vật, kỹ năng Forte, vũ khí, Echo, quái vật, cốt truyện) hoặc ký ức của Senpai.\n"
    "2. THÔNG TIN NGOÀI ĐỜI (needs_vector_search = false, needs_web_search = true):\n"
    "   - Câu hỏi cần tra cứu dữ kiện thực tế bên ngoài (người thật, tin tức mới, sự kiện đời thực, thời gian thực, kiến thức chuyên ngành, bài báo khoa học, tài liệu kỹ thuật).\n"
    "3. CẢ HAI (needs_vector_search = true, needs_web_search = true):\n"
    "   - Câu hỏi kết hợp giữa nội dung game và thông tin cập nhật bên ngoài (như tin tức/rò rỉ cập nhật mới về game, thời gian ra mắt banner/sự kiện sắp tới, so sánh đối chiếu).\n"
    "4. TRUY HỒI ẢNH KÝ ỨC (needs_image_retrieval = true):\n"
    "   - Người dùng yêu cầu tìm lại, gửi lại hoặc xem lại bức ảnh đã từng lưu trữ trong quá khứ (ví dụ: 'gửi lại ảnh đi chơi', 'cho xem lại cái hình con mèo hôm nọ', 'quăng lại đây tấm ảnh bữa trước', 'ảnh cũ đâu rồi').\n"
    "5. KHÔNG CẦN TRA CỨU (tất cả cờ = false):\n"
    "   - Trò chuyện tâm sự, tán gẫu cảm xúc thường nhật, chào hỏi, hoặc thao tác trực tiếp trên nội dung văn bản/hình ảnh do người dùng gửi kèm.\n\n"
    "NHIỆM VỤ 2: VIẾT LẠI TRUY VẤN TÌM KIẾM ('rewritten_query'):\n"
    "- Viết lại câu hỏi thành chuỗi từ khóa tìm kiếm độc lập, rõ ràng, gãy gọn.\n"
    "- Loại bỏ toàn bộ từ đệm đàm thoại ('cho anh hỏi', 'tìm giúp em', 'là gì thế', 'nhé').\n"
    "- Sử dụng danh xưng/thuật ngữ tự nhiên và hiệu quả nhất cho đối tượng được hỏi.\n"
    "- Chuẩn hóa đại từ: đổi 'em/chisa' -> 'Kuchiba Chisa'; 'anh/tôi' -> 'Senpai'; đại từ ngữ cảnh ('anh ấy', 'cô ấy', 'nhân vật đó') -> thực thể câu trước.\n\n"
    "Bắt buộc trả về JSON:\n"
    "{\n"
    "  \"rewritten_query\": \"chuỗi từ khóa tìm kiếm\",\n"
    "  \"needs_vector_search\": true/false,\n"
    "  \"needs_web_search\": true/false,\n"
    "  \"needs_image_retrieval\": true/false\n"
    "}"
)

REWRITE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "rewritten_query": {
            "type": "string",
            "description": "Câu truy vấn tìm kiếm độc lập, súc tích, chuẩn danh xưng."
        },
        "needs_vector_search": {
            "type": "boolean",
            "description": "True nếu cần tra cứu database game Wuthering Waves hoặc ký ức của Senpai."
        },
        "needs_web_search": {
            "type": "boolean",
            "description": "True nếu cần tìm kiếm internet thông tin thực tế ngoài đời, tin tức mới hoặc tài liệu chuyên ngành."
        },
        "needs_image_retrieval": {
            "type": "boolean",
            "description": "True nếu Senpai yêu cầu tìm lại hoặc gửi lại ảnh cũ trong kho ký ức hình ảnh."
        }
    },
    "required": ["rewritten_query", "needs_vector_search", "needs_web_search"],
    "additionalProperties": False,
}


from app.domain.tuning.rag import RAGTuning


def is_obvious_code_or_technical_query(text: str) -> bool:
    """Detects if input is obvious source code snippet or programming exercise."""
    if not text:
        return False
    # Check for dense code syntax markers
    code_keywords = [
        r"\bclass\s+\w+",
        r"\bstruct\s+\w+",
        r"\bpublic\s*:",
        r"\bprivate\s*:",
        r"\b#include\b",
        r"\bint\s+main\b",
        r"\bdef\s+\w+\s*\(",
        r"\bfunction\s+\w+\s*\(",
        r"\bvoid\s+\w+\s*\(",
        r"\bunordered_map<",
        r"\bvector<",
        r"\bconsole\.log\(",
        r"```[\s\S]*?```",
    ]
    for pat in code_keywords:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


class QueryRewriter:
    """
    Tiered Query Rewriter with Tri-State Knowledge Routing (Vector Search vs Web Search).
    """
    def __init__(self, llm: BaseLLMAdapter, entity_resolver: Optional[Any] = None):
        self.llm = llm
        self.entity_resolver = entity_resolver

    async def rewrite(
        self,
        user_message: str,
        cleaned_query: str,
        prev_rewritten_query: Optional[str] = None,
        needs_llm_rewrite: bool = False,
        intent_hint: Optional[str] = None,
        timeout_seconds: float = RAGTuning.REWRITE_TIMEOUT_SECONDS,
    ) -> RewriteResult:
        """
        Main rewrite method.
        Returns:
            RewriteResult: rewritten query and retrieval-routing decisions.
        """
        # 1. Base cleaned query
        base_query = cleaned_query or clean_query_for_rag(user_message)
        if not base_query:
            return RewriteResult(user_message, "FAST_PATH", False, False, False)

        is_code = is_obvious_code_or_technical_query(user_message)

        # 2. If LLM rewrite is NOT requested, use Fast-Path Entity Enrichment
        if not needs_llm_rewrite:
            enriched = enrich_query_with_entities(base_query, self.entity_resolver, intent_hint=intent_hint)
            # Default vector search to True for lore/memory unless it's obvious code
            needs_vec = not is_code
            return RewriteResult(enriched, "FAST_PATH", needs_vec, False, False)

        # 3. LLM Micro-Rewrite (DeepSeek V4 Flash) with context chaining or persona disambiguation
        # Strip platform tags (<@1512944169310748682>) so LLM receives clean user semantic context
        raw_user_query = strip_platform_mentions(user_message.strip()) or user_message.strip()
        if prev_rewritten_query:
            prev_clamped = " ".join(prev_rewritten_query.strip().split()[:60])
            user_input = f'Ngữ cảnh câu trước / thảo luận gần đây: "{prev_clamped}"\nCâu hỏi hiện tại: "{raw_user_query}"'
        else:
            prev_clamped = "None"
            user_input = f'Câu hỏi hiện tại: "{raw_user_query}"'

        prompt = StructuredPrompt(
            system=REWRITE_SYSTEM_PROMPT,
            history=[],
            user_message=user_input,
            response_schema=REWRITE_SCHEMA,
            max_tokens=100,
            temperature=0.1,
        )

        try:
            from app.domain.context import llm_call_purpose
            llm_call_purpose.set("micro_llm_query_rewrite")
            log.info("Executing Micro LLM Rewrite", current=raw_user_query, prev_context=prev_clamped)
            resp = await asyncio.wait_for(
                self.llm.generate(prompt),
                timeout=timeout_seconds,
            )

            rewritten = resp.parsed.get("rewritten_query", "").strip()
            needs_vector_search = bool(resp.parsed.get("needs_vector_search", not is_code))
            needs_web_search = bool(resp.parsed.get("needs_web_search", False))
            needs_image_retrieval = bool(resp.parsed.get("needs_image_retrieval", False))

            # Code heuristic override: if code is present and no lore entity, force False on both
            if is_code and not (self.entity_resolver and self.entity_resolver.extract_entities(rewritten)):
                needs_vector_search = False
                needs_web_search = False

            if rewritten and len(rewritten) >= 3:
                # Enrich with any explicit wiki entity aliases
                final_query = enrich_query_with_entities(rewritten, self.entity_resolver, intent_hint=intent_hint)
                log.info(
                    "LLM Rewrite succeeded",
                    original=user_message[:60],
                    rewritten=final_query,
                    needs_vector_search=needs_vector_search,
                    needs_web_search=needs_web_search,
                    needs_image_retrieval=needs_image_retrieval,
                    latency_tokens=resp.input_tokens + resp.output_tokens
                )
                return RewriteResult(
                    rewritten_query=final_query,
                    method="LLM_FLASH",
                    needs_vector_search=needs_vector_search,
                    needs_web_search=needs_web_search,
                    needs_image_retrieval=needs_image_retrieval,
                )

        except asyncio.TimeoutError:
            log.warning("LLM Rewrite timed out, falling back to Fast-Path", timeout=timeout_seconds)
        except Exception as exc:
            log.warning("LLM Rewrite failed, falling back to Fast-Path", error=str(exc))

        # Safe Fallback
        fallback_query = enrich_query_with_entities(base_query, self.entity_resolver, intent_hint=intent_hint)
        return RewriteResult(
            rewritten_query=fallback_query,
            method="FAST_PATH_FALLBACK",
            needs_vector_search=not is_code,
            needs_web_search=False,
            needs_image_retrieval=False,
        )
