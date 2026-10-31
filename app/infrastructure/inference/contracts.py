"""Embedding contracts shared by the inference service and its clients; no model runtime."""

from __future__ import annotations

from dataclasses import dataclass

E5_PREFIXES = ("query: ", "passage: ")


class EmbeddingGenerationError(Exception):
    """The embedding backend could not produce vectors."""


@dataclass(frozen=True)
class EmbeddingModelInfo:
    model: str
    dimension: int
    revision: str


def with_e5_prefix(text: str, prefix: str) -> str:
    """Apply the e5 asymmetric prefix unless the caller already chose one (KNW-005)."""
    return text if text.startswith(E5_PREFIXES) else f"{prefix}{text}"
