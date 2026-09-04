import asyncio
from typing import Any

from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.session import IDbSession
from app.domain.interfaces.tracker import IPipelineTracker
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class ThinkingLoopAgent:
    """
    Runs an iterative reasoning loop to search across Vector Store (Qdrant),
    Web (DuckDuckGo/Tavily/Serper), or Hybrid for missing information,
    acting as the Loop Thinking component of the RAG pipeline.
    """

    def __init__(
        self,
        pipeline_tracker: IPipelineTracker,
        lore_retriever: Any | None = None,
    ):
        self.pipeline_tracker = pipeline_tracker
        self.lore_retriever = lore_retriever

    async def run(
        self,
        session: IDbSession,
        user_id: str,
        user_message: str,
        history: list[dict[str, str]],
        initial_context: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        web_search_tool: Any,
        initial_search_query: str | None = None,
        initial_extracted_facts: str = "",
        lore_retriever: Any | None = None,
        initial_search_target: str = "web",
    ) -> tuple[str, list[dict[str, Any]]]:
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
                    initial_extracted_facts=initial_extracted_facts,
                    lore_retriever=lore_retriever or self.lore_retriever,
                    initial_search_target=initial_search_target,
                ),
                timeout=float(settings.THINKING_LOOP_TIMEOUT),
            )
        except TimeoutError:
            log.warning(
                "Thinking loop global timeout reached, returning accumulated context",
                user_message=user_message,
            )
            return initial_context, []

    async def _execute_adaptive_search(
        self,
        search_target: str,
        search_query: str,
        session: IDbSession,
        user_id: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider | None,
        web_search_tool: Any,
        history: list[dict[str, str]],
        lore_retriever: Any | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Executes adaptive search according to the target (vector, web, or both).
        """
        results = []
        details: dict[str, Any] = {
            "search_target": search_target,
            "search_query": search_query,
            "vector_results": [],
            "web_results": {},
            "status": "success",
            "snippets": [],
        }

        # 1. Vector Lore Search
        if search_target in ("vector", "both") and lore_retriever and embedder:
            try:
                log.info("Thinking loop executing Vector Search retry", query=search_query)
                query_vector = await embedder.embed_text(search_query, prefix="query: ")
                for collection in ["character_lore", "world_lore", "story_lore"]:
                    lore_res = await lore_retriever.retrieve_lore_parent_child(
                        collection=collection,
                        query_vector=query_vector,
                        session=session,
                        query_text=search_query,
                        top_k=3,
                        score_threshold=0.30,
                    )
                    for item in lore_res:
                        if len(item) == 3:
                            text, score, meta = item
                        elif len(item) == 2:
                            text, score = item
                            meta = {}
                        else:
                            text = str(item)
                            score = 0.5
                            meta = {}
                        results.append(f"[LORE ({collection})] (score={score:.2f}):\n{text}")
                        details["vector_results"].append(
                            {"text": text, "score": score, "collection": collection, "meta": meta}
                        )
            except Exception as ve:
                log.warning("Vector search in thinking loop failed", error=str(ve))

        # 2. Web Search
        if search_target in ("web", "both") and web_search_tool:
            try:
                log.info("Thinking loop executing Web Search", query=search_query)
                web_res = await web_search_tool.execute(
                    session=session,
                    user_id=user_id,
                    user_message=search_query,
                    llm=llm,
                    embedder=embedder,
                    history=history,
                    bypass_optimize=True,
                )
                web_text = web_res.get("message", "")
                if web_text:
                    results.append(f"[WEB SEARCH]:\n{web_text}")
                details["web_results"] = web_res
                details["snippets"] = web_res.get("snippets") or []
                details["provider"] = web_res.get("provider", "unknown")
                details["status"] = web_res.get("status", "success")
            except Exception as we:
                log.warning("Web search in thinking loop failed", error=str(we))

        result_text = "\n\n".join(results) if results else "No search results returned."
        return result_text, details

    async def _run_inner(
        self,
        session: IDbSession,
        user_id: str,
        user_message: str,
        history: list[dict[str, str]],
        initial_context: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        web_search_tool: Any,
        initial_search_query: str | None = None,
        initial_extracted_facts: str = "",
        lore_retriever: Any | None = None,
        initial_search_target: str = "web",
    ) -> tuple[str, list[dict[str, Any]]]:
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
        thinking_steps: list[dict[str, Any]] = []

        for i in range(1, max_cycles + 1):
            log.info("Starting thinking loop cycle", cycle=i)

            if i == 1 and initial_search_query and initial_search_query.strip():
                log.info(
                    "Bypassing Cycle 1 LLM query extraction using assessor query",
                    query=initial_search_query,
                )
                thinking = "ContextAssessor has already evaluated the initial context as unaligned and generated a targeted search query."
                has_enough_info = False
                search_query = initial_search_query.strip()
                search_target = initial_search_target or "web"
                distilled_facts = initial_extracted_facts or ""
            else:
                is_reasoning_cycle = False

                system_prompt = (
                    "You are an Adaptive Loop Thinking Agent for Kuchiba Chisa (Wuthering Waves).\n"
                    "Your goal is to gather objective, verifiable facts so Chisa can answer the user's specific question accurately.\n"
                    "Analyze the conversation history, the user's question, and the current accumulated context.\n\n"
                    "CRITICAL SCOPING RULES (PREVENT OVER-SEARCHING):\n"
                    "1. SCOPE-BOUND EVALUATION: Evaluate ONLY what the user explicitly asks for.\n"
                    "   - If the user asks a general question, general factual background is 100% SUFFICIENT -> set 'has_enough_info': true.\n"
                    "   - DO NOT demand encyclopedic completeness. NEVER search for combat stats, multipliers, or voice lines unless the user EXPLICITLY requested them.\n"
                    "2. SUFFICIENCY GATE: Set 'has_enough_info' to true when the current context contains enough facts to answer >80% of the question.\n"
                    "3. SEARCH TARGET ROUTING ('search_target') - ONLY WHEN has_enough_info = false:\n"
                    "  * 'vector': For character lore, story, and canon in-game mechanics (Default for game questions unless internet info is explicitly requested).\n"
                    "  * 'web': For real-world facts, news, release dates, patch notes, or internet discussions.\n"
                    "  * 'both': ONLY when comparing in-game lore with online discussions/leaks/buffs.\n"
                    "4. MANDATORY FACT DISTILLATION ('distilled_facts'):\n"
                    "  * Distill key factual points from context, preserving 100% of exact numbers, percentages, dates, proper names, entities, and formulas.\n"
                    "5. MULTI-HOP SEARCH REFINEMENT (CYCLE 2+):\n"
                    "  * Synthesize terms discovered in Cycle 1 to craft a sharper, targeted 'search_query' (4 to 8 terms) targeting ONLY the missing aspect.\n"
                    "  * DO NOT repeat the exact same search query as Cycle 1.\n\n"
                    "You MUST output the result as a valid JSON object matching the requested schema."
                )

                if i > 1 and thinking_steps:
                    cycle_1_step = thinking_steps[0]
                    cycle_1_query = cycle_1_step.get("search_query", "")
                    cycle_1_result = cycle_1_step.get("search_result", "")
                    user_prompt = (
                        f"[Conversation History]:\n{history_str}\n\n"
                        f"[User Original Question]: \"{user_message}\"\n\n"
                        f"[Cycle 1 Search Query Executed]: \"{cycle_1_query}\"\n"
                        f"[Cycle 1 Search Target]: \"{cycle_1_step.get('search_target', 'web')}\"\n"
                        f"[Cycle 1 Search Results Gathered]:\n{cycle_1_result}\n\n"
                        f"[Total Accumulated Context]:\n{current_context}\n\n"
                        f"INSTRUCTION FOR CYCLE 2 SEARCH REFINEMENT:\n"
                        f"1. Check if Cycle 1 results answer all facts of the User Original Question.\n"
                        f"2. If satisfied -> Set 'has_enough_info': true, 'search_query': '', 'distilled_facts': '<summary of facts>'.\n"
                        f"3. If missing information -> Choose 'search_target' ('vector', 'web', or 'both') and synthesize a refined 'search_query' for Cycle 2."
                    )
                else:
                    user_prompt = (
                        f"[Conversation History]:\n{history_str}\n\n"
                        f'[User Question]: "{user_message}"\n\n'
                        f"[Current Context]:\n{current_context}"
                    )

                schema_properties = {
                    "has_enough_info": {"type": "boolean"},
                    "search_query": {"type": "string"},
                    "search_target": {
                        "type": "string",
                        "enum": ["web", "vector", "both"],
                        "description": (
                            "Nguồn tìm kiếm tiếp theo: 'vector' = Qdrant game lore DB, "
                            "'web' = Internet search, 'both' = cả hai."
                        ),
                    },
                    "distilled_facts": {
                        "type": "string",
                        "description": (
                            "Tóm tắt dữ kiện quan trọng từ context hiện tại "
                            "(giữ nguyên 100% số liệu, tên riêng, ngày tháng, công thức)"
                        ),
                    },
                }
                required_fields = ["has_enough_info"]

                if is_reasoning_cycle:
                    schema_properties["thinking"] = {"type": "string"}
                    required_fields.append("thinking")

                schema = {
                    "type": "object",
                    "properties": schema_properties,
                    "required": required_fields,
                }

                prompt = StructuredPrompt(
                    system=system_prompt,
                    history=[],
                    user_message=user_prompt,
                    response_schema=schema,
                    retrieved_memories=[],
                    retrieved_lore=[],
                    rag_decisions={"use_deep_thinking": False},
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
                    search_target = parsed.get("search_target") or "web"
                    distilled_facts = (parsed.get("distilled_facts") or "").strip()

                context_is_empty = (
                    not current_context.strip()
                    or current_context.strip() == "(No context retrieved)"
                )
                if context_is_empty and not has_enough_info and not search_query:
                    search_query = user_message.strip()

                log.info(
                    "Thinking cycle evaluated",
                    cycle=i,
                    has_enough_info=has_enough_info,
                    search_query=search_query,
                    search_target=search_target,
                )

                if has_enough_info or not search_query:
                    thinking_steps.append(
                        {
                            "cycle": i,
                            "thinking": thinking,
                            "has_enough_info": True,
                            "search_query": "",
                            "search_target": search_target,
                            "distilled_facts": distilled_facts,
                            "search_result": "No further search needed.",
                        }
                    )
                    self.pipeline_tracker.add_step(
                        name=f"thinking_loop_cycle_{i}",
                        stage_id="stage_5_rag",
                        depth=1,
                        category="llm_inference",
                        title=f"5.3.{i} [THINKING] Vòng lặp Loop Thinking Cycle {i}",
                        subtitle="✓ Đã thu thập đủ thông tin (Dừng vòng lặp)",
                        data={
                            "thinking": thinking,
                            "has_enough_info": True,
                            "search_query": "",
                            "search_target": search_target,
                            "distilled_facts": distilled_facts,
                            "search_result": "No further search needed.",
                            "input_context": current_context,
                        },
                    )
                    break

                # Execute Adaptive Search (vector, web, or both)
                search_result_text, search_details = await self._execute_adaptive_search(
                    search_target=search_target,
                    search_query=search_query,
                    session=session,
                    user_id=user_id,
                    llm=llm,
                    embedder=embedder,
                    web_search_tool=web_search_tool,
                    history=history,
                    lore_retriever=lore_retriever,
                )

                context_before_search = current_context

                # Append to current context
                current_context += f"\n\n[Thinking Cycle {i} ({search_target.upper()}) Reasoning]:\n{thinking}\n[Thinking Cycle {i} Results for '{search_query}']:\n{search_result_text}"

                step_data = {
                    "cycle": i,
                    "thinking": thinking,
                    "has_enough_info": False,
                    "search_query": search_query,
                    "search_target": search_target,
                    "distilled_facts": distilled_facts,
                    "search_result": search_result_text,
                    "search_detail": search_details,
                }
                thinking_steps.append(step_data)

                # ── Real-time step logging for Inspector / Visualizer ──
                self.pipeline_tracker.add_step(
                    name=f"thinking_loop_cycle_{i}",
                    stage_id="stage_5_rag",
                    depth=1,
                    category="llm_inference",
                    title=f"5.3.{i} [THINKING] Vòng lặp Loop Thinking Cycle {i}",
                    subtitle=f'Đang tìm kiếm ({search_target.upper()}): "{search_query[:24]}..."',
                    data={
                        "thinking": thinking,
                        "has_enough_info": False,
                        "search_query": search_query,
                        "search_target": search_target,
                        "distilled_facts": distilled_facts,
                        "search_result": search_result_text,
                        "input_context": context_before_search,
                    },
                )

                # Sub-node for Vector Lore Retrieval (5.3.i.1)
                if search_target in ("vector", "both") and search_details.get("vector_results"):
                    self.pipeline_tracker.add_step(
                        name="lore_retrieval",
                        stage_id="stage_5_rag",
                        depth=2,
                        category="retrieval",
                        title=f"5.3.{i}.1 [VECTOR] Qdrant Lore Retrieval",
                        subtitle=f"\"{search_query[:24]}...\" ({len(search_details.get('vector_results', []))} chunks)",
                        data={
                            "query": search_query,
                            "source": f"thinking_loop_cycle_{i}",
                            "chunks_count": len(search_details.get("vector_results", [])),
                            "chunks": search_details.get("vector_results", []),
                        },
                    )

                # Sub-node for Web Search (5.3.i.1 or 5.3.i.2)
                if search_target in ("web", "both") and search_details.get("web_results"):
                    from app.domain.services.tools.web_search import web_search_trace_payload

                    web_sub_idx = (
                        "2"
                        if (search_target == "both" and search_details.get("vector_results"))
                        else "1"
                    )
                    self.pipeline_tracker.add_step(
                        name="web_search",
                        stage_id="stage_5_rag",
                        depth=2,
                        category="tool_execution",
                        title=f"5.3.{i}.{web_sub_idx} [TOOL] DuckDuckGo Search & Crawler",
                        subtitle=f"\"{search_query[:24]}...\" ({len(search_details.get('snippets', []))} snippets)",
                        data=web_search_trace_payload(
                            search_details["web_results"],
                            source=f"thinking_loop_cycle_{i}",
                            original_message=search_query,
                        ),
                    )

                # ── AUTO-SATISFY: Skip Cycle 2 LLM if Cycle 1 search returned valid results ──
                snippets = search_details.get("snippets") or []
                vector_hits = search_details.get("vector_results") or []
                web_success = search_details.get("status") == "success" and len(snippets) >= 2
                vector_success = len(vector_hits) >= 1

                if search_target == "both":
                    is_satisfied = web_success and vector_success
                    satisfied_reason = (
                        f"Tìm kiếm Hybrid Cycle 1 trả về {len(vector_hits)} vector chunks và {len(snippets)} web snippets. "
                        "Đầy đủ cả 2 nguồn tri thức ➔ Tự động chuyển sang Prompt Build."
                    )
                elif search_target == "vector":
                    is_satisfied = vector_success
                    satisfied_reason = (
                        f"Tìm kiếm Vector Cycle 1 trả về {len(vector_hits)} vector chunks phù hợp. "
                        "Tự động chuyển sang Prompt Build để tối ưu latency."
                    )
                else:  # "web"
                    is_satisfied = web_success
                    satisfied_reason = (
                        f"Tìm kiếm Web Cycle 1 trả về {len(snippets)} web snippets phù hợp. "
                        "Tự động chuyển sang Prompt Build để tối ưu latency."
                    )

                if i == 1 and is_satisfied:
                    log.info("Auto-satisfying after Cycle 1 search", reason=satisfied_reason)
                    self.pipeline_tracker.add_step(
                        name="thinking_loop_auto_satisfy",
                        stage_id="stage_5_rag",
                        depth=1,
                        category="decision",
                        title="5.3.2 [AUTO-SATISFY] Tự động Thỏa mãn Dữ liệu",
                        subtitle="Đã đủ dữ liệu ➔ Bỏ qua Cycle 2",
                        data={
                            "cycle": 1,
                            "auto_satisfied": True,
                            "search_target": search_target,
                            "snippet_count": len(snippets),
                            "vector_count": len(vector_hits),
                            "reason": satisfied_reason,
                        },
                    )
                    break

            except Exception as e:
                log.error("Error in thinking loop cycle", cycle=i, error=str(e))
                thinking_steps.append(
                    {
                        "cycle": i,
                        "thinking": f"Error occurred: {str(e)}",
                        "has_enough_info": True,
                        "search_query": "",
                        "search_target": "none",
                        "distilled_facts": "",
                        "search_result": "",
                    }
                )
                break

        return current_context, thinking_steps
