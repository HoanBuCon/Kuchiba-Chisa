"""Ports for the silver stage: the cleaner, the silver store and the per-page check ledger."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.ingestion.documents import CanonicalDocument
from app.domain.ingestion.page_checks import Verdict
from app.domain.interfaces.wiki_ingestion import ParsedPage


class CleaningError(RuntimeError):
    """A bronze page could not be parsed into silver."""


class IPageCleaner(Protocol):
    @property
    def version(self) -> str:
        """Cleaner code and rules version; any change re-cleans every page."""
        ...

    def clean(self, page: ParsedPage, family: str | None) -> CanonicalDocument: ...


class ISilverStore(Protocol):
    def path_for(self, page_id: int, key: str) -> str: ...

    def save(self, key: str, document: CanonicalDocument) -> str:
        """Persist the document under `key` and return its store-relative path."""
        ...

    def load(self, path: str) -> CanonicalDocument: ...


@dataclass(frozen=True)
class SilverEntry:
    """Latest check of one page and the last-known-good silver it falls back to (ING-006)."""

    page_id: int
    silver_path: str
    output_hash: str
    verdict: Verdict
    reasons: tuple[str, ...]
    unchanged_runs: int
    checked_at: datetime
    # Silver the corpus uses: the latest output once accepted, otherwise the previous good one.
    lkg_path: str | None = None


class ISilverLedger(Protocol):
    async def load(self) -> dict[int, SilverEntry]: ...

    async def upsert(self, entries: Iterable[SilverEntry]) -> None: ...
