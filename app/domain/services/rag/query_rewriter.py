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

REWRITE_SYSTEM_PROMPT = (
    "Bạn là bộ Query Rewriter & Tri-State Knowledge Router thông minh cho trợ lý AI Kuchiba Chisa (game Wuthering Waves).\n"
    "Nhiệm vụ:\n"
    "1. Viết lại câu hỏi của user thành câu truy vấn tìm kiếm độc lập, rõ ràng bằng tiếng Việt, kèm thuật ngữ/tên riêng chuẩn.\n"
    "2. Đánh 2 cờ định tuyến kiến thức độc lập:\n"
    "   a. 'needs_vector_search' (Tra cứu Database Game Wuthering Waves / Ký ức):\n"
    "      - true: Câu hỏi về nhân vật, kỹ năng Forte, vũ khí, Echo, quái vật, cốt truyện, lore game Wuthering Waves, hoặc ký ức của Senpai.\n"
    "      - false: Câu hỏi ngoài game, lập trình, hoặc không liên quan đến database game.\n"
    "   b. 'needs_web_search' (Tìm kiếm Internet / DuckDuckGo bên ngoài):\n"
    "      - true: Câu hỏi về thông tin thực tế ngoài đời, người thật (tác giả, streamer, hoanbucon, nhà phát triển...), tin tức mới, sự kiện ngoài game, tra cứu internet mà database game không có.\n"
    "      - false: Câu hỏi về lore game nội bộ, lập trình (C++, Python...), hoặc tâm sự trò chuyện thường ngày.\n\n"
    "QUY TẮC ĐẶC BIỆT:\n"
    "- LẬP TRÌNH / CODE / THUẬT TOÁN: Nếu user gửi code C++, Python, LeetCode (như LFUCache, QuickSort...) -> BẮT BUỘC đặt needs_vector_search = false VÀ needs_web_search = false.\n"
    "- TÁN GẪU / TÂM SỰ: 'chào em', 'hôm nay anh mệt quá' -> BẮT BUỘC đặt needs_vector_search = false VÀ needs_web_search = false.\n"
    "- THỰC THỂ NGOÀI GAME: 'hoanbucon là ai', 'thời tiết hôm nay', 'tin tức mới' -> BẮT BUỘC đặt needs_vector_search = false VÀ needs_web_search = true.\n"
    "- LORE GAME WUTHERING WAVES: 'vũ khí của Jiyan', 'kỹ năng của Chisa' -> BẮT BUỘC đặt needs_vector_search = true VÀ needs_web_search = false.\n\n"
    "QUY TẮC BẮT BUỘC VỀ ĐẠI TỪ:\n"
    "1. ĐẠI TỪ CHỈ AI ('em', 'chisa', 'chía', 'bé chisa', 'cô bé'): Khi user hỏi về năng lực, kỹ năng, vũ khí của AI -> Đổi 'em' thành 'Kuchiba Chisa'.\n"
    "2. ĐẠI TỪ CHỈ USER ('anh', 'tôi', 'mình', 'senpai', 'tớ'): Khi hỏi ký ức của user -> Đổi thành 'Senpai / người dùng'.\n"
    "3. ĐẠI TỪ CHỈ NGỮ CẢNH CÂU TRƯỚC ('anh ấy', 'cô ấy', 'họ', 'vị tướng đó', 'vũ khí đó'): Dùng thực thể trong 'Ngữ cảnh câu trước' để thay thế chính xác.\n\n"
    "VÍ DỤ MẪU (FEW-SHOT):\n"
    "- Ngữ cảnh: \"\" | Câu hỏi: \"vậy em có năng lực gì\" -> {\"rewritten_query\": \"năng lực kỹ năng Forte của Kuchiba Chisa\", \"needs_vector_search\": true, \"needs_web_search\": false}\n"
    "- Ngữ cảnh: \"\" | Câu hỏi: \"biết hoanbucon là ai không em\" -> {\"rewritten_query\": \"hoanbucon là ai\", \"needs_vector_search\": false, \"needs_web_search\": true}\n"
    "- Ngữ cảnh: \"Kể về vị tướng Jiyan\" | Câu hỏi: \"Vũ khí của anh ấy là gì?\" -> {\"rewritten_query\": \"vũ khí của tướng quân Jiyan\", \"needs_vector_search\": true, \"needs_web_search\": false}\n"
    "- Ngữ cảnh: \"\" | Câu hỏi: \"ý anh là bài này class LFUCache{...}\" -> {\"rewritten_query\": \"giải thích và tối ưu mã nguồn cấu trúc dữ liệu LFUCache bằng C++\", \"needs_vector_search\": false, \"needs_web_search\": false}\n"
    "- Ngữ cảnh: \"\" | Câu hỏi: \"viết giúp anh hàm quicksort bằng python\" -> {\"rewritten_query\": \"thuật toán sắp xếp QuickSort bằng ngôn ngữ Python\", \"needs_vector_search\": false, \"needs_web_search\": false}\n"
    "- Ngữ cảnh: \"Jiyan dùng vũ khí gì\" | Câu hỏi: \"Mà thôi hôm nay anh mệt quá\" -> {\"rewritten_query\": \"tâm sự chia sẻ khi Senpai cảm thấy mệt mỏi\", \"needs_vector_search\": false, \"needs_web_search\": false}\n"
    "- Ngữ cảnh: \"\" | Câu hỏi: \"khi nào banner Shorekeeper ra mắt\" -> {\"rewritten_query\": \"thời gian ra mắt banner Shorekeeper Wuthering Waves\", \"needs_vector_search\": true, \"needs_web_search\": true}\n\n"
    "Bắt buộc trả về JSON: {\"rewritten_query\": \"...\", \"needs_vector_search\": true/false, \"needs_web_search\": true/false}"
)

REWRITE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "rewritten_query": {
            "type": "string",
            "description": "Câu hỏi đã được viết lại tường minh, độc lập."
        },
        "needs_vector_search": {
            "type": "boolean",
            "description": "True nếu câu hỏi liên quan đến kiến thức game Wuthering Waves (nhân vật, lore, kỹ năng, vũ khí...) hoặc ký ức của Senpai."
        },
        "needs_web_search": {
            "type": "boolean",
            "description": "True nếu câu hỏi là về thông tin thực tế ngoài đời, người thật (hoanbucon, tác giả, streamer...), sự kiện internet, tin tức bên ngoài."
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
    ) -> Tuple[str, str, bool, bool]:
        """
        Main rewrite method.
        Returns:
            (final_rewritten_query, method, needs_vector_search, needs_web_search)
            method is one of: "BYPASS", "FAST_PATH", "LLM_FLASH", "FAST_PATH_FALLBACK"
            needs_vector_search: bool flag determining if Qdrant vector retrieval should execute.
            needs_web_search: bool flag determining if external Web Search should execute.
        """
        # 1. Base cleaned query
        base_query = cleaned_query or clean_query_for_rag(user_message)
        if not base_query:
            return user_message, "FAST_PATH", False, False

        is_code = is_obvious_code_or_technical_query(user_message)

        # 2. If LLM rewrite is NOT requested, use Fast-Path Entity Enrichment
        if not needs_llm_rewrite:
            enriched = enrich_query_with_entities(base_query, self.entity_resolver, intent_hint=intent_hint)
            # Default vector search to True for lore/memory unless it's obvious code
            needs_vec = not is_code
            return enriched, "FAST_PATH", needs_vec, False

        # 3. LLM Micro-Rewrite (DeepSeek V4 Flash) with context chaining or persona disambiguation
        # Strip platform tags (<@1512944169310748682>) so LLM receives clean user semantic context
        raw_user_query = strip_platform_mentions(user_message.strip()) or user_message.strip()
        if prev_rewritten_query:
            prev_clamped = " ".join(prev_rewritten_query.strip().split()[:60])
            user_input = f'Ngữ cảnh câu trước: "{prev_clamped}"\nCâu hỏi hiện tại: "{raw_user_query}"'
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
                    latency_tokens=resp.input_tokens + resp.output_tokens
                )
                return final_query, "LLM_FLASH", needs_vector_search, needs_web_search

        except asyncio.TimeoutError:
            log.warning("LLM Rewrite timed out, falling back to Fast-Path", timeout=timeout_seconds)
        except Exception as exc:
            log.warning("LLM Rewrite failed, falling back to Fast-Path", error=str(exc))

        # Safe Fallback
        fallback_query = enrich_query_with_entities(base_query, self.entity_resolver, intent_hint=intent_hint)
        return fallback_query, "FAST_PATH_FALLBACK", not is_code, False
