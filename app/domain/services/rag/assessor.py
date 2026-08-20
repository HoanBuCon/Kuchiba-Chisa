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
            "You are an Information Alignment Assessor & Factual Distiller for Kuchiba Chisa (Wuthering Waves).\n"
            "Evaluate whether the retrieved context (from Qdrant Game Lore OR Web Search) contains enough specific, factual, and verified information "
            "to answer the user's question accurately without any hallucination, given the conversation history.\n\n"
            "TASKS:\n"
            "1. Determine factual alignment ('is_aligned'):\n"
            "   - true: The context already contains enough verified facts/principles/steps to answer ALL core aspects of the question (>80% answerable).\n"
            "     * SPECIAL RULE FOR ALGORITHMS/CODE: If the context contains the core mathematical principle, recurrence, or algorithmic steps, mark is_aligned = true (the LLM can implement the code without further searching).\n"
            "   - false: Information is missing critical details, ambiguous, or needs deeper web search.\n\n"
            "2. Decide whether to keep the context ('use_lore'):\n"
            "   - Set to true if the context contains relevant facts about the game lore or real-world topic.\n"
            "   - Set to false ONLY if the context is completely irrelevant noise or error page.\n\n"
            "3. MANDATORY FACT DISTILLATION & SUMMARY ('extracted_facts'):\n"
            "   - Whenever the retrieved context contains relevant information (from Web Search or Vector Lore), YOU MUST summarize all essential facts into concise, high-density bullet points.\n"
            "   - PRESERVE 100% OF IMPORTANT INFO: Keep all exact numbers, percentages, dates, proper names, entities, mathematical formulas, time complexities, and algorithmic steps.\n"
            "   - STRIP OUT ALL JUNK: Remove promotional text, website navigation menus, duplicates, filler phrases, and HTML clutter.\n"
            "   - This distilled summary is injected directly into the Main LLM system prompt as the ground truth reference.\n"
            "   - If no relevant facts found, return empty string.\n\n"
            "4. Multi-Hop Search Query Refinement ('search_query'):\n"
            "   - If 'is_aligned' is false, craft a sharp, focused keyword search query (4 to 8 terms) for the NEXT search cycle.\n"
            "   - Synthesize entities/terms discovered in the context to dig deeper. Use standard English terms for technical/academic topics.\n\n"
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
                "extracted_facts": {
                    "type": ["string", "array"],
                    "description": "Concise bullet-point factual summary preserving exact numbers, dates, steps and formulas."
                },
                "search_query": {"type": "string"},
                "use_lore": {"type": "boolean"}
            },
            "required": ["is_aligned", "use_lore"]
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
            
            reason = parsed.get("reason")
            if not reason or not str(reason).strip():
                reason = "Ngữ cảnh đầy đủ thông tin để trả lời" if is_aligned else "Cần tìm kiếm bổ sung thêm dữ liệu"
            else:
                reason = str(reason).strip()

            search_query = (parsed.get("search_query") or "").strip() if isinstance(parsed.get("search_query"), str) else ""
            use_lore = parsed.get("use_lore", True)
            
            raw_facts = parsed.get("extracted_facts") or ""
            if isinstance(raw_facts, list):
                extracted_facts = "\n".join(f"- {str(f).strip()}" for f in raw_facts if str(f).strip())
            elif isinstance(raw_facts, str):
                extracted_facts = raw_facts.strip()
            else:
                extracted_facts = str(raw_facts).strip() if raw_facts else ""

            log.info("Information alignment check complete", is_aligned=is_aligned, reason=reason, search_query=search_query, use_lore=use_lore, facts_len=len(extracted_facts))
            return is_aligned, reason, search_query, use_lore, extracted_facts
        except Exception as e:
            log.warning("Information alignment check failed, defaulting to True", error=str(e))
            return True, "Check failed, defaulting to aligned", "", True, ""
