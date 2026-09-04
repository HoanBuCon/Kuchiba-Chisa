from typing import Any, Dict, Optional, Protocol

class IPipelineTracker(Protocol):
    def get_current_trace(self) -> dict[str, Any]:
        ...

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
    ) -> Any:
        pass

