from typing import Any, List, Dict, Tuple
from app.domain.interfaces.session import IDbSession
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.shared.utils.logger import get_logger
from app.domain.interfaces.tracker import IPipelineTracker

log = get_logger(__name__)

class ThinkingLoopAgent:
    """
    Runs an iterative reasoning loop to search the web for missing information,
    acting as the Loop Thinking component of the RAG pipeline.
    """
    def __init__(self, pipeline_tracker: IPipelineTracker):
        self.pipeline_tracker = pipeline_tracker

    async def run(
        self,
        session: IDbSession,
        user_id: str,
        user_message: str,
        history: List[Dict[str, str]],
        initial_context: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        web_search_tool: Any,
        initial_search_query: str = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        import asyncio
        from app.config.settings import settings

        try:
            return await asyncio.wait_for(
                self._run_inner(
                    session=session,
                    user_id=user_id,
                    user_message=user_message,
                    history=history,
                    initial_context=initial_context,
                    llm=llm,
                    embedder=embedder,
                    web_search_tool=web_search_tool,
                    initial_search_query=initial_search_query,
                ),
                timeout=float(settings.THINKING_LOOP_TIMEOUT)
            )
        except asyncio.TimeoutError:
            log.warning("Thinking loop global timeout reached, returning accumulated context", user_message=user_message)
            return initial_context, []

    async def _run_inner(
        self,
        session: IDbSession,
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
                is_reasoning_cycle = False
                use_deep_thinking = False  # Always False for fast search query extraction

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
                    "- MULTI-HOP SEARCH REFINEMENT (CYCLE 2+):\n"
                    "  * When evaluating in Cycle 2+, carefully inspect the knowledge and entities discovered from Cycle 1.\n"
                    "  * If key details are still missing, synthesize new proper names, titles, or technical terms found in Cycle 1 to craft a sharper, targeted 'search_query' for Cycle 2.\n"
                    "  * DO NOT repeat the exact same search query as Cycle 1.\n\n"
                    "- OPTIMIZATION GUIDELINES FOR 'search_query':\n"
                    "  * Keep it focused and keyword-based (4 to 8 search terms). Combine: (1) Primary Entity, (2) Target Action/Attribute, and (3) Key Qualifiers.\n"
                    "  * Strip out conversational fillers ('cho hỏi', 'em ơi', 'là gì', 'được không', 'của em', 'vậy em', 'nhé') and resolve relative pronouns ('em' -> 'Kuchiba Chisa', 'game này' -> 'Wuthering Waves').\n\n"
                    "FEW-SHOT EXAMPLES:\n"
                    "Example 1 (Cycle 1 Initial Search):\n"
                    "- User Question: 'Phiên bản 2.8 cập nhật ngày nào và có nhân vật mới nào không?'\n"
                    "- Current Context: '(No context retrieved)'\n"
                    "- Output JSON:\n"
                    "{\n"
                    "  \"thinking\": \"Câu hỏi yêu cầu ngày cập nhật bản 2.8 và danh sách nhân vật mới. Hiện tại context trống rỗng, tôi cần tìm kiếm ngày cập nhật bản 2.8 và nhân vật mới của Wuthering Waves.\",\n"
                    "  \"has_enough_info\": false,\n"
                    "  \"search_query\": \"Wuthering Waves 2.8 release date characters\"\n"
                    "}\n\n"
                    "Example 2 (Sufficient Context Found):\n"
                    "- User Question: 'Sở thích của Chisa là gì vậy?'\n"
                    "- Current Context: '[Thinking Cycle 1 Search Results for 'Sở thích của Chisa']: Chisa thích ăn đồ ngọt, đặc biệt là que socola đen. Cô ấy cũng thích đi dạo ở công viên Honami vào buổi tối.'\n"
                    "- Output JSON:\n"
                    "{\n"
                    "  \"thinking\": \"Context hiện tại đã ghi rõ sở thích của Chisa là ăn đồ ngọt (que socola đen) và đi dạo ở công viên Honami vào buổi tối. Thông tin này đã đầy đủ để trả lời câu hỏi.\",\n"
                    "  \"has_enough_info\": true,\n"
                    "  \"search_query\": \"\"\n"
                    "}\n\n"
                    "Example 3 (Cycle 2 Multi-Hop Query Refinement):\n"
                    "- User Question: 'Tác giả của bộ truyện Doraemon sinh năm bao nhiêu và còn sống không?'\n"
                    "- Cycle 1 Query: 'Tác giả bộ truyện Doraemon'\n"
                    "- Cycle 1 Results: 'Doraemon là bộ truyện tranh Nhật Bản được sáng tác bởi họa sĩ Fujiko F. Fujio (bút danh của Hiroshi Fujimoto).'\n"
                    "- Output JSON:\n"
                    "{\n"
                    "  \"thinking\": \"Kết quả Cycle 1 đã xác định được tác giả là Fujiko F. Fujio (Hiroshi Fujimoto), nhưng chưa có thông tin về năm sinh và tình trạng còn sống/đã mất. Tôi cần dùng tên tác giả vừa tìm được để tra cứu năm sinh và ngày mất của ông.\",\n"
                    "  \"has_enough_info\": false,\n"
                    "  \"search_query\": \"Fujiko F. Fujio Hiroshi Fujimoto năm sinh ngày mất\"\n"
                    "}\n\n"
                    "You MUST output the result as a valid JSON object matching the requested schema."
                )

                if i > 1 and thinking_steps:
                    # Explicit Multi-Hop Context Injection for Cycle 2
                    cycle_1_step = thinking_steps[0]
                    cycle_1_query = cycle_1_step.get("search_query", "")
                    cycle_1_result = cycle_1_step.get("search_result", "")
                    user_prompt = (
                        f"[Conversation History]:\n{history_str}\n\n"
                        f"[User Original Question]: \"{user_message}\"\n\n"
                        f"[Cycle 1 Search Query Executed]: \"{cycle_1_query}\"\n"
                        f"[Cycle 1 Search Results Gathered]:\n{cycle_1_result}\n\n"
                        f"[Total Accumulated Context]:\n{current_context}\n\n"
                        f"INSTRUCTION FOR CYCLE 2 SEARCH REFINEMENT:\n"
                        f"1. Check if Cycle 1 results answer all facts of the User Original Question.\n"
                        f"2. If satisfied -> Set 'has_enough_info': true, 'search_query': ''.\n"
                        f"3. If missing information -> Synthesize new entities/keywords from Cycle 1 to produce a refined, deeper 'search_query' for Cycle 2."
                    )
                else:
                    user_prompt = (
                        f"[Conversation History]:\n{history_str}\n\n"
                        f"[User Question]: \"{user_message}\"\n\n"
                        f"[Current Context]:\n{current_context}"
                    )

                schema_properties = {
                    "has_enough_info": {"type": "boolean"},
                    "search_query": {"type": "string"}
                }
                required_fields = ["has_enough_info"]
                
                if is_reasoning_cycle:
                    schema_properties["thinking"] = {"type": "string"}
                    required_fields.append("thinking")

                schema = {
                    "type": "object",
                    "properties": schema_properties,
                    "required": required_fields
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
                # Only execute LLM call if not bypassed
                if not (i == 1 and initial_search_query and initial_search_query.strip()):
                    from app.domain.context import llm_call_purpose
                    llm_call_purpose.set(f"thinking_loop_cycle_{i}")
                    response = await llm.generate(prompt)
                    parsed = response.parsed or {}
                    reasoning_content = getattr(response, "reasoning_content", None)
                    thinking = reasoning_content or parsed.get("thinking", "")
                    
                    if not is_reasoning_cycle and not thinking:
                        thinking = f"Bypassed thinking for cycle {i} to save tokens."
                        
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
                    self.pipeline_tracker.add_step(f"thinking_loop_cycle_{i}", {
                        "thinking": thinking,
                        "has_enough_info": True,
                        "search_query": "",
                        "search_result": "No further search needed.",
                        "input_context": current_context
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

                context_before_search = current_context

                # Append to current context
                current_context += f"\n\n[Thinking Cycle {i} Reasoning]:\n{thinking}\n[Thinking Cycle {i} Search Results for '{search_query}']:\n{search_result_text}"

                thinking_steps.append({
                    "cycle": i,
                    "thinking": thinking,
                    "has_enough_info": False,
                    "search_query": search_query,
                    "search_result": search_result_text,
                    "search_detail": search_res,
                })
                # Add steps to tracker in real-time (Cycle first, then its inner web_search)
                self.pipeline_tracker.add_step(f"thinking_loop_cycle_{i}", {
                    "thinking": thinking,
                    "has_enough_info": False,
                    "search_query": search_query,
                    "search_result": search_result_text,
                    "input_context": context_before_search
                })
                from app.domain.services.tools.web_search import web_search_trace_payload
                self.pipeline_tracker.add_step(
                    "web_search",
                    web_search_trace_payload(
                        search_res,
                        source=f"thinking_loop_cycle_{i}",
                        original_message=search_query,
                    ),
                )

                # ── AUTO-SATISFY: Skip Cycle 2 LLM if Cycle 1 search returned valid results ──
                search_success = search_res.get("status") == "success"
                snippets = search_res.get("snippets") or []
                if i == 1 and initial_search_query and search_success and len(snippets) >= 2:
                    log.info(
                        "Auto-satisfying after Cycle 1 search: sufficient snippets returned, skipping Cycle 2 LLM",
                        snippet_count=len(snippets)
                    )
                    self.pipeline_tracker.add_step("thinking_loop_auto_satisfy", {
                        "cycle": 1,
                        "auto_satisfied": True,
                        "snippet_count": len(snippets),
                        "reason": f"Tìm kiếm Cycle 1 đã trả về {len(snippets)} snippets phù hợp. Tự động chuyển sang Prompt Build và bỏ qua lượt gọi LLM Cycle 2 để tối ưu latency."
                    })
                    break

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
