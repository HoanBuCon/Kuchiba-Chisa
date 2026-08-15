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
    "Bạn là bộ Query Rewriter cho trợ lý game Wuthering Waves. Nhiệm vụ: Viết lại câu hỏi của user thành 1 câu truy vấn tìm kiếm độc lập, rõ ràng bằng tiếng Việt, kèm thuật ngữ/tên riêng tiếng Anh (nếu có).\n"
    "- Nếu câu hỏi có đại từ ('anh ấy', 'cô ấy', 'họ', 'vị tướng đó', 'vũ khí đó', 'ở đó', 'con đó', 'chiêu đó'), hãy dùng 'Ngữ cảnh câu trước' để thay thế.\n"
    "- Nếu câu hỏi đã rõ ràng hoặc đổi chủ đề mới, TUYỆT ĐỐI KHÔNG ghép ngữ cảnh câu trước vào.\n"
    "- Câu viết lại phải súc tích, trực diện, không dài dòng.\n"
    "- Bắt buộc trả về JSON: {\"rewritten_query\": \"...\"}"
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
        if not needs_llm_rewrite or not prev_rewritten_query:
            enriched = enrich_query_with_entities(base_query, self.entity_resolver)
            return enriched, "FAST_PATH"

        # 3. LLM Micro-Rewrite (DeepSeek V4 Flash) with 1-turn context chaining
        # Clamp previous context to avoid token bloat
        prev_clamped = " ".join(prev_rewritten_query.strip().split()[:60])
        user_input = f'Ngữ cảnh câu trước: "{prev_clamped}"\nCâu hỏi hiện tại: "{base_query}"'

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
                final_query = enrich_query_with_entities(rewritten, self.entity_resolver)
                log.info("LLM Rewrite succeeded", original=user_message, rewritten=final_query, latency_tokens=resp.input_tokens + resp.output_tokens)
                return final_query, "LLM_FLASH"

        except asyncio.TimeoutError:
            log.warning("LLM Rewrite timed out, falling back to Fast-Path", timeout=timeout_seconds)
        except Exception as exc:
            log.warning("LLM Rewrite failed, falling back to Fast-Path", error=str(exc))

        # Safe Fallback
        fallback_query = enrich_query_with_entities(base_query, self.entity_resolver)
        return fallback_query, "FAST_PATH_FALLBACK"
