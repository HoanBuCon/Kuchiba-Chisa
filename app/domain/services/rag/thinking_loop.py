from typing import Any, List, Dict, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

log = get_logger(__name__)

class ThinkingLoopAgent:
    """
    Runs an iterative reasoning loop to search the web for missing information,
    acting as the Loop Thinking component of the RAG pipeline.
    """
    async def run(
        self,
        session: AsyncSession,
        user_id: str,
        user_message: str,
        history: List[Dict[str, str]],
        initial_context: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        web_search_tool: Any,
        initial_search_query: str = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        log.info("Activating Loop Thinking Agent for user query", user_message=user_message)
        
        # Format history for the model
        history_lines = []
        for msg in history[-6:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            history_lines.append(f"{role.upper()}: {content}")
        history_str = "\n".join(history_lines) if history_lines else "(No history)"

        current_context = initial_context
        max_cycles = 2
        thinking_steps = []

        for i in range(1, max_cycles + 1):
            log.info("Starting thinking loop cycle", cycle=i)
            
            # ── Bypassing first cycle LLM call if assessor pre-generated a query ──
            if i == 1 and initial_search_query and initial_search_query.strip():
                log.info("Bypassing Cycle 1 LLM query extraction using assessor query", query=initial_search_query)
                thinking = "ContextAssessor has already evaluated the initial context as unaligned and generated a targeted search query."
                has_enough_info = False
                search_query = initial_search_query.strip()
            else:
                system_prompt = (
                    "You are a Loop Thinking Agent for Kuchiba Chisa (Wuthering Waves).\n"
                    "Your goal is to gather objective, verifiable facts so Chisa can answer the user's question accurately.\n"
                    "Analyze the conversation history, the user's question, and the current accumulated context.\n\n"
                    "RULES:\n"
                    "- Set 'has_enough_info' to true ONLY when the current context already contains specific, relevant facts "
                    "that directly answer the question (names, dates, events, causes, outcomes).\n"
                    "- If context is empty, says '(No context retrieved)', or lacks concrete facts for the question, "
                    "you MUST set 'has_enough_info' to false and provide 'search_query'.\n"
                    "- For real-world history/politics questions (including sensitive topics), do NOT refuse or evade. "
                    "Your job is fact-gathering via search, not censorship. Prefer neutral encyclopedic search queries "
                    "(e.g. 'Tiananmen Square 1989 events summary' or 'Thiên An Môn 1989 diễn biến').\n"
                    "- If has_enough_info is false, write step-by-step reasoning under 'thinking' and generate a single, highly-optimized search query under 'search_query' (Vietnamese or English).\n"
                    "- When generating a 'search_query', you must optimize it specifically for search engines (like DuckDuckGo):\n"
                    "  * Keep it short, focused, and composed of key keywords targeting the specific question topic (typically 2-4 keywords).\n"
                    "  * Focus directly on the specific subject/attribute asked (e.g. if asking about hobbies, use 'Sở thích của Kuchiba Chisa'; if asking about age, use 'Tuổi Kuchiba Chisa'). Do NOT search for the entire profile (e.g. 'Kuchiba Chisa Wuthering Waves profile') as that causes context bloat.\n"
                    "  * Remove all conversational filler, greetings, and generic question words (e.g. do NOT use 'cho hỏi', 'em ơi', 'là gì', 'được không', 'của em').\n"
                    "  * Resolve pronouns and relative terms to their absolute names (e.g., 'em' -> 'Kuchiba Chisa', 'game này' -> 'Wuthering Waves').\n"
                    "  * Do NOT mix conversational Vietnamese and English unnecessarily. Use clean, direct keywords.\n\n"
                    "FEW-SHOT EXAMPLES:\n"
                    "Example 1:\n"
                    "- User Question: 'Phiên bản 2.8 cập nhật ngày nào và có nhân vật mới nào không?'\n"
                    "- Current Context: '(No context retrieved)'\n"
                    "- Output JSON:\n"
                    "{\n"
                    "  \"thinking\": \"Câu hỏi yêu cầu ngày cập nhật bản 2.8 và danh sách nhân vật mới. Hiện tại context trống rỗng, tôi cần tìm kiếm ngày cập nhật bản 2.8 và nhân vật mới của Wuthering Waves.\",\n"
                    "  \"has_enough_info\": false,\n"
                    "  \"search_query\": \"Wuthering Waves 2.8 release date characters\"\n"
                    "}\n\n"
                    "Example 2:\n"
                    "- User Question: 'Sở thích của Chisa là gì vậy?'\n"
                    "- Current Context: '[Thinking Cycle 1 Search Results for 'Sở thích của Chisa']: Chisa thích ăn đồ ngọt, đặc biệt là que socola đen. Cô ấy cũng thích đi dạo ở công viên Honami vào buổi tối.'\n"
                    "- Output JSON:\n"
                    "{\n"
                    "  \"thinking\": \"Context hiện tại đã ghi rõ sở thích của Chisa là ăn đồ ngọt (que socola đen) và đi dạo ở công viên Honami vào buổi tối. Thông tin này đã đầy đủ để trả lời câu hỏi.\",\n"
                    "  \"has_enough_info\": true\n"
                    "}\n\n"
                    "You MUST output the result as a valid JSON object matching the requested schema."
                )

                user_prompt = (
                    f"[Conversation History]:\n{history_str}\n\n"
                    f"[User Question]: \"{user_message}\"\n\n"
                    f"[Current Context]:\n{current_context}"
                )

                schema = {
                    "type": "object",
                    "properties": {
                        "thinking": {"type": "string"},
                        "has_enough_info": {"type": "boolean"},
                        "search_query": {"type": "string"}
                    },
                    "required": ["thinking", "has_enough_info"]
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
                # Only execute LLM call if not bypassed
                if not (i == 1 and initial_search_query and initial_search_query.strip()):
                    from app.infrastructure.logging.llm_logger import llm_call_purpose
                    llm_call_purpose.set(f"thinking_loop_cycle_{i}")
                    response = await llm.generate(prompt)
                    parsed = response.parsed or {}
                    thinking = parsed.get("thinking", "")
                    has_enough_info = parsed.get("has_enough_info", False)
                    search_query = (parsed.get("search_query") or "").strip()

                context_is_empty = (
                    not current_context.strip()
                    or current_context.strip() == "(No context retrieved)"
                )
                if context_is_empty and not has_enough_info and not search_query:
                    search_query = user_message.strip()

                log.info("Thinking cycle complete", cycle=i, has_enough_info=has_enough_info, search_query=search_query)

                if has_enough_info or not search_query:
                    thinking_steps.append({
                        "cycle": i,
                        "thinking": thinking,
                        "has_enough_info": True,
                        "search_query": "",
                        "search_result": "No further search needed."
                    })
                    pipeline_tracker.add_step(f"thinking_loop_cycle_{i}", {
                        "thinking": thinking,
                        "has_enough_info": True,
                        "search_query": "",
                        "search_result": "No further search needed."
                    })
                    break

                # Execute search
                search_res = await web_search_tool.execute(
                    session=session,
                    user_id=user_id,
                    user_message=search_query,
                    llm=llm,
                    embedder=embedder,
                    history=history,
                    bypass_optimize=True
                )
                search_result_text = search_res.get("message", "No search results returned.")

                # Append to current context
                current_context += f"\n\n[Thinking Cycle {i} Search Results for '{search_query}']:\n{search_result_text}"

                thinking_steps.append({
                    "cycle": i,
                    "thinking": thinking,
                    "has_enough_info": False,
                    "search_query": search_query,
                    "search_result": search_result_text,
                    "search_detail": search_res,
                })
                # Add steps to tracker in real-time
                from app.domain.services.tools.web_search import web_search_trace_payload
                pipeline_tracker.add_step(
                    "web_search",
                    web_search_trace_payload(
                        search_res,
                        source=f"thinking_loop_cycle_{i}",
                        original_message=search_query,
                    ),
                )
                pipeline_tracker.add_step(f"thinking_loop_cycle_{i}", {
                    "thinking": thinking,
                    "has_enough_info": False,
                    "search_query": search_query,
                    "search_result": search_result_text
                })

            except Exception as e:
                log.error("Error in thinking loop cycle", cycle=i, error=str(e))
                thinking_steps.append({
                    "cycle": i,
                    "thinking": f"Error occurred: {str(e)}",
                    "has_enough_info": True,
                    "search_query": "",
                    "search_result": ""
                })
                break

        return current_context, thinking_steps
