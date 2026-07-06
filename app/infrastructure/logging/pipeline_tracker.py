import time
import uuid
import datetime
import contextvars
from typing import Any, Dict, List, Set, Callable

# Request-scoped trace variable
current_trace_var: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar("current_trace_var", default={})

class PipelineTracker:
    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.history: List[Dict[str, Any]] = []
        self.listeners: Set[Callable[[Dict[str, Any]], Any]] = set()

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
                
            # Add to history (limit size)
            self.history.append(trace)
            if len(self.history) > self.max_history:
                self.history.pop(0)

            # Notify listeners (e.g. WebSockets)
            for listener in list(self.listeners):
                try:
                    listener(trace)
                except Exception:
                    pass

            # Clear context variable
            current_trace_var.set({})
            return trace
        except Exception:
            return {}

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
