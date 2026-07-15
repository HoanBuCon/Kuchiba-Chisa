from typing import Any, Dict, Protocol

class IPipelineTracker(Protocol):
    def add_step(self, name: str, data: Dict[str, Any]) -> None:
        pass
