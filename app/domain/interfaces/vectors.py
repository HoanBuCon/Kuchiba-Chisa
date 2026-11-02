"""Ports for the vector stage: passage embedding, the vector cache and the staging index."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class StagingError(RuntimeError):
    """The staging collection is missing a channel or does not match the manifest (D11)."""


class IPassageEmbedder(Protocol):
    @property
    def model_id(self) -> str:
        """Model and revision; part of the cache key, since vectors never mix across models."""
        ...

    @property
    def dimension(self) -> int: ...

    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...


class IVectorCache(Protocol):
    def load(self, keys: Iterable[str]) -> dict[str, list[float]]: ...

    def save(self, vectors: Mapping[str, Sequence[float]]) -> None: ...


@dataclass(frozen=True)
class StagingPoint:
    point_id: str
    vector: Sequence[float]
    # Tokenised by the index itself into the lexical channel.
    lexical_text: str
    payload: dict[str, Any]


class IStagingIndex(Protocol):
    async def create(self, collection: str, dimension: int, *, replace: bool) -> None: ...

    async def upsert(self, collection: str, points: Sequence[StagingPoint]) -> None: ...

    async def verify(self, collection: str, expected_points: int) -> None:
        """Raise StagingError unless every channel exists and the point count matches."""
        ...
