import asyncio
import os
import re
import datetime
import contextvars
from typing import Any, List
from app.domain.interfaces.llm_provider import StructuredPrompt, LLMResponse

LOG_FILE_PATH = "llm_api_clean.txt"

# Context variables to track Question Index and Turn Index within each request context
request_question_idx: contextvars.ContextVar[int] = contextvars.ContextVar("request_question_idx", default=1)
request_turn_idx: contextvars.ContextVar[int] = contextvars.ContextVar("request_turn_idx", default=1)
llm_call_purpose: contextvars.ContextVar[str] = contextvars.ContextVar("llm_call_purpose", default="unknown")
enable_clean_log: contextvars.ContextVar[bool] = contextvars.ContextVar("enable_clean_log", default=False)

LLM_PURPOSE_LABELS: dict[str, str] = {
    "chat_response": "Trả lời Chisa (call chính)",
    "alignment_assessor": "Alignment Assessor",
    "web_search_query_extract": "Web Search · trích query",
    "unknown": "LLM call (không gắn nhãn)",
}


def purpose_label(purpose: str) -> str:
    if purpose in LLM_PURPOSE_LABELS:
        return LLM_PURPOSE_LABELS[purpose]
    if purpose.startswith("thinking_loop_cycle_"):
        n = purpose.replace("thinking_loop_cycle_", "")
        return f"Loop Thinking · Cycle {n}"
    return purpose


def _write_routing_log_sync(
    user_message: str,
    is_small_talk: bool,
    intents: List[str],
    tool_name: str,
    tool_score: float,
    tool_result: str,
    q_idx: int
) -> None:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    log_content = f"""================================================================================
LẦN HỎI {q_idx}
================================================================================
Thời gian: {now_str}
Tin nhắn của User: "{user_message}"

[SEMANTIC ROUTING & TOOL DECISION]
- Phân loại kiểu tin nhắn: {"Small Talk (Bypass RAG)" if is_small_talk else "Lore Talk (Truy cập RAG)"}
- Định tuyến intent (Semantic Router): {intents}
- Định tuyến Tool (Semantic Tool Router): Tool = "{tool_name}" (Confidence: {tool_score:.4f})
- Kết quả thực thi Tool: {tool_result if tool_result else "Không kích hoạt hoặc bỏ qua"}

================================================================================

"""
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(log_content)


async def log_routing_transaction(
    user_message: str,
    is_small_talk: bool,
    intents: List[str],
    tool_name: str,
    tool_score: float,
    tool_result: str
) -> None:
    """
    Asynchronously logs the Semantic Routing & Tool Decisions to the clean txt file.
    Runs inside a thread pool to avoid blocking the event loop.
    """
    try:
        if not enable_clean_log.get():
            return
        q_idx = request_question_idx.get()
        await asyncio.to_thread(
            _write_routing_log_sync,
            user_message,
            is_small_talk,
            intents,
            tool_name,
            tool_score,
            tool_result,
            q_idx
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to write clean Routing log: {e}")


def _write_log_sync(prompt: StructuredPrompt, response: LLMResponse, q_idx: int, t_idx: int) -> None:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Format chat history
    history_lines = []
    if prompt.history:
        for msg in prompt.history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            history_lines.append(f"- {role}: {content}")
    else:
        history_lines.append("(Không có lịch sử trò chuyện)")
    history_str = "\n".join(history_lines)
    
    # Format parsed response
    parsed_lines = []
    if response.parsed:
        for k, v in response.parsed.items():
            parsed_lines.append(f"{k}: {v}")
    else:
        parsed_lines.append("(Không thể phân tích dữ liệu)")
    parsed_str = "\n".join(parsed_lines)
    
    # Format RAG information
    decisions = prompt.rag_decisions or {}
    use_lore = decisions.get("use_lore", False)
    use_memory = decisions.get("use_memory", False)
    decisions_str = f"Lấy Lore (use_lore): {use_lore} | Lấy Ký ức (use_memory): {use_memory}"
    
    lore_lines = []
    if prompt.retrieved_lore:
        for i, chunk in enumerate(prompt.retrieved_lore, 1):
            chunk_snippet = chunk.replace("\n", " ").strip()
            lore_lines.append(f"  + Mảnh {i}: {chunk_snippet}")
    else:
        lore_lines.append("  (Không có dữ liệu Lore được lấy)")
    lore_str = "\n".join(lore_lines)
    
    memory_lines = []
    if prompt.retrieved_memories:
        for i, mem in enumerate(prompt.retrieved_memories, 1):
            text = getattr(mem, "text_content", str(mem))
            tier = getattr(mem, "memory_tier", "N/A")
            score = getattr(mem, "final_score", 0.0)
            comps = getattr(mem, "components", {})
            memory_lines.append(f"  + Ký ức {i}: {text} (Loại: {tier}, Score: {score:.4f}, Components: {comps})")
    else:
        memory_lines.append("  (Không có dữ liệu Ký ức được lấy)")
    memories_str = "\n".join(memory_lines)
    
    log_content = f"""===== LƯỢT {t_idx} =====
LẦN HỎI: {q_idx}
Thời gian: {now_str}
Model sử dụng: {response.model}

--------------------------------------------------------------------------------
[1. REQUEST GỬI LÊN API LLM]
--------------------------------------------------------------------------------
[RAG RETRIEVAL INFO]
- Quyết định RAG Router: {decisions_str}
- Kết quả truy xuất Lore:
{lore_str}
- Kết quả truy xuất Memory:
{memories_str}

[SYSTEM PROMPT]
{prompt.system}

[CHAT HISTORY]
{history_str}

[USER MESSAGE]
{prompt.user_message}

--------------------------------------------------------------------------------
[2. RESPONSE TRẢ VỀ TỪ API LLM]
--------------------------------------------------------------------------------
[FINISH REASON]
{response.finish_reason}

[USAGE METADATA]
Input Tokens: {response.input_tokens}
Output Tokens: {response.output_tokens}
Total Tokens: {response.input_tokens + response.output_tokens}

[RAW CONTENT]
{response.raw_content}

[PARSED JSON]
{parsed_str}

================================================================================

"""
    # Open with 'a' mode for appending, encoding utf-8 to support Vietnamese
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(log_content)


async def log_llm_transaction(prompt: StructuredPrompt, response: LLMResponse) -> None:
    """
    Asynchronously logs a complete LLM transaction (Request & Response) to a clean txt file.
    Runs inside a thread pool to avoid blocking the event loop.
    """
    try:
        q_idx = request_question_idx.get()
        t_idx = request_turn_idx.get()
        # Increment the turn counter in the request context (main thread)
        request_turn_idx.set(t_idx + 1)
        
        # Add LLM call step to the pipeline tracker
        try:
            from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
            purpose = llm_call_purpose.get()
            pipeline_tracker.add_step("llm_generation", {
                "model": response.model,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.input_tokens + response.output_tokens,
                "finish_reason": response.finish_reason,
                "raw_response": response.raw_content,
                "parsed_response": response.parsed,
                "purpose": purpose,
                "purpose_label": purpose_label(purpose),
                "call_index": t_idx,
                "token_source": "api",
                "system_prompt": prompt.system,
                "user_message": prompt.user_message,
            })
        except Exception:
            pass

        if not enable_clean_log.get():
            return

        await asyncio.to_thread(_write_log_sync, prompt, response, q_idx, t_idx)
    except Exception as e:
        # Prevent logging errors from crashing the main chat flow
        import logging
        logging.getLogger(__name__).warning(f"Failed to write clean LLM log: {e}")
