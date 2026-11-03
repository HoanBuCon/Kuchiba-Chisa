"""Structured channel for the whole wiki, independent of the text tiers (ING-014)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.ingestion.corpus_safety import CorpusSafetyPolicy
from app.domain.ingestion.knowledge import StructuredPage
from app.domain.interfaces.gold import IStructuredSource, IStructuredStore
from app.domain.interfaces.wiki_ingestion import IWikiInventory

BATCH_SIZE = 50


@dataclass(frozen=True)
class StructuredReport:
    pages: int
    fetched: int
    with_infobox: int
    # Page -> safety findings; the page keeps no structured data until approved or changed.
    blocked: dict[int, tuple[str, ...]] = field(default_factory=dict)


class StructuredStage:
    def __init__(
        self,
        inventory: IWikiInventory,
        source: IStructuredSource,
        store: IStructuredStore,
        safety: CorpusSafetyPolicy | None = None,
    ) -> None:
        self._safety = safety or CorpusSafetyPolicy()
        self._inventory = inventory
        self._source = source
        self._store = store

    async def run(self) -> StructuredReport:
        states = await self._inventory.load()
        wanted = {
            page_id: state.last_revid
            for page_id, state in states.items()
            if state.is_active and not state.in_text_scope
        }
        stored = self._store.load()
        pages = {pid: page for pid, page in stored.items() if pid in wanted}
        stale = sorted(
            pid for pid, revid in wanted.items() if pid not in pages or pages[pid].revid != revid
        )
        blocked: dict[int, tuple[str, ...]] = {}
        try:
            for start in range(0, len(stale), BATCH_SIZE):
                batch = stale[start : start + BATCH_SIZE]
                found = await self._source.structured_pages(batch)
                for page_id in batch:
                    raw_boxes, redirects = found.get(page_id, ((), ()))
                    boxes, findings = self._safety.vet_infoboxes(page_id, raw_boxes)
                    if findings:
                        blocked[page_id] = findings
                    pages[page_id] = StructuredPage(
                        wanted[page_id], () if findings else boxes, redirects
                    )
        finally:
            # A wiki failure keeps the batches already paid for; the next run continues.
            self._store.save(pages)
        return StructuredReport(
            pages=len(pages),
            fetched=len(stale),
            with_infobox=sum(bool(page.infoboxes) for page in pages.values()),
            blocked=blocked,
        )
