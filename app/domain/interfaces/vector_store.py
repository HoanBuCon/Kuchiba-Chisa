from abc import ABC, abstractmethod
from typing import Any, List, Dict, Optional, Union

class IVectorStore(ABC):
    """
    Interface for Vector Storage operations.
    Abstracts away specific vector DB implementation like Qdrant or Pinecone.
    """
    @abstractmethod
    async def upsert_memory(
        self,
        collection: str,
        point_id: str,
        vector: List[float],
        payload: Any,
    ) -> None:
        pass

    @abstractmethod
    async def search_by_user(
        self,
        collection: str,
        query_vector: List[float],
        user_id: str,
        limit: int = 10,
        score_threshold: float = 0.65,
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def search_lore(
        self,
        collection: str,
        query_vector: List[float],
        limit: int = 4,
        score_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def upsert_lore(
        self,
        collection: str,
        point_id: str,
        vector: List[float],
        text_content: str,
        section: str = "general",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        pass

    @abstractmethod
    async def delete_points(self, collection: str, ids: List[Union[str, int]]) -> None:
        pass
