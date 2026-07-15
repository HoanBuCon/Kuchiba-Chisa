import abc
from abc import ABC
from typing import Any, Dict, List


from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.interfaces.embedding_provider import IEmbeddingProvider


class BaseAgentTool(ABC):
    """
    Base class representing a system action tool (Agent Tool)
    in the production pipeline.
    """
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier of the tool."""
        pass

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Human-readable description of the tool's purpose."""
        pass

    @property
    @abc.abstractmethod
    def anchors(self) -> List[str]:
        """Anchor examples for Semantic Routing."""
        pass

    @abc.abstractmethod
    async def execute(
        self,
        user_id: str,
        user_message: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute the tool logic."""
        pass
