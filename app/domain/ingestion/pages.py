"""What the wiki reports about a page and what the inventory remembers about it (ING-013)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum


class PageStatus(StrEnum):
    ACTIVE = "active"
    # Absent from one reconciliation; becomes a tombstone only if still absent next run.
    PENDING_DELETE = "pending_delete"
    DELETED = "deleted"


@dataclass(frozen=True)
class WikiPageInfo:
    """One `allpages` + `prop=info` row; `touched` moves when templates re-render the page."""

    page_id: int
    title: str
    last_revid: int
    touched: datetime
    revision_timestamp: datetime | None = None
    categories: tuple[str, ...] = ()
    templates: tuple[str, ...] = ()


@dataclass(frozen=True)
class PageState:
    """Inventory row keyed by page_id, which MediaWiki keeps stable across renames."""

    page_id: int
    title: str
    last_revid: int
    touched: datetime
    family: str | None = None
    tier: str | None = None
    templates: tuple[str, ...] = ()
    status: PageStatus = PageStatus.ACTIVE
    fetched_revid: int | None = None
    fetched_touched: datetime | None = None
    fetched_at: datetime | None = None
    bronze_key: str | None = None
    aliases: tuple[str, ...] = field(default=())

    @property
    def in_text_scope(self) -> bool:
        return self.status is PageStatus.ACTIVE and self.family is not None

    def observe(self, info: WikiPageInfo) -> PageState:
        """Apply a fresh wiki observation; a new title keeps the old one as an alias."""
        aliases = self.aliases
        if info.title != self.title and self.title not in aliases:
            aliases = (*aliases, self.title)
        return replace(
            self,
            title=info.title,
            last_revid=info.last_revid,
            touched=info.touched,
            templates=info.templates or self.templates,
            status=PageStatus.ACTIVE,
            aliases=aliases,
        )
