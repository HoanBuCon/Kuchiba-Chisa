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

async def log_llm_transaction(prompt: StructuredPrompt, response: LLMResponse) -> None:
    try:
        q_idx = request_question_idx.get()
        t_idx = request_turn_idx.get()
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
                "reasoning_content": response.reasoning_content,
                "history": prompt.history,
            })
        except Exception:
            pass

        if not enable_clean_log.get():
            return

        await asyncio.to_thread(_write_log_sync, prompt, response, q_idx, t_idx)
    except Exception as e:
        import logging as py_logging
        py_logging.getLogger(__name__).warning(f"Failed to write LLM telemetry: {e}")
