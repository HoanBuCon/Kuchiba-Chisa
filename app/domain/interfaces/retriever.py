from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Dict
from app.domain.services.rag.base import ScoredMemory

class ILoreRetriever(ABC):
    @abstractmethod
    async def retrieve_lore_standard(
        self,
        query_vector: List[float],
        query_text: str = "",
        top_k: int = 8,
        score_threshold: float = 0.3,
    ) -> List[Tuple[str, float]]:
        pass

    @abstractmethod
    async def retrieve_lore_parent_child(
        self,
        collection: str,
        query_vector: List[float],
        query_text: str = "",
        top_k: int = 5,
        score_threshold: float = 0.35,
    ) -> List[str]:
        pass

class IMemoryRetriever(ABC):
    @abstractmethod
    async def retrieve_memories(
        self,
        collection: str,
        query_vector: List[float],
        user_id: str,
        current_emotion: Optional[Dict[str, float]] = None,
        limit: int = 15,
        top_k: int = 5
    ) -> List[ScoredMemory]:
        pass
