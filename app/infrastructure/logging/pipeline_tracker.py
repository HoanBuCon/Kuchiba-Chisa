import asyncio
import contextvars
import datetime
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

from app.config.settings import settings
from app.infrastructure.logging.telemetry_redaction import redact_telemetry_payload
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

# Request-scoped trace variable
current_trace_var: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "current_trace_var",
    default=None,
)

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
    "guild_memory_retrieval": "stage_5_rag",
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
    "summarize_channel_topic": "stage_10_bg",
    "community_topic_summarize": "stage_10_bg",
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
        self.history: list[dict[str, Any]] = []
        self.listeners: set[Callable[[dict[str, Any]], Any]] = set()
        self._pending_tasks: set[asyncio.Task[Any]] = set()
        self._subscriber_task: Any = None
        self._redis_broadcast_ready = False
        self.instance_id: str = str(uuid.uuid4())

    def _notify_listeners(self, event: dict[str, Any], broadcast_redis: bool = True):
        # 1. Notify local in-process listeners
        for listener in list(self.listeners):
            try:
                listener(event)
            except Exception:
                pass

        # 2. Broadcast to Redis Pub/Sub across multi-worker processes
        if broadcast_redis and self._redis_broadcast_ready:
            try:
                event["_publisher_id"] = self.instance_id
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    task = loop.create_task(self._publish_redis_event(event))
                    self._track_task(task)
            except RuntimeError:
                pass  # Event loop not running

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        """Track a best-effort observability task under its owning event loop."""
        self._discard_completed_or_closed_tasks()
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    def _discard_completed_or_closed_tasks(self) -> None:
        """Remove tasks that cannot produce another observable result."""
        for task in tuple(self._pending_tasks):
            if task.done() or task.get_loop().is_closed():
                self._pending_tasks.discard(task)

    async def flush(self):
        """Awaits all pending background tasks (e.g. before loop shutdown in tests)."""
        self._discard_completed_or_closed_tasks()
        current_loop = asyncio.get_running_loop()
        tasks = [
            task
            for task in self._pending_tasks
            if task.get_loop() is current_loop and not task.done()
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _publish_redis_event(self, event: dict[str, Any]):
        try:
            from app.infrastructure.cache.redis.redis_service import get_redis_client
            redis = get_redis_client()
            await redis.publish(REDIS_PUBSUB_CHANNEL, json.dumps(event, default=str))
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
            self._redis_broadcast_ready = True
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
            self._redis_broadcast_ready = False
            log.warning("Failed to start PipelineTracker Redis subscriber", error=str(e))

    def start_trace(
        self,
        user_id: str,
        message: str,
        pipeline: str,
        source: str | None = "web",
        username: str | None = None,
        channel_name: str | None = None,
        guild_name: str | None = None,
    ) -> str:
        trace_id = str(uuid.uuid4())
        # This is an observability record, never a conversation/content store.
        # Arguments containing identity or user content remain outside the trace.
        trace: dict[str, Any] = {
            "id": trace_id,
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
            "latency_ms": 0.0,
            "loop_thinking_activated": False,
            "input_char_count": len(message),
            "has_principal": bool(user_id),
            "has_tenant_context": bool(guild_name),
            "has_channel_context": bool(channel_name),
            "has_display_name": bool(username),
        }
        current_trace_var.set(trace)
        return trace_id

    def get_current_trace(self) -> dict[str, Any]:
        return current_trace_var.get() or {}

    def add_step(
        self,
        name: str,
        data: dict[str, Any],
        stage_id: str | None = None,
        parent_step_id: str | None = None,
        depth: int | None = None,
        category: str | None = None,
        duration_ms: float | None = None,
        status: str | None = None,
        title: str | None = None,
        subtitle: str | None = None,
        tokens: dict[str, Any] | None = None,
        trace_id: str | None = None,
        *args: Any,
        **kwargs: Any
    ):
        try:
            trace = None
            if trace_id:
                for t in self.history:
                    if t.get("id") == trace_id:
                        trace = t
                        break
            if not trace:
                trace = current_trace_var.get() or {}
            if not trace:
                return None
            
            telemetry_data = redact_telemetry_payload(data)

            # Resolve stage_id from the trusted method argument or a known stage map.
            resolved_stage_id = stage_id or telemetry_data.get("stage_id")
            if not resolved_stage_id:
                if name.startswith("thinking_loop_"):
                    resolved_stage_id = "stage_5_rag"
                else:
                    resolved_stage_id = STEP_NAME_TO_STAGE_ID.get(name, "stage_unknown")

            # Resolve depth
            resolved_depth = depth if depth is not None else telemetry_data.get("depth")
            if resolved_depth is None:
                if name == "web_search" and (
                    telemetry_data.get("source", "").startswith("thinking_loop_cycle_")
                    or telemetry_data.get("source") == "thinking_loop"
                ):
                    resolved_depth = 2
                elif name in (
                    "information_alignment_check", "alignment_assessment", "query_rewrite",
                    "thinking_loop_auto_satisfy", "web_search", "memory_extraction",
                    "guild_memory_retrieval", "summarize_channel_topic", "community_topic_summarize",
                    "summarize_conversation_memory", "unified_auto_summarize", "auto_summarize"
                ) or name.startswith("thinking_loop_cycle_"):
                    resolved_depth = 1
                else:
                    resolved_depth = 0

            # Resolve category
            resolved_category = category or telemetry_data.get("category")
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
            resolved_duration_ms = (
                duration_ms if duration_ms is not None else telemetry_data.get("duration_ms", 0.0)
            )
            resolved_status = status or telemetry_data.get("status", "success")
            resolved_parent_step_id = parent_step_id
            resolved_tokens = redact_telemetry_payload(
                {
                    "tokens": (
                        tokens
                        or telemetry_data.get("tokens")
                        or telemetry_data.get("token_breakdown")
                    )
                }
            ).get("tokens", {})

            step_index = len(trace["steps"]) + 1
            step_id = f"step_{step_index}_{name}"

            step = {
                "id": step_id,
                "stage_id": resolved_stage_id,
                "parent_step_id": resolved_parent_step_id,
                "depth": resolved_depth,
                "name": name,
                "category": resolved_category,
                "status": resolved_status,
                "duration_ms": resolved_duration_ms,
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                "tokens": resolved_tokens,
                "data": telemetry_data,
            }
            trace["steps"].append(step)
            
            # Auto-aggregate tokens across LLM / token-bearing steps
            tb = resolved_tokens or telemetry_data.get("token_breakdown")
            if tb:
                in_tok = tb.get("total_input") or telemetry_data.get("input_tokens", 0)
                out_tok = tb.get("total_output") or telemetry_data.get("output_tokens", 0)
                reason_tok = tb.get("reasoning_cot") or telemetry_data.get("reasoning_tokens", 0)
                tot_tok = tb.get("total_tokens") or (in_tok + out_tok + reason_tok)
                
                trace["total_input_tokens"] = trace.get("total_input_tokens", 0) + in_tok
                trace["total_output_tokens"] = trace.get("total_output_tokens", 0) + out_tok
                trace["total_reasoning_tokens"] = trace.get("total_reasoning_tokens", 0) + reason_tok
                trace["total_tokens"] = trace.get("total_tokens", 0) + tot_tok
            elif name == "llm_generation" and "data" in step:
                in_tok = telemetry_data.get("input_tokens", 0)
                out_tok = telemetry_data.get("output_tokens", 0)
                reason_tok = telemetry_data.get("reasoning_tokens", 0)
                
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
        name: str | None = None,
        title: str | None = None,
        subtitle: str | None = None,
        data: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
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
        data: dict[str, Any],
        parent_step_id: str | None = None,
        depth: int = 1,
        stage_id: str | None = None,
        category: str | None = None,
        title: str | None = None,
        subtitle: str | None = None
    ) -> dict[str, Any] | None:
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


    def end_trace(
        self,
        response_text: str = "",
        emotions: dict[str, float] | None = None,
        status: str = "success",
        error: str | None = None,
    ) -> dict[str, Any]:
        try:
            trace = current_trace_var.get() or {}
            if not trace:
                return {}

            trace["status"] = status
            trace["response_char_count"] = len(response_text)
            trace["has_emotions"] = bool(emotions)
            trace["emotion_dimension_count"] = len(emotions or {})
            trace["has_error"] = error is not None
            
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

            # Persist to Redis history only after the tracker has a ready Redis lifecycle.
            if self._redis_broadcast_ready:
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        task = loop.create_task(self._push_history_redis(trace))
                        self._track_task(task)
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

    async def _push_history_redis(self, trace: dict[str, Any]):
        try:
            from app.infrastructure.cache.redis.redis_service import get_redis_client
            redis = get_redis_client()
            history_entry = json.dumps(trace, default=str)
            await cast(Awaitable[int], redis.lpush(REDIS_HISTORY_KEY, history_entry))
            await cast(Awaitable[str], redis.ltrim(REDIS_HISTORY_KEY, 0, self.max_history - 1))
            await cast(
                Awaitable[bool],
                redis.expire(REDIS_HISTORY_KEY, settings.PIPELINE_TRACE_TTL_SECONDS),
            )
        except Exception:
            pass

    def get_traces(self) -> list[dict[str, Any]]:
        return self.history

    def get_loop_thinking_activated(self) -> bool:
        """Returns whether loop thinking was activated during the current trace."""
        trace = current_trace_var.get() or {}
        return bool(trace.get("loop_thinking_activated", False))

    def register_listener(self, listener: Callable[[dict[str, Any]], Any]):
        self.listeners.add(listener)

    def unregister_listener(self, listener: Callable[[dict[str, Any]], Any]):
        self.listeners.discard(listener)

# Global singleton
pipeline_tracker = PipelineTracker()
