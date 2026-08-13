import json
import time
import uuid
import datetime
import asyncio
import contextvars
from typing import Any, Dict, List, Set, Callable

from app.shared.utils.logger import get_logger

log = get_logger(__name__)

# Request-scoped trace variable
current_trace_var: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar("current_trace_var", default={})

REDIS_PUBSUB_CHANNEL = "chisa:pipeline_events"
REDIS_HISTORY_KEY = "chisa:pipeline_history"


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
            "response": "",
            "latency_ms": 0.0,
            "error": None,
            "loop_thinking_activated": False
        }
        current_trace_var.set(trace)
        return trace_id

    def get_current_trace(self) -> Dict[str, Any]:
        return current_trace_var.get()

    def add_step(self, name: str, data: Dict[str, Any]):
        try:
            trace = current_trace_var.get()
            if not trace:
                return
            
            step = {
                "name": name,
                "timestamp": datetime.datetime.now().isoformat(),
                "data": data
            }
            trace["steps"].append(step)
            
            # Auto-aggregate tokens if this is an LLM step
            if name == "llm_generation" and "data" in step:
                tokens = step["data"].get("input_tokens", 0) + step["data"].get("output_tokens", 0)
                trace["total_tokens"] += tokens

            # Auto-flag loop thinking activation
            if name.startswith("thinking_loop_cycle_"):
                trace["loop_thinking_activated"] = True

            self._notify_listeners({
                "type": "step",
                "trace_id": trace.get("id"),
                "step": step,
                "loop_thinking_activated": trace.get("loop_thinking_activated", False),
            })
        except Exception:
            pass  # Fail-safe to avoid impacting the main thread

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
