from abc import ABC, abstractmethod
from typing import Any, List, Dict, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.interfaces.embedding_provider import IEmbeddingProvider

class IThinkingAgent(ABC):
    @abstractmethod
    async def run(
        self,
        session: AsyncSession,
        user_id: str,
        user_message: str,
        history: List[Dict[str, str]],
        initial_context: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        web_search_tool: Any,
        initial_search_query: Optional[str] = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        pass
