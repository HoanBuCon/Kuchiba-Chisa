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
)

log = get_logger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "Bạn là bộ Query Rewriter thông minh cho trợ lý AI game Wuthering Waves (nhân vật Kuchiba Chisa).\n"
    "Nhiệm vụ: Viết lại câu hỏi của user thành 1 câu truy vấn tìm kiếm độc lập, rõ ràng bằng tiếng Việt, kèm thuật ngữ/tên riêng tiếng Anh chuẩn của game.\n\n"
    "QUY TẮC BẮT BUỘC:\n"
    "1. ĐẠI TỪ CHỈ AI ('em', 'chisa', 'chía', 'bé chisa', 'cô bé'):\n"
    "   - Khi user hỏi về năng lực, kỹ năng, vũ khí, tiểu sử, thông tin của AI -> Đổi 'em' thành 'Kuchiba Chisa'.\n"
    "   - Ngoại lệ: Nếu 'em/bé' đi liền tên nhân vật khác (vd: 'em Chixia', 'bé Danjin') -> Giữ nguyên tên nhân vật đó.\n"
    "2. ĐẠI TỪ CHỈ USER ('anh', 'tôi', 'mình', 'senpai', 'tớ', 'chị'):\n"
    "   - Khi user hỏi về ký ức/thông tin cá nhân của họ -> Đổi thành 'Senpai / người dùng'.\n"
    "   - Ngoại lệ: Nếu 'anh' đi liền tên nhân vật (vd: 'anh Jiyan') -> Giữ tên 'Jiyan'.\n"
    "3. ĐẠI TỪ CHỈ NGỮ CẢNH CÂU TRƯỚC ('anh ấy', 'cô ấy', 'họ', 'vị tướng đó', 'vũ khí đó', 'ở đó', 'con rồng đó', 'chiêu đó', 'nơi đó'):\n"
    "   - Dùng thực thể trong 'Ngữ cảnh câu trước' để thay thế chính xác.\n"
    "4. ĐỔI CHỦ ĐỀ HOẶC CÂU ĐÃ ĐỦ NGHĨA:\n"
    "   - Nếu user chuyển sang chủ đề mới hoặc tâm sự cá nhân ('mà thôi', 'không nói chuyện game nữa') -> TUYỆT ĐỐI KHÔNG ghép thực thể câu trước vào.\n"
    "5. PHỦ ĐỊNH / ĐÍNH CHÍNH ('không phải A mà là B'):\n"
    "   - Loại trừ hoàn toàn A, chỉ giữ lại B.\n\n"
    "VÍ DỤ MẪU (FEW-SHOT):\n"
    "- Ngữ cảnh: \"\" | Câu hỏi: \"vậy em có năng lực gì\" -> {\"rewritten_query\": \"năng lực kỹ năng Forte của Kuchiba Chisa\"}\n"
    "- Ngữ cảnh: \"Kể về vị tướng Jiyan\" | Câu hỏi: \"Vũ khí của anh ấy là gì?\" -> {\"rewritten_query\": \"vũ khí của tướng quân Jiyan\"}\n"
    "- Ngữ cảnh: \"Kể về Jiyan\" | Câu hỏi: \"Không phải Jiyan, anh đang hỏi Geshu Lin\" -> {\"rewritten_query\": \"thông tin về tướng quân Geshu Lin\"}\n"
    "- Ngữ cảnh: \"Jiyan dùng vũ khí gì\" | Câu hỏi: \"Mà thôi hôm nay anh mệt quá\" -> {\"rewritten_query\": \"tâm sự chia sẻ khi Senpai cảm thấy mệt mỏi\"}\n"
    "- Ngữ cảnh: \"\" | Câu hỏi: \"em Chixia dùng súng gì\" -> {\"rewritten_query\": \"vũ khí của Chixia trong Wuthering Waves\"}\n\n"
    "Bắt buộc trả về JSON: {\"rewritten_query\": \"...\"}"
)

REWRITE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "rewritten_query": {
            "type": "string",
            "description": "Câu hỏi đã được viết lại tường minh, độc lập."
        }
    },
    "required": ["rewritten_query"],
    "additionalProperties": False,
}


from app.domain.tuning.rag import RAGTuning

class QueryRewriter:
    """
    Tiered Query Rewriter Engine:
    - Tier 1: Fast-Path (Regex normalization + Entity Alias Enrichment) -> 0 token, <0.2ms
    - Tier 2: Micro LLM Rewriter (DeepSeek V4 Flash) -> ~40 tokens, ~100-250ms (up to 2.5s during peak hours)
    - Fallback: Safe timeout guard (2.5s) -> degrades gracefully to Fast-Path
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
    ) -> Tuple[str, str]:
        """
        Main rewrite method.
        Returns:
            (final_rewritten_query, method)
            method is one of: "BYPASS", "FAST_PATH", "LLM_FLASH", "FAST_PATH_FALLBACK"
        """
        # 1. Base cleaned query
        base_query = cleaned_query or clean_query_for_rag(user_message)
        if not base_query:
            return user_message, "FAST_PATH"

        # 2. If LLM rewrite is NOT requested, use Fast-Path Entity Enrichment
        if not needs_llm_rewrite:
            enriched = enrich_query_with_entities(base_query, self.entity_resolver, intent_hint=intent_hint)
            return enriched, "FAST_PATH"

        # 3. LLM Micro-Rewrite (DeepSeek V4 Flash) with context chaining or persona disambiguation
        if prev_rewritten_query:
            prev_clamped = " ".join(prev_rewritten_query.strip().split()[:60])
            user_input = f'Ngữ cảnh câu trước: "{prev_clamped}"\nCâu hỏi hiện tại: "{base_query}"'
        else:
            prev_clamped = "None"
            user_input = f'Câu hỏi hiện tại: "{base_query}"'

        prompt = StructuredPrompt(
            system=REWRITE_SYSTEM_PROMPT,
            history=[],
            user_message=user_input,
            response_schema=REWRITE_SCHEMA,
            max_tokens=80,
            temperature=0.1,
        )

        try:
            log.info("Executing Micro LLM Rewrite", current=base_query, prev_context=prev_clamped)
            resp = await asyncio.wait_for(
                self.llm.generate(prompt),
                timeout=timeout_seconds,
            )

            rewritten = resp.parsed.get("rewritten_query", "").strip()
            if rewritten and len(rewritten) >= 3:
                # Enrich with any explicit wiki entity aliases
                final_query = enrich_query_with_entities(rewritten, self.entity_resolver, intent_hint=intent_hint)
                log.info("LLM Rewrite succeeded", original=user_message, rewritten=final_query, latency_tokens=resp.input_tokens + resp.output_tokens)
                return final_query, "LLM_FLASH"

        except asyncio.TimeoutError:
            log.warning("LLM Rewrite timed out, falling back to Fast-Path", timeout=timeout_seconds)
        except Exception as exc:
            log.warning("LLM Rewrite failed, falling back to Fast-Path", error=str(exc))

        # Safe Fallback
        fallback_query = enrich_query_with_entities(base_query, self.entity_resolver, intent_hint=intent_hint)
        return fallback_query, "FAST_PATH_FALLBACK"
