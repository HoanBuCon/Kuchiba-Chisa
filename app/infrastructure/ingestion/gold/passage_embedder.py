"""Offline passage embedding for the vector stage, using the inference service's own adapter."""

from __future__ import annotations

from collections.abc import Sequence

from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter

PASSAGE_PREFIX = "passage: "


class FastEmbedPassageEmbedder:
    def __init__(self, adapter: FastEmbedAdapter) -> None:
        self._adapter = adapter

    @property
    def model_id(self) -> str:
        return f"{self._adapter.model_name}@{self._adapter.version}"

    @property
    def dimension(self) -> int:
        return self._adapter.dimension

    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._adapter.embed_batch(list(texts), prefix=PASSAGE_PREFIX)
