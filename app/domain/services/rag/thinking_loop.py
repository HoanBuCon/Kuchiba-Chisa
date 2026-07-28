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
                from app.config.settings import settings
                is_reasoning_cycle = (i > 1)
                use_deep_thinking = settings.DEEP_THINKING and is_reasoning_cycle

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
                )
                
                if is_reasoning_cycle:
                    if use_deep_thinking:
                        system_prompt += "- Analyze the context thoroughly before generating the final JSON. Provide a highly-optimized search query under 'search_query'.\n"
                    else:
                        system_prompt += "- If has_enough_info is false, write step-by-step reasoning under 'thinking' and generate a highly-optimized search query under 'search_query'.\n"
                else:
                    system_prompt += "- Output the JSON immediately without reasoning. Provide a highly-optimized search query under 'search_query'.\n"
                
                system_prompt += (
                    "- When generating a 'search_query', you must optimize it specifically for search engines (like DuckDuckGo):\n"
                    "  * Keep it focused and keyword-based. Strip out conversational fillers, greetings, punctuation, and generic question words (e.g., do NOT use 'cho hỏi', 'em ơi', 'là gì', 'được không', 'của em', 'vậy em', 'nhé').\n"
                    "  * Resolve pronouns and relative terms to their absolute names (e.g., 'em' -> 'Kuchiba Chisa', 'game này' -> 'Wuthering Waves').\n"
                    "  * CRITICAL FOR RELEVANCE: Retain all distinct semantic constraints from the user's question. Do NOT over-truncate. A high-quality query must combine: (1) the primary Subject/Entity, (2) the target Action/Attribute, and (3) key qualifiers (such as Location, Nationality, or specific Industry). Omitting any of these distinct constraints makes the search too broad and yields useless results.\n"
                    "  * Focus on semantic completeness: include all distinct constraints in a concise manner (typically 4 to 8 search terms). Do not search for a broad profile if the user asks about a very specific attribute.\n"
                    "  * Keep the language consistent: use clean, direct keywords matching the language of the query. Do NOT mix conversational Vietnamese and English.\n"
                    "  * Context Integration: You are encouraged to combine context from the [Conversation History], the [Current Context], and the [User Question] to formulate the best search query. However, you MUST intelligently filter out irrelevant fictional concepts, lore, or names that do not directly pertain to the specific question being asked.\n\n"
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

                schema_properties = {
                    "has_enough_info": {"type": "boolean"},
                    "search_query": {"type": "string"}
                }
                required_fields = ["has_enough_info"]
                
                if is_reasoning_cycle and not use_deep_thinking:
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
                    rag_decisions={"use_deep_thinking": use_deep_thinking}
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
                        thinking = "Bypassed thinking for cycle 1 to save tokens."
                        
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
                # Add steps to tracker in real-time
                from app.domain.services.tools.web_search import web_search_trace_payload
                self.pipeline_tracker.add_step(
                    "web_search",
                    web_search_trace_payload(
                        search_res,
                        source=f"thinking_loop_cycle_{i}",
                        original_message=search_query,
                    ),
                )
                self.pipeline_tracker.add_step(f"thinking_loop_cycle_{i}", {
                    "thinking": thinking,
                    "has_enough_info": False,
                    "search_query": search_query,
                    "search_result": search_result_text,
                    "input_context": context_before_search
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
