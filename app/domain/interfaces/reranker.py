"""Port for a trusted cross-encoder reranking provider."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol


class RerankerUnavailableError(RuntimeError):
    """The configured reranker cannot produce a trustworthy score in time."""


class RerankerDataBoundary(StrEnum):
    """Where a reranker processes the supplied query and evidence text."""

    LOCAL = "local"
    REMOTE = "remote"


class ICrossEncoderReranker(Protocol):
    """Score a query and ordered candidate texts without changing their content."""

    @property
    def data_boundary(self) -> RerankerDataBoundary:
        """State whether this adapter sends evidence outside the deployment boundary."""
        ...

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """Return one finite score per supplied document, in the same order."""
        ...
