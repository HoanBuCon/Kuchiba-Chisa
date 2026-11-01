"""Wiki sync: reconcile the inventory with the wiki, then fetch changed pages (ING-002, ING-013)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.ingestion.change_detection import (
    FetchDecision,
    FetchPolicy,
    TemplateClassifier,
    mark_absent,
    plan_fetches,
)
from app.domain.ingestion.families import FamilyCatalog
from app.domain.ingestion.pages import PageState, PageStatus, WikiPageInfo
from app.domain.interfaces.wiki_ingestion import (
    IBronzeStore,
    IWikiInventory,
    IWikiSyncSource,
    SyncRun,
    WikiSourceError,
)

# Change feeds older than this are not trusted to be complete; rolling refresh covers the rest.
RECENT_CHANGES_HORIZON = timedelta(days=30)
# Consecutive parse failures mean the wiki is throttling or broken, not that pages are bad.
MAX_CONSECUTIVE_FAILURES = 5
PERSIST_EVERY = 25


class RunStatus:
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    LOCKED = "locked"


@dataclass(frozen=True)
class SyncRules:
    catalog: FamilyCatalog
    classifier: TemplateClassifier
    policy: FetchPolicy


@dataclass(frozen=True)
class Reconciliation:
    states: dict[int, PageState]
    changed: dict[int, PageState]
    revision_times: dict[int, datetime]
    changed_templates: frozenset[str]
    stats: dict[str, int]


@dataclass(frozen=True)
class SyncReport:
    run_id: str
    status: str
    decisions: tuple[FetchDecision, ...] = ()
    stats: dict[str, int] = field(default_factory=dict)
    failures: tuple[tuple[int, str], ...] = ()


def _needs_details(previous: PageState | None, info: WikiPageInfo) -> bool:
    # `touched` moves on every edit and re-render, the only events that can change categories.
    if previous is None or info.touched != previous.touched:
        return True
    # Rows written before categories were stored have nothing to classify from.
    return not previous.categories


def _classified(state: PageState, catalog: FamilyCatalog) -> PageState:
    rule = catalog.classify(state.title, state.categories)
    return replace(state, family=rule.name if rule else None, tier=rule.tier if rule else None)


def _observe(previous: PageState | None, info: WikiPageInfo, catalog: FamilyCatalog) -> PageState:
    if previous is None:
        state = PageState(
            info.page_id,
            info.title,
            info.last_revid,
            info.touched,
            templates=info.templates,
            categories=info.categories,
        )
    else:
        state = previous.observe(info)
    return _classified(state, catalog)


def _oldest_pending_touch(states: Mapping[int, PageState], now: datetime) -> datetime:
    """Read template changes back to the oldest unfetched re-render so a short budget loses none."""
    horizon = now - RECENT_CHANGES_HORIZON
    pending = [
        s.fetched_touched
        for s in states.values()
        if s.in_text_scope and s.fetched_touched is not None and s.touched > s.fetched_touched
    ]
    return max(horizon, min(pending)) if pending else now


def _with_fetch(state: PageState, revid: int, fetched_at: datetime, key: str) -> PageState:
    return replace(
        state,
        last_revid=max(state.last_revid, revid),
        fetched_revid=revid,
        fetched_touched=state.touched,
        fetched_at=fetched_at,
        bronze_key=key,
    )


class WikiSyncService:
    def __init__(
        self,
        source: IWikiSyncSource,
        inventory: IWikiInventory,
        bronze: IBronzeStore,
        rules: SyncRules,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._source = source
        self._inventory = inventory
        self._bronze = bronze
        self._rules = rules
        self._clock = clock

    async def plan(self) -> SyncReport:
        """Reconcile and rank fetches without writing anything."""
        now = self._clock()
        reconciliation = await self._reconcile(now)
        decisions = self._plan(reconciliation, now)
        stats = {**reconciliation.stats, "planned": len(decisions)}
        return SyncReport(
            run_id="", status=RunStatus.PLANNED, decisions=tuple(decisions), stats=stats
        )

    async def sync(self) -> SyncReport:
        async with self._inventory.exclusive_run() as acquired:
            if not acquired:
                return SyncReport(run_id="", status=RunStatus.LOCKED)
            return await self._locked_sync()

    async def _locked_sync(self) -> SyncReport:
        started = self._clock()
        run_id = f"{started:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
        await self._inventory.record_run(SyncRun(run_id, started, None, RunStatus.RUNNING, {}))
        try:
            reconciliation = await self._reconcile(started)
            await self._inventory.upsert(reconciliation.changed.values())
            decisions = self._plan(reconciliation, started)
            fetched, failures = await self._fetch(decisions, reconciliation.states)
        except WikiSourceError as error:
            await self._finish(run_id, started, RunStatus.FAILED, {"error": 1})
            return SyncReport(run_id, RunStatus.FAILED, failures=((0, str(error)),))
        status = RunStatus.PARTIAL if failures else RunStatus.SUCCEEDED
        stats = {
            **reconciliation.stats,
            "planned": len(decisions),
            "fetched": fetched,
            "failed": len(failures),
        }
        await self._finish(run_id, started, status, stats)
        return SyncReport(run_id, status, tuple(decisions), stats, tuple(failures))

    async def _finish(
        self, run_id: str, started: datetime, status: str, stats: dict[str, int]
    ) -> None:
        await self._inventory.record_run(SyncRun(run_id, started, self._clock(), status, stats))

    def _plan(self, reconciliation: Reconciliation, now: datetime) -> list[FetchDecision]:
        return plan_fetches(
            reconciliation.states.values(),
            revision_times=reconciliation.revision_times,
            changed_templates=reconciliation.changed_templates,
            classifier=self._rules.classifier,
            policy=self._rules.policy,
            now=now,
        )

    async def _reconcile(self, now: datetime) -> Reconciliation:
        stored = await self._inventory.load()
        listed = await self._source.list_page_ids()
        infos = await self._source.page_infos(sorted(listed))
        catalog = await self._expanded_catalog()
        detail_ids = [
            info.page_id for info in infos if _needs_details(stored.get(info.page_id), info)
        ]
        details = await self._source.page_details(detail_ids) if detail_ids else {}

        changed: dict[int, PageState] = {}
        for info in infos:
            categories, templates = details.get(info.page_id, ((), ()))
            observed = replace(info, categories=categories, templates=templates)
            previous = stored.get(info.page_id)
            state = _observe(previous, observed, catalog)
            if state != previous:
                changed[info.page_id] = state

        present = frozenset(info.page_id for info in infos)
        changed.update(
            mark_absent(stored, present, await self._confirmed_deletions(stored, present, now))
        )
        states = {**stored, **changed}
        since = _oldest_pending_touch(states, now)
        changed_templates = (
            await self._source.changed_templates(since) if since < now else frozenset()
        )
        return Reconciliation(
            states=states,
            changed=changed,
            revision_times={i.page_id: i.revision_timestamp for i in infos if i.revision_timestamp},
            changed_templates=changed_templates,
            stats=self._reconcile_stats(stored, states, len(listed), len(detail_ids)),
        )

    async def _expanded_catalog(self) -> FamilyCatalog:
        catalog = self._rules.catalog
        parents = {
            parent
            for rule in catalog.rules
            if rule.tier in catalog.enabled_tiers
            for parent in rule.subcategory_parents
        }
        return catalog.with_subcategories(
            {parent: await self._source.subcategories(parent) for parent in parents}
        )

    async def _confirmed_deletions(
        self, stored: Mapping[int, PageState], present: frozenset[int], now: datetime
    ) -> frozenset[int]:
        pending = {
            pid: s.title for pid, s in stored.items() if s.status is PageStatus.PENDING_DELETE
        }
        candidates = {pid: title for pid, title in pending.items() if pid not in present}
        if not candidates:
            return frozenset()
        deleted = await self._source.deleted_titles(now - RECENT_CHANGES_HORIZON)
        return frozenset(pid for pid, title in candidates.items() if title in deleted)

    @staticmethod
    def _reconcile_stats(
        stored: Mapping[int, PageState], states: Mapping[int, PageState], listed: int, detailed: int
    ) -> dict[str, int]:
        statuses = Counter(state.status.value for state in states.values())
        return {
            "listed": listed,
            "new": len(states.keys() - stored.keys()),
            "detailed": detailed,
            "in_scope": sum(state.in_text_scope for state in states.values()),
            **{status.value: statuses.get(status.value, 0) for status in PageStatus},
        }

    async def _fetch(
        self, decisions: list[FetchDecision], states: dict[int, PageState]
    ) -> tuple[int, list[tuple[int, str]]]:
        fetched, failures, consecutive, dirty = 0, [], 0, {}
        for decision in decisions:
            try:
                page = await self._source.parse(decision.page_id)
            except WikiSourceError as error:
                failures.append((decision.page_id, str(error)))
                consecutive += 1
                if consecutive >= MAX_CONSECUTIVE_FAILURES:
                    break
                continue
            consecutive = 0
            key = self._bronze.save(page)
            dirty[decision.page_id] = states[decision.page_id] = _with_fetch(
                states[decision.page_id], page.revid, page.fetched_at, key
            )
            fetched += 1
            if len(dirty) >= PERSIST_EVERY:
                await self._inventory.upsert(dirty.values())
                dirty = {}
        await self._inventory.upsert(dirty.values())
        return fetched, failures
