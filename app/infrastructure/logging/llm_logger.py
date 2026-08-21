import asyncio
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from typing import Any, List
from app.domain.interfaces.llm_provider import StructuredPrompt, LLMResponse
from app.config.settings import settings
from app.domain.context import (
    request_question_idx,
    request_turn_idx,
    llm_call_purpose,
    enable_clean_log
)
from app.infrastructure.logging.pipeline_tracker import current_trace_var

# ─── JSON Formatter ───────────────────────────────────────────────────────────

class LLMTelemetryFormatter(logging.Formatter):
    """Formats log records as JSON lines with an ISO8601 UTC timestamp."""
    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            data = record.msg.copy()
        else:
            data = {"message": str(record.msg)}
            
        # Ensure timestamp is ISO8601 UTC
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        return json.dumps(data, ensure_ascii=False)


# ─── Logger Initialization ────────────────────────────────────────────────────

llm_telemetry_logger = logging.getLogger("llm_telemetry")
llm_telemetry_logger.setLevel(logging.INFO)
llm_telemetry_logger.propagate = False  # Do not propagate to root logger

def _init_logger():
    if not llm_telemetry_logger.handlers:
        log_dir = os.path.dirname(settings.LLM_LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            
        handler = RotatingFileHandler(
            settings.LLM_LOG_FILE,
            maxBytes=settings.LLM_LOG_MAX_BYTES,
            backupCount=settings.LLM_LOG_BACKUP_COUNT,
            encoding="utf-8"
        )
        handler.setFormatter(LLMTelemetryFormatter())
        llm_telemetry_logger.addHandler(handler)

# Initialize on module load
_init_logger()


# ─── Purpose Labels ───────────────────────────────────────────────────────────

LLM_PURPOSE_LABELS: dict[str, str] = {
    "chat_response": "Trả lời Chisa (call chính)",
    "micro_llm_query_rewrite": "Viết lại câu hỏi & Router RAG (Micro LLM)",
    "query_rewrite": "Viết lại câu hỏi (Query Rewrite)",
    "alignment_assessor": "Alignment Assessor",
    "web_search_query_extract": "Web Search · trích query",
    "summarize_conversation": "Tóm tắt hội thoại (Tool Summarize)",
    "unified_auto_summarize": "Tự động tóm tắt ngầm (Auto-Summarize)",
    "memory_extraction": "Trích xuất ký ức (Memory Extractor)",
    "memory_reconciliation": "Giải quyết mâu thuẫn ký ức (Memory Reconciliation)",
    "unknown": "LLM call (không gắn nhãn)",
}

def purpose_label(purpose: str) -> str:
    if purpose in LLM_PURPOSE_LABELS:
        return LLM_PURPOSE_LABELS[purpose]
    if purpose.startswith("thinking_loop_cycle_"):
        n = purpose.replace("thinking_loop_cycle_", "")
        return f"Loop Thinking · Cycle {n}"
    return purpose


# ─── Routing Logger ───────────────────────────────────────────────────────────

def _write_routing_log_sync(
    user_message: str,
    is_small_talk: bool,
    intents: List[str],
    tool_name: str,
    tool_score: float,
    tool_result: str,
    q_idx: int
) -> None:
    trace = current_trace_var.get()
    
    payload = {
        "event_type": "semantic_routing",
        "request_id": trace.get("id") if trace else None,
        "user_id": trace.get("user_id") if trace else None,
        "question_idx": q_idx,
        "user_message": user_message,
        "is_small_talk": is_small_talk,
        "intents": intents,
        "tool_routing": {
            "tool_name": tool_name,
            "confidence": tool_score,
            "result_summary": tool_result if tool_result else None
        }
    }
    llm_telemetry_logger.info(payload)

async def log_routing_transaction(
    user_message: str,
    is_small_talk: bool,
    intents: List[str],
    tool_name: str,
    tool_score: float,
    tool_result: str
) -> None:
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
        import logging as py_logging
        py_logging.getLogger(__name__).warning(f"Failed to write routing telemetry: {e}")


# ─── LLM Transaction Logger ───────────────────────────────────────────────────

def _write_log_sync(prompt: StructuredPrompt, response: LLMResponse, q_idx: int, t_idx: int) -> None:
    trace = current_trace_var.get()
    purpose = llm_call_purpose.get()
    
    # Extract retrieval metadata
    decisions = prompt.rag_decisions or {}
    retrieval_metadata = {
        "use_lore": decisions.get("use_lore", False),
        "use_memory": decisions.get("use_memory", False),
        "lore_count": len(prompt.retrieved_lore) if prompt.retrieved_lore else 0,
        "memory_count": len(prompt.retrieved_memories) if prompt.retrieved_memories else 0
    }
    
    # Optional intent from trace
    intent = None
    if trace and "steps" in trace:
        for step in trace["steps"]:
            if step.get("name") == "intent_stage":
                intent = step.get("data", {}).get("intents")
                break
    
    payload = {
        "event_type": "llm_generation",
        "request_id": trace.get("id") if trace else None,
        "user_id": trace.get("user_id") if trace else None,
        "provider": settings.LLM_PROVIDER,
        "model": response.model,
        "purpose": purpose,
        "purpose_label": purpose_label(purpose),
        "latency_ms": 0.0,  # Not tracked at this layer yet
        "prompt_tokens": response.input_tokens,
        "completion_tokens": response.output_tokens,
        "reasoning_tokens": getattr(response, "reasoning_tokens", 0),
        "total_tokens": response.input_tokens + response.output_tokens,
        "intent": intent,
        "retrieval_metadata": retrieval_metadata,
        "status": "success",
        
        # Additional debug details
        "details": {
            "question_idx": q_idx,
            "turn_idx": t_idx,
            "finish_reason": response.finish_reason,
            "parsed_response": response.parsed
        }
    }
    llm_telemetry_logger.info(payload)

def compute_token_breakdown(prompt: StructuredPrompt, response: LLMResponse) -> dict[str, Any]:
    """
    Computes a fine-grained token breakdown across all input and output components.
    """
    from app.shared.utils.token_estimator import TokenEstimator

    system_text = prompt.system or ""
    user_text = prompt.user_message or ""
    history = prompt.history or []

    # 1. Parse sub-sections from system_text if present
    lore_text = ""
    memories_text = ""
    search_text = ""
    summary_text = ""
    format_text = ""

    if "[LORE — REFERENCE DATA START]" in system_text and "[LORE — REFERENCE DATA END]" in system_text:
        start = system_text.find("[LORE — REFERENCE DATA START]")
        end = system_text.find("[LORE — REFERENCE DATA END]") + len("[LORE — REFERENCE DATA END]")
        lore_text = system_text[start:end]

    if "[MEMORIES — REFERENCE DATA START]" in system_text and "[MEMORIES — REFERENCE DATA END]" in system_text:
        start = system_text.find("[MEMORIES — REFERENCE DATA START]")
        end = system_text.find("[MEMORIES — REFERENCE DATA END]") + len("[MEMORIES — REFERENCE DATA END]")
        memories_text = system_text[start:end]

    if "[SEARCH DATA — REFERENCE DATA START]" in system_text and "[SEARCH DATA — REFERENCE DATA END]" in system_text:
        start = system_text.find("[SEARCH DATA — REFERENCE DATA START]")
        end = system_text.find("[SEARCH DATA — REFERENCE DATA END]") + len("[SEARCH DATA — REFERENCE DATA END]")
        search_text = system_text[start:end]

    if "[CONVERSATION SUMMARY]" in system_text:
        start = system_text.find("[CONVERSATION SUMMARY]")
        next_markers = ["[MEMORIES", "[LORE", "[SEARCH DATA", "[OUTPUT FORMAT", "\n\n["]
        end = len(system_text)
        for m in next_markers:
            p = system_text.find(m, start + len("[CONVERSATION SUMMARY]"))
            if p != -1 and p < end:
                end = p
        summary_text = system_text[start:end].strip()

    if "[OUTPUT FORMAT]" in system_text:
        start = system_text.find("[OUTPUT FORMAT]")
        format_text = system_text[start:].strip()

    # Calculate token counts for each section
    lore_tokens = TokenEstimator.estimate(lore_text) if lore_text else sum(TokenEstimator.estimate(c) for c in (getattr(prompt, "retrieved_lore", []) or []))
    memory_tokens = TokenEstimator.estimate(memories_text) if memories_text else sum(TokenEstimator.estimate(m.text_content if hasattr(m, 'text_content') else str(m)) for m in (getattr(prompt, "retrieved_memories", []) or []))
    search_tokens = TokenEstimator.estimate(search_text) if search_text else 0
    summary_tokens = TokenEstimator.estimate(summary_text) if summary_text else 0
    format_tokens = TokenEstimator.estimate(format_text) if format_text else 0

    total_system_tokens = TokenEstimator.estimate(system_text)
    base_system_tokens = max(0, total_system_tokens - lore_tokens - memory_tokens - search_tokens - summary_tokens - format_tokens)
    if base_system_tokens == 0 and total_system_tokens > 0:
        base_system_tokens = total_system_tokens

    history_tokens = TokenEstimator.estimate_messages(history, overhead_per_msg=4) if history else 0
    user_tokens = TokenEstimator.estimate(user_text)

    reasoning_tokens = getattr(response, "reasoning_tokens", 0) or 0
    if not reasoning_tokens and getattr(response, "reasoning_content", None):
        reasoning_tokens = TokenEstimator.estimate(response.reasoning_content)

    output_tokens = response.output_tokens or TokenEstimator.estimate(response.raw_content or "")
    total_input = response.input_tokens or (total_system_tokens + history_tokens + user_tokens)
    total_tokens = total_input + output_tokens + reasoning_tokens

    return {
        "system_prompt": total_system_tokens,
        "base_system": base_system_tokens,
        "format_instructions": format_tokens,
        "context_lore": lore_tokens,
        "context_memories": memory_tokens,
        "context_web_search": search_tokens,
        "conversation_summary": summary_tokens,
        "conversation_history": history_tokens,
        "user_message": user_tokens,
        "reasoning_cot": reasoning_tokens,
        "completion_output": output_tokens,
        "total_input": total_input,
        "total_output": output_tokens,
        "total_tokens": total_tokens,
        "history_count": len(history),
        "lore_count": len(getattr(prompt, "retrieved_lore", []) or []),
        "memory_count": len(getattr(prompt, "retrieved_memories", []) or []),
    }


async def log_llm_transaction(prompt: StructuredPrompt, response: LLMResponse) -> None:
    try:
        q_idx = request_question_idx.get()
        t_idx = request_turn_idx.get()
        request_turn_idx.set(t_idx + 1)
        
        token_breakdown = compute_token_breakdown(prompt, response)

        # Add LLM call step to the pipeline tracker
        try:
            from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
            purpose = llm_call_purpose.get()
            is_deep_thinking = prompt.rag_decisions.get("use_deep_thinking", False) if hasattr(prompt, "rag_decisions") and prompt.rag_decisions else False
            is_main_chat = (purpose == "chat_response" or not purpose or purpose == "unknown")

            if is_main_chat:
                pipeline_tracker.add_step(
                    name="llm_generation",
                    stage_id="stage_7_llm",
                    depth=0,
                    category="llm_inference",
                    title="Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)",
                    subtitle=f"Model: {response.model} · {token_breakdown['total_tokens']} tokens",
                    tokens=token_breakdown,
                    data={
                        "model": response.model,
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "reasoning_tokens": token_breakdown["reasoning_cot"],
                        "total_tokens": token_breakdown["total_tokens"],
                        "token_breakdown": token_breakdown,
                        "finish_reason": response.finish_reason,
                        "raw_response": response.raw_content,
                        "parsed_response": response.parsed,
                        "purpose": purpose or "chat_response",
                        "purpose_label": purpose_label(purpose or "chat_response"),
                        "call_index": t_idx,
                        "token_source": "api",
                        "system_prompt": prompt.system,
                        "user_message": prompt.user_message,
                        "use_deep_thinking": is_deep_thinking,
                        "reasoning_content": response.reasoning_content,
                        "history": prompt.history,
                        "temperature": getattr(prompt, "temperature", 0.5),
                    }
                )
            else:
                # Sub-calls (Micro Rewriter, Assessor, Thinking Loop cycles):
                # Do not emit a standalone root node, but aggregate tokens in trace and attach telemetry to parent stage
                trace = pipeline_tracker.get_current_trace()
                if trace:
                    in_tok = response.input_tokens or token_breakdown["total_input"]
                    out_tok = response.output_tokens or token_breakdown["total_output"]
                    reason_tok = token_breakdown.get("reasoning_cot", 0) or getattr(response, "reasoning_tokens", 0)
                    tot_tok = token_breakdown.get("total_tokens") or (in_tok + out_tok + reason_tok)

                    trace["total_input_tokens"] = trace.get("total_input_tokens", 0) + in_tok
                    trace["total_output_tokens"] = trace.get("total_output_tokens", 0) + out_tok
                    trace["total_reasoning_tokens"] = trace.get("total_reasoning_tokens", 0) + reason_tok
                    trace["total_tokens"] = trace.get("total_tokens", 0) + tot_tok

                    # Attach sub-call telemetry to parent stage payload
                    if "steps" in trace and trace["steps"]:
                        for s in reversed(trace["steps"]):
                            if purpose in ("micro_llm_query_rewrite", "query_rewrite") and s.get("name") in ("intent_classification", "intent_stage"):
                                s["data"]["llm_rewrite_telemetry"] = {
                                    "model": response.model,
                                    "tokens": token_breakdown,
                                    "raw_response": response.raw_content,
                                    "parsed_response": response.parsed
                                }
                                break
                            elif purpose in ("alignment_assessor", "context_assessor") and s.get("name") in ("information_alignment_check", "alignment_assessment"):
                                s["data"]["assessor_llm_telemetry"] = {
                                    "model": response.model,
                                    "tokens": token_breakdown,
                                    "raw_response": response.raw_content,
                                    "parsed_response": response.parsed
                                }
                                break
                            elif purpose.startswith("thinking_loop_cycle_") and s.get("name") == purpose:
                                s["data"]["llm_telemetry"] = {
                                    "model": response.model,
                                    "tokens": token_breakdown,
                                    "raw_response": response.raw_content,
                                    "parsed_response": response.parsed
                                }
                                break
        except Exception:
            pass


        if not enable_clean_log.get():
            return

        await asyncio.to_thread(_write_log_sync, prompt, response, q_idx, t_idx)
    except Exception as e:
        import logging as py_logging
        py_logging.getLogger(__name__).warning(f"Failed to write LLM telemetry: {e}")
