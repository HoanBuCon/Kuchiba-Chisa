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
            "You are an Information Alignment Assessor.\n"
            "Evaluate whether the retrieved context contains enough specific, factual, and relevant information to fully "
            "and accurately answer the user's question without any hallucination, given the conversation history.\n\n"
            "Decide whether to keep the retrieved local context under the key 'use_lore':\n"
            "- Set 'use_lore' to true if the local context contains information about the character's background, world, relationships, or anything relevant to the user's question.\n"
            "- Set 'use_lore' to false ONLY IF the retrieved local context is completely irrelevant to the user's question, or if the user is asking a purely real-world factual question where game lore is useless.\n\n"
            "Determine alignment under the key 'is_aligned':\n"
            "- If the user is asking about real-time, dynamic real-world information (like current events, prices, live statistics, etc.) "
            "and the exact current numbers/details are not present in the context, set 'is_aligned' to false.\n"
            "- If the user asks a factual question about real-world history, politics, geography, science, or public figures, "
            "and the retrieved context is empty or only contains irrelevant fictional lore, set 'is_aligned' to false.\n"
            "- If the user's message is simple casual conversation that doesn't require factual data lookup, set 'is_aligned' to true.\n\n"
            "If you set 'is_aligned' to false, you MUST generate a single, highly optimized search query under the key 'search_query' "
            "specifically designed for search engines (like DuckDuckGo) to retrieve the missing factual information.\n"
            "- Keep it focused and keyword-based. Strip out conversational fillers, greetings, punctuation, and generic question words (e.g., 'cho hỏi', 'vậy em', 'nhé', 'ở đâu').\n"
            "- Resolve pronouns (e.g., 'em' -> 'Chisa').\n"
            "- CRITICAL FOR RELEVANCE: Retain all distinct semantic constraints from the user's question. Do NOT over-truncate. A high-quality query must combine: (1) the primary Subject/Entity, (2) the target Action/Attribute, and (3) key qualifiers (such as Location, Nationality, or specific Industry). Omitting any of these distinct constraints makes the search too broad and yields useless results.\n"
            "- Focus on semantic completeness: include all distinct constraints in a concise manner (typically 4 to 8 search terms). Do not search for a broad profile if the user asks about a very specific attribute.\n"
            "- Context Integration: You are encouraged to combine context from the [Recent Conversation History], the [Retrieved Context], and the [Latest User Question] to formulate the best search query. However, you MUST intelligently filter out irrelevant fictional concepts, lore, or names that do not directly pertain to the specific question being asked.\n\n"
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
            rag_decisions={}
        )

        try:
            from app.domain.context import llm_call_purpose
            llm_call_purpose.set("alignment_assessor")
            response = await llm.generate(prompt)
            parsed = response.parsed or {}
            is_aligned = parsed.get("is_aligned", True)
            reason = parsed.get("reason", "No reason provided")
            search_query = parsed.get("search_query", "").strip()
            use_lore = parsed.get("use_lore", True)
            log.info("Information alignment check complete", is_aligned=is_aligned, reason=reason, search_query=search_query, use_lore=use_lore)
            return is_aligned, reason, search_query, use_lore
        except Exception as e:
            log.warning("Information alignment check failed, defaulting to True", error=str(e))
            return True, "Check failed, defaulting to aligned", "", True
