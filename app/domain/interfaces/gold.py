"""Port for the gold stage: versioned corpus artifacts with a manifest (design L3)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Protocol

from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.knowledge import KnowledgeBase, StructuredPage


class IKnowledgeStore(Protocol):
    async def publish(self, version: str, knowledge: KnowledgeBase) -> dict[str, int]:
        """Replace this version's rows atomically and return the row counts."""
        ...

    async def count(self, version: str) -> dict[str, int]: ...


class IStructuredSource(Protocol):
    async def structured_pages(
        self, page_ids: Sequence[int]
    ) -> dict[int, tuple[tuple[dict[str, str], ...], tuple[str, ...]]]:
        """Page ID -> (flattened infoboxes, redirect titles)."""
        ...


class IStructuredStore(Protocol):
    def load(self) -> dict[int, StructuredPage]: ...

    def save(self, pages: Mapping[int, StructuredPage]) -> None: ...


class IGoldStore(Protocol):
    def next_version(self, day: date) -> str:
        """Return the next free `YYYY.MM.DD-N` corpus version."""
        ...

    def latest_version(self) -> str | None: ...

    def read_chunks(self, version: str) -> list[Chunk]: ...

    def read_knowledge(self, version: str) -> KnowledgeBase: ...

    def read_manifest(self, version: str) -> dict[str, Any]: ...

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
