import json
import time
import uuid
import datetime
import asyncio
import contextvars
from typing import Any, Dict, List, Set, Callable, Optional

from app.shared.utils.logger import get_logger

log = get_logger(__name__)

# Request-scoped trace variable
current_trace_var: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar("current_trace_var", default={})

REDIS_PUBSUB_CHANNEL = "chisa:pipeline_events"
REDIS_HISTORY_KEY = "chisa:pipeline_history"


from enum import Enum

class StepCategory(str, Enum):
    STAGE_ROOT = "stage_root"           # Node gốc của 1 trong 10 giai đoạn
    LLM_INFERENCE = "llm_inference"     # Lượt gọi LLM (có prompt, response, tokens)
    RETRIEVAL = "retrieval"             # Truy vấn vector hoặc web search
    TOOL_EXECUTION = "tool_execution"   # Thực thi công cụ
    DECISION = "decision"               # Đánh giá logic, phân loại
    DATA_PROCESSING = "data_processing"  # Tính toán nội bộ, cảm xúc, persistence

STEP_NAME_TO_STAGE_ID = {
    "initialization": "stage_1_init",
    "init_stage": "stage_1_init",
    "intent_classification": "stage_2_intent",
    "intent_stage": "stage_2_intent",
    "query_rewrite": "stage_2_intent",
    "cache_check": "stage_3_cache",
    "cache_lookup": "stage_3_cache",
    "cache_stage": "stage_3_cache",
    "tool_routing": "stage_4_tool",
    "tool_routing_stage": "stage_4_tool",
    "rag_retrieval": "stage_5_rag",
    "rag_stage": "stage_5_rag",
    "lore_retrieval": "stage_5_rag",
    "memory_retrieval": "stage_5_rag",
    "web_search": "stage_5_rag",
    "information_alignment_check": "stage_5_rag",
    "alignment_assessment": "stage_5_rag",
    "thinking_loop_auto_satisfy": "stage_5_rag",
    "context_building": "stage_6_prompt",
    "context_builder": "stage_6_prompt",
    "llm_generation": "stage_7_llm",
    "emotion_update": "stage_8_emotion",
    "persistence": "stage_9_persist",
    "persistence_stage": "stage_9_persist",
    "cache_update": "stage_9_persist",
    "background_tasks": "stage_10_bg",
    "background_stage": "stage_10_bg",
    "memory_extraction": "stage_10_bg",
    "summarize_conversation_memory": "stage_10_bg",
}

STAGE_ID_TO_ROOT_NAME = {
    "stage_1_init": "initialization",
    "stage_2_intent": "intent_classification",
    "stage_3_cache": "cache_check",
    "stage_4_tool": "tool_routing",
    "stage_5_rag": "rag_retrieval",
    "stage_6_prompt": "context_building",
    "stage_7_llm": "llm_generation",
    "stage_8_emotion": "emotion_update",
    "stage_9_persist": "persistence",
    "stage_10_bg": "background_tasks",
}


class PipelineTracker:
    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.history: List[Dict[str, Any]] = []
        self.listeners: Set[Callable[[Dict[str, Any]], Any]] = set()
        self._subscriber_task: Any = None
        self.instance_id: str = str(uuid.uuid4())

    def _notify_listeners(self, event: Dict[str, Any], broadcast_redis: bool = True):
        # 1. Notify local in-process listeners
        for listener in list(self.listeners):
            try:
                listener(event)
            except Exception:
                pass

        # 2. Broadcast to Redis Pub/Sub across multi-worker processes
        if broadcast_redis:
            try:
                event["_publisher_id"] = self.instance_id
                loop = asyncio.get_running_loop()
                loop.create_task(self._publish_redis_event(event))
            except RuntimeError:
                pass  # Event loop not running

    async def _publish_redis_event(self, event: Dict[str, Any]):
        try:
            from app.infrastructure.cache.redis.redis_service import get_redis_client
            redis = get_redis_client()
            await redis.publish(REDIS_PUBSUB_CHANNEL, json.dumps(event, default=str))
            await redis.close()
        except Exception:
            pass

    async def start_redis_subscriber(self):
        """Starts a background Redis subscriber loop for multi-worker event sync."""
        if self._subscriber_task and not self._subscriber_task.done():
            return
        
        try:
            from app.infrastructure.cache.redis.redis_service import get_redis_client
            redis = get_redis_client()
            pubsub = redis.pubsub()
            await pubsub.subscribe(REDIS_PUBSUB_CHANNEL)
            log.info("PipelineTracker Redis Pub/Sub subscriber started ✓")
            
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    try:
                        event = json.loads(message["data"])
                        # Filter out self-published messages to prevent duplicate notifications
                        if event.get("_publisher_id") == self.instance_id:
                            continue
                        # Notify local listeners without re-publishing to Redis
                        self._notify_listeners(event, broadcast_redis=False)
                    except Exception:
                        pass
        except Exception as e:
            log.warning("Failed to start PipelineTracker Redis subscriber", error=str(e))

    def start_trace(self, user_id: str, message: str, pipeline: str, source: str = "web", username: str = None, channel_name: str = None, guild_name: str = None) -> str:
        trace_id = str(uuid.uuid4())
        trace = {
            "id": trace_id,
            "user_id": user_id,
            "username": username,
            "channel_name": channel_name,
            "guild_name": guild_name,
            "message": message,
            "source": source or "web",
            "pipeline": pipeline,
            "timestamp": datetime.datetime.now().isoformat(),
            "start_time": time.time(),
            "status": "processing",
            "steps": [],
            "total_tokens": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_reasoning_tokens": 0,
            "response": "",
            "latency_ms": 0.0,
            "error": None,
            "loop_thinking_activated": False
        }
        current_trace_var.set(trace)
        return trace_id

    def get_current_trace(self) -> Dict[str, Any]:
        return current_trace_var.get()

    def add_step(
        self,
        name: str,
        data: Dict[str, Any],
        stage_id: Optional[str] = None,
        parent_step_id: Optional[str] = None,
        depth: Optional[int] = None,
        category: Optional[str] = None,
        duration_ms: Optional[float] = None,
        status: Optional[str] = None,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        tokens: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any
    ):
        try:
            trace = current_trace_var.get()
            if not trace:
                return None
            
            # Resolve stage_id
            resolved_stage_id = stage_id or data.get("stage_id")
            if not resolved_stage_id:
                if name.startswith("thinking_loop_"):
                    resolved_stage_id = "stage_5_rag"
                else:
                    resolved_stage_id = STEP_NAME_TO_STAGE_ID.get(name, "stage_unknown")

            # Resolve depth
            resolved_depth = depth if depth is not None else data.get("depth")
            if resolved_depth is None:
                if name == "web_search" and (data.get("source", "").startswith("thinking_loop_cycle_") or data.get("source") == "thinking_loop"):
                    resolved_depth = 2
                elif name in (
                    "information_alignment_check", "alignment_assessment", "query_rewrite",
                    "thinking_loop_auto_satisfy", "web_search", "memory_extraction",
                    "summarize_conversation_memory", "unified_auto_summarize", "auto_summarize"
                ) or name.startswith("thinking_loop_cycle_"):
                    resolved_depth = 1
                else:
                    resolved_depth = 0

            # Resolve category
            resolved_category = category or data.get("category")
            if not resolved_category:
                if resolved_depth == 0 and name in (
                    "initialization", "init_stage", "intent_classification", "intent_stage",
                    "cache_check", "cache_lookup", "cache_stage", "tool_routing", "tool_routing_stage",
                    "rag_retrieval", "rag_stage", "context_building", "context_builder",
                    "llm_generation", "emotion_update", "persistence", "persistence_stage",
                    "background_tasks", "background_stage"
                ):
                    resolved_category = StepCategory.STAGE_ROOT.value
                elif "llm" in name or name.startswith("thinking_loop_cycle_"):
                    resolved_category = StepCategory.LLM_INFERENCE.value
                elif "retrieval" in name or "search" in name:
                    resolved_category = StepCategory.RETRIEVAL.value
                elif "tool" in name:
                    resolved_category = StepCategory.TOOL_EXECUTION.value
                elif "alignment" in name or "intent" in name or "check" in name or "decision" in name:
                    resolved_category = StepCategory.DECISION.value
                else:
                    resolved_category = StepCategory.DATA_PROCESSING.value
            elif isinstance(resolved_category, StepCategory):
                resolved_category = resolved_category.value

            # Resolve timing, status, titles
            resolved_duration_ms = duration_ms if duration_ms is not None else data.get("duration_ms", 0.0)
            resolved_status = status or data.get("status", "success")
            resolved_title = title or data.get("title")
            resolved_subtitle = subtitle or data.get("subtitle")
            resolved_parent_step_id = parent_step_id or data.get("parent_step_id")
            resolved_tokens = tokens or data.get("tokens") or data.get("token_breakdown")

            step_index = len(trace["steps"]) + 1
            step_id = data.get("id") or f"step_{step_index}_{name}"

            step = {
                "id": step_id,
                "stage_id": resolved_stage_id,
                "parent_step_id": resolved_parent_step_id,
                "depth": resolved_depth,
                "name": name,
                "category": resolved_category,
                "title": resolved_title,
                "subtitle": resolved_subtitle,
                "status": resolved_status,
                "duration_ms": resolved_duration_ms,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "tokens": resolved_tokens,
                "data": data
            }
            trace["steps"].append(step)
            
            # Auto-aggregate tokens across LLM / token-bearing steps
            tb = resolved_tokens or data.get("token_breakdown")
            if tb:
                in_tok = tb.get("total_input") or data.get("input_tokens", 0)
                out_tok = tb.get("total_output") or data.get("output_tokens", 0)
                reason_tok = tb.get("reasoning_cot") or data.get("reasoning_tokens", 0)
                tot_tok = tb.get("total_tokens") or (in_tok + out_tok + reason_tok)
                
                trace["total_input_tokens"] = trace.get("total_input_tokens", 0) + in_tok
                trace["total_output_tokens"] = trace.get("total_output_tokens", 0) + out_tok
                trace["total_reasoning_tokens"] = trace.get("total_reasoning_tokens", 0) + reason_tok
                trace["total_tokens"] = trace.get("total_tokens", 0) + tot_tok
            elif name == "llm_generation" and "data" in step:
                in_tok = step["data"].get("input_tokens", 0)
                out_tok = step["data"].get("output_tokens", 0)
                reason_tok = step["data"].get("reasoning_tokens", 0)
                
                trace["total_input_tokens"] = trace.get("total_input_tokens", 0) + in_tok
                trace["total_output_tokens"] = trace.get("total_output_tokens", 0) + out_tok
                trace["total_reasoning_tokens"] = trace.get("total_reasoning_tokens", 0) + reason_tok
                trace["total_tokens"] = trace.get("total_tokens", 0) + (in_tok + out_tok + reason_tok)

            # Auto-flag loop thinking activation
            if name.startswith("thinking_loop_cycle_") or name == "thinking_loop":
                trace["loop_thinking_activated"] = True

            self._notify_listeners({
                "type": "step",
                "trace_id": trace.get("id"),
                "step": step,
                "loop_thinking_activated": trace.get("loop_thinking_activated", False),
            })
            return step
        except Exception:
            return None  # Fail-safe to avoid impacting the main thread

    def start_stage(
        self,
        stage_id: str,
        name: Optional[str] = None,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Helper to emit a top-level canonical Stage Root node (depth 0)."""
        actual_name = name or STAGE_ID_TO_ROOT_NAME.get(stage_id, stage_id)
        payload = data or {}
        return self.add_step(
            name=actual_name,
            data=payload,
            stage_id=stage_id,
            depth=0,
            category=StepCategory.STAGE_ROOT.value,
            title=title,
            subtitle=subtitle
        )

    def add_sub_step(
        self,
        name: str,
        data: Dict[str, Any],
        parent_step_id: Optional[str] = None,
        depth: int = 1,
        stage_id: Optional[str] = None,
        category: Optional[str] = None,
        title: Optional[str] = None,
        subtitle: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Helper to emit a hierarchical child / sub-action node."""
        return self.add_step(
            name=name,
            data=data,
            stage_id=stage_id,
            parent_step_id=parent_step_id,
            depth=depth,
            category=category,
            title=title,
            subtitle=subtitle
        )


    def end_trace(self, response_text: str = "", emotions: Dict[str, float] = None, status: str = "success", error: str = None) -> Dict[str, Any]:
        try:
            trace = current_trace_var.get()
            if not trace:
                return {}

            trace["status"] = status
            trace["response"] = response_text
            trace["emotions"] = emotions
            trace["error"] = error
            
            # Compute latency
            start_time = trace.pop("start_time", None)
            if start_time:
                trace["latency_ms"] = round((time.time() - start_time) * 1000, 2)
            else:
                trace["latency_ms"] = 0.0
                
            # Add to local history (limit size)
            self.history.append(trace)
            if len(self.history) > self.max_history:
                self.history.pop(0)

            # Persist to Redis history list asynchronously
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._push_history_redis(trace))
            except RuntimeError:
                pass

            # Notify listeners (e.g. SSE/WebSocket subscribers)
            self._notify_listeners({
                "type": "complete",
                "trace_id": trace.get("id"),
                "trace": trace,
            })

            # Clear context variable
            current_trace_var.set({})
            return trace
        except Exception:
            return {}

    async def _push_history_redis(self, trace: Dict[str, Any]):
        try:
            from app.infrastructure.cache.redis.redis_service import get_redis_client
            redis = get_redis_client()
            await redis.lpush(REDIS_HISTORY_KEY, json.dumps(trace, default=str))
            await redis.ltrim(REDIS_HISTORY_KEY, 0, self.max_history - 1)
            await redis.close()
        except Exception:
            pass

    def get_traces(self) -> List[Dict[str, Any]]:
        return self.history

    def get_loop_thinking_activated(self) -> bool:
        """Returns whether loop thinking was activated during the current trace."""
        trace = current_trace_var.get()
        return bool(trace.get("loop_thinking_activated", False))

    def register_listener(self, listener: Callable[[Dict[str, Any]], Any]):
        self.listeners.add(listener)

    def unregister_listener(self, listener: Callable[[Dict[str, Any]], Any]):
        self.listeners.discard(listener)

# Global singleton
pipeline_tracker = PipelineTracker()
