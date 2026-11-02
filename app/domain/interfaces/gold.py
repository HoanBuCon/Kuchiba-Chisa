"""Port for the gold stage: versioned corpus artifacts with a manifest (design L3)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Protocol

from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.knowledge import KnowledgeBase


class IGoldStore(Protocol):
    def next_version(self, day: date) -> str:
        """Return the next free `YYYY.MM.DD-N` corpus version."""
        ...

    def write(
        self,
        version: str,
        chunks: Sequence[Chunk],
        duplicate_of: Mapping[str, int],
        knowledge: KnowledgeBase,
        manifest: Mapping[str, Any],
    ) -> str:
        """Publish the version atomically and return its store-relative directory."""
        ...
