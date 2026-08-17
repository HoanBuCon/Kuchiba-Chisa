from typing import Tuple
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.shared.utils.logger import get_logger

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
        llm: BaseLLMAdapter,
        history: list = None,
        conversation_summary: str = None,
    ) -> Tuple[bool, str, str, bool]:
        import json
        # Prefer summary (compact) over raw history to save tokens.
        # Fallback to last 4 raw messages if no summary exists yet.
        if conversation_summary and conversation_summary.strip():
            context_history_label = "[Conversation Summary]"
            history_text = conversation_summary.strip()
        elif history:
            history_lines = []
            for msg in history[-4:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "assistant" and content.strip().startswith("{"):
                    try:
                        parsed = json.loads(content)
                        content = parsed.get("response", content)
                    except Exception:
                        pass
                history_lines.append(f"{role.upper()}: {content}")
            context_history_label = "[Recent Conversation History]"
            history_text = "\n".join(history_lines) if history_lines else "(No conversation history)"
        else:
            context_history_label = "[Recent Conversation History]"
            history_text = "(No conversation history)"

        system_prompt = (
            "You are an Information Alignment Assessor & Search Query Refiner for Kuchiba Chisa (Wuthering Waves).\n"
            "Evaluate whether the retrieved context (which may come from Qdrant Game Lore OR initial Web Search Round 1) contains enough specific, factual, and relevant information to fully "
            "and accurately answer the user's question without any hallucination, given the conversation history.\n\n"
            "TASKS:\n"
            "1. Decide whether to keep the retrieved context under the key 'use_lore':\n"
            "   - Set 'use_lore' to true if the context contains relevant facts about the characters, lore, or real-world subject of the question.\n"
            "   - Set 'use_lore' to false ONLY IF the retrieved context is completely irrelevant or noise.\n\n"
            "2. Determine factual alignment under the key 'is_aligned':\n"
            "   - Set 'is_aligned' to true ONLY if the current context has enough verified facts to answer ALL key aspects of the question.\n"
            "   - Set 'is_aligned' to false if information is incomplete, missing specific details, or if further internet search is needed.\n\n"
            "3. Multi-Hop Search Query Refinement ('search_query'):\n"
            "   - If 'is_aligned' is false, generate a sharp, optimized search query for the NEXT search cycle in Loop Thinking.\n"
            "   - CRITICAL: Read the facts, real names, aliases, or entities already discovered in [Retrieved Context] and synthesize them with the user question to create a deeper, multi-hop search query (DO NOT repeat the exact old search query).\n"
            "   - Keep query focused and keyword-based (4 to 8 search terms). Strip conversational fillers ('cho hỏi', 'vậy em', 'nhé').\n\n"
            "You MUST output the result as a valid JSON object matching the requested schema."
        )

        user_prompt = (
            f"{context_history_label}:\n{history_text}\n\n"
            f"[Latest User Question]: \"{user_message}\"\n\n"
            f"[Retrieved Context]:\n{context_text}"
        )

        schema = {
            "type": "object",
            "properties": {
                "is_aligned": {"type": "boolean"},
                "reason": {"type": "string"},
                "search_query": {"type": "string"},
                "use_lore": {"type": "boolean"}
            },
            "required": ["is_aligned", "reason", "use_lore"]
        }

        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=user_prompt,
            response_schema=schema,
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={"use_deep_thinking": False}
        )

        try:
            from app.domain.context import llm_call_purpose
            llm_call_purpose.set("alignment_assessor")
            response = await llm.generate(prompt)
            parsed = response.parsed or {}
            is_aligned = parsed.get("is_aligned", True)
            reason = parsed.get("reason", "No reason provided")
            search_query = (parsed.get("search_query") or "").strip()
            use_lore = parsed.get("use_lore", True)
            log.info("Information alignment check complete", is_aligned=is_aligned, reason=reason, search_query=search_query, use_lore=use_lore)
            return is_aligned, reason, search_query, use_lore
        except Exception as e:
            log.warning("Information alignment check failed, defaulting to True", error=str(e))
            return True, "Check failed, defaulting to aligned", "", True
