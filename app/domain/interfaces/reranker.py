"""Port for a trusted cross-encoder reranking provider."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class RerankerUnavailableError(RuntimeError):
    """The configured reranker cannot produce a trustworthy score in time."""


class ICrossEncoderReranker(Protocol):
    """Score a query and ordered candidate texts without changing their content."""

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """Return one finite score per supplied document, in the same order."""
        ...
