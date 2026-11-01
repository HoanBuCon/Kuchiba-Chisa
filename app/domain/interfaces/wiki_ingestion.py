"""Ports for the wiki sync: the MediaWiki source, the inventory store and the bronze store."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.ingestion.pages import PageState, WikiPageInfo


class WikiSourceError(RuntimeError):
    """The wiki could not be read safely (throttled, challenged, malformed, or over budget)."""


@dataclass(frozen=True)
class ParsedPage:
    """One `action=parse` response kept verbatim as bronze (ING-002, ING-018)."""

    page_id: int
    title: str
    revid: int
    html: str
    categories: tuple[str, ...]
    templates: tuple[str, ...]
    sections: tuple[dict, ...]
    properties: dict[str, str]
    url: str
    license: str
    fetched_at: datetime


class IWikiSyncSource(Protocol):
    async def list_page_ids(self) -> dict[int, str]: ...

    async def page_infos(self, page_ids: Sequence[int]) -> list[WikiPageInfo]: ...

    async def page_details(
        self, page_ids: Sequence[int]
    ) -> dict[int, tuple[tuple[str, ...], tuple[str, ...]]]:
        """Return (categories, templates) per page; only asked for new or re-rendered pages."""
        ...

    async def subcategories(self, parent: str) -> list[str]: ...

    async def changed_templates(self, since: datetime) -> frozenset[str]: ...

    async def deleted_titles(self, since: datetime) -> frozenset[str]: ...

    async def parse(self, page_id: int) -> ParsedPage: ...


class IBronzeStore(Protocol):
    def save(self, page: ParsedPage) -> str:
        """Persist the page and return its store-relative key."""
        ...

    def load(self, key: str) -> ParsedPage: ...


@dataclass(frozen=True)
class SyncRun:
    """One reconcile-and-fetch run; only successful runs move the change-feed cursor."""

    run_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    stats: dict[str, int]


class IWikiInventory(Protocol):
    async def load(self) -> dict[int, PageState]: ...

    async def upsert(self, states: Iterable[PageState]) -> None: ...

    async def last_successful_run(self) -> SyncRun | None: ...

    async def record_run(self, run: SyncRun) -> None: ...

    def exclusive_run(self) -> AbstractAsyncContextManager[bool]:
        """Hold the single-writer sync lock for the block; yields False when another run owns it."""
        ...
