from typing import Any

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
        history: list[dict[str, Any]] | None = None,
        conversation_summary: str | None = None,
    ) -> tuple[bool, str, str, bool, str, str]:
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
            "Evaluate whether the retrieved context contains enough facts to answer the user's specific question accurately without hallucinations.\n\n"
            "CRITICAL SCOPING PRINCIPLES (PREVENT OVER-ASSESSMENT & UNNECESSARY SEARCHES):\n"
            "1. SCOPE-BOUND EVALUATION: Evaluate ONLY what the user explicitly asks for.\n"
            "   - If the user asks a general question (e.g. 'Who is Chisa?'), general background/identity/personality is 100% SUFFICIENT -> mark is_aligned = true.\n"
            "   - DO NOT demand encyclopedic completeness. NEVER mark false for missing combat skills, multipliers, or voice lines unless the user EXPLICITLY asked for them.\n"
            "   - SPECIAL RULE FOR ALGORITHMS/CODE: If the context contains the core mathematical principle, recurrence, or algorithmic steps, mark is_aligned = true.\n\n"
            "2. 80/20 SUFFICIENCY GATE ('is_aligned'):\n"
            "   - true: The context enables answering the user's core question (>80% answerable without guessing).\n"
            "   - false: The core question CANNOT be answered at all (context is completely irrelevant, empty, or misses the exact specific fact requested).\n\n"
            "3. INTENT CONSERVATION FOR SEARCH TARGET ('search_target'):\n"
            "   - Only determine 'search_target' when is_aligned = false.\n"
            "   - 'vector': For in-game lore, story, characters, and canon game mechanics (Default for all game lore queries unless internet/real-world is explicitly mentioned).\n"
            "   - 'web': For real-world news, release dates, patch updates, internet leaks, or non-game topics.\n"
            "   - 'both': ONLY when the user explicitly asks to compare in-game lore with online discussions/leaks/buffs.\n\n"
            "4. MANDATORY FACT DISTILLATION ('extracted_facts'):\n"
            "   - Summarize verified facts from the context into concise bullet points.\n"
            "   - Preserve 100% of exact numbers, percentages, dates, proper names, entities, and formulas. Strip website junk/boilerplate.\n\n"
            "5. SEARCH QUERY REFINEMENT ('search_query'):\n"
            "   - If is_aligned = false, craft a focused keyword query (4 to 8 search terms) targeting ONLY the missing aspect of the user's question.\n\n"
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
                "search_target": {
                    "type": "string",
                    "enum": ["vector", "web", "both"],
                    "description": "Target engine for next search cycle ('vector', 'web', or 'both')."
                },
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
            search_target = str(parsed.get("search_target") or "web").strip().lower()
            if search_target not in ("vector", "web", "both"):
                search_target = "web"
            use_lore = parsed.get("use_lore", True)
            
            raw_facts = parsed.get("extracted_facts") or ""
            if isinstance(raw_facts, list):
                bullet_lines = []
                for f in raw_facts:
                    f_str = str(f).strip()
                    if f_str:
                        if not f_str.startswith(("- ", "* ", "• ")):
                            bullet_lines.append(f"- {f_str}")
                        else:
                            bullet_lines.append(f_str)
                extracted_facts = "\n".join(bullet_lines)
            elif isinstance(raw_facts, str):
                lines = [line.strip() for line in raw_facts.strip().split("\n") if line.strip()]
                bullet_lines = []
                for line in lines:
                    if not line.startswith(("- ", "* ", "• ")):
                        bullet_lines.append(f"- {line}")
                    else:
                        bullet_lines.append(line)
                extracted_facts = "\n".join(bullet_lines) if bullet_lines else ""
            else:
                extracted_facts = str(raw_facts).strip() if raw_facts else ""

            log.info("Information alignment check complete", is_aligned=is_aligned, reason=reason, search_query=search_query, search_target=search_target, use_lore=use_lore, facts_len=len(extracted_facts))
            return is_aligned, reason, search_query, use_lore, extracted_facts, search_target
        except Exception as e:
            log.warning("Information alignment check failed, defaulting to True", error=str(e))
            return True, "Check failed, defaulting to aligned", "", True, "", "web"
