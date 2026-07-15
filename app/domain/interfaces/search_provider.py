from typing import Protocol, List, Optional
from pydantic import BaseModel

class SearchResult(BaseModel):
    snippets: List[str]
    urls: List[str]
    provider: str

class ISearchProvider(Protocol):
    """
    Interface for a web search strategy.
    """
    @property
    def name(self) -> str:
        """Name of the search provider."""
        ...

    async def search(self, query: str) -> Optional[SearchResult]:
        """
        Executes a web search for the given query.
        Returns a SearchResult if successful and snippets were found, None otherwise.
        """
        ...
