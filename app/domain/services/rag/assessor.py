from typing import Tuple
from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

class ContextAssessor:
    """
    Evaluates whether the retrieved context contains enough factual information
    to fully and correctly answer the user's question without hallucinations.
    """
    async def assess_alignment(
        self,
        user_message: str,
        context_text: str,
        llm: BaseLLMAdapter
    ) -> Tuple[bool, str, str]:
        system_prompt = (
            "You are an Information Alignment Assessor.\n"
            "Evaluate whether the retrieved context contains enough specific, factual, and relevant information to fully "
            "and accurately answer the user's question without any hallucination.\n"
            "If the user is asking about real-time, dynamic information (like current events, prices, live statistics, etc.) "
            "and the exact current numbers/details are not present in the context, you MUST set 'is_aligned' to false.\n"
            "If the user asks a factual question about real-world history, politics, geography, science, public figures, "
            "or major world events, and the retrieved context is empty, says '(No context retrieved)', or only contains "
            "irrelevant game/fiction lore, you MUST set 'is_aligned' to false.\n"
            "If the user's message is simple casual conversation (greeting, small talk, emotional check-in) that doesn't "
            "require factual data lookup, set 'is_aligned' to true.\n"
            "If you set 'is_aligned' to false, you MUST generate a single, highly optimized search query under the key 'search_query' "
            "specifically designed for search engines (like DuckDuckGo) to retrieve the missing factual information. "
            "Keep the query short, composed of key keywords (typically 2-4 keywords), resolve pronouns (e.g. 'em' -> 'Chisa'), and remove all conversational fillers/question particles.\n"
            "You MUST output the result as a valid JSON object matching the requested schema."
        )

        user_prompt = (
            f"[User Question]: \"{user_message}\"\n\n"
            f"[Retrieved Context]:\n{context_text}"
        )

        schema = {
            "type": "object",
            "properties": {
                "is_aligned": {"type": "boolean"},
                "reason": {"type": "string"},
                "search_query": {"type": "string"}
            },
            "required": ["is_aligned", "reason"]
        }

        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=user_prompt,
            response_schema=schema,
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={}
        )

        try:
            from app.infrastructure.logging.llm_logger import llm_call_purpose
            llm_call_purpose.set("alignment_assessor")
            response = await llm.generate(prompt)
            parsed = response.parsed or {}
            is_aligned = parsed.get("is_aligned", True)
            reason = parsed.get("reason", "No reason provided")
            search_query = parsed.get("search_query", "").strip()
            log.info("Information alignment check complete", is_aligned=is_aligned, reason=reason, search_query=search_query)
            return is_aligned, reason, search_query
        except Exception as e:
            log.warning("Information alignment check failed, defaulting to True", error=str(e))
            return True, "Check failed, defaulting to aligned", ""
