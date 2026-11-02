"""Wiki sync service: reconcile, classify, budgeted fetch, deletion, renames, run log."""

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.application.ingestion.wiki_sync import RunStatus, SyncRules, WikiSyncService
from app.domain.ingestion.change_detection import FetchPolicy, FetchReason, TemplateClassifier
from app.domain.ingestion.families import FamilyCatalog, FamilyRule
from app.domain.ingestion.pages import PageStatus, WikiPageInfo
from app.domain.interfaces.wiki_ingestion import ParsedPage, SyncRun, WikiSourceError

NOW = datetime(2026, 11, 2, tzinfo=UTC)
OLD = NOW - timedelta(days=5)
RULES = SyncRules(
    catalog=FamilyCatalog(
        rules=(
            FamilyRule("resonator", "A", categories=("Resonators",)),
            FamilyRule("faction", "A", subcategory_parents=("Factions",)),
            FamilyRule("echo", "B", categories=("Echoes",)),
        ),
    ),
    classifier=TemplateClassifier(chrome_patterns=(r"Navbox",)),
    policy=FetchPolicy(stabilization=timedelta(hours=24), rolling_fraction=0.0, budget=10),
)


class FakeSource:
    def __init__(self) -> None:
        self.pages: dict[int, WikiPageInfo] = {}
        self.categories: dict[int, tuple[str, ...]] = {}
        self.templates: dict[int, tuple[str, ...]] = {}
        self.subcats = {"Factions": ["Black Shores"]}
        self.changed: frozenset[str] = frozenset()
        self.deleted: frozenset[str] = frozenset()
        self.broken: set[int] = set()
        self.detail_requests: list[list[int]] = []
        self.parsed: list[int] = []
        self.template_since: list[datetime] = []
        self.redirect_titles: dict[int, tuple[str, ...]] = {}

    def add(
        self, page_id, title, *, revid=1, touched=OLD, revised=OLD, categories=(), templates=()
    ):
        self.pages[page_id] = WikiPageInfo(page_id, title, revid, touched, revised)
        self.categories[page_id] = categories
        self.templates[page_id] = templates

    async def list_page_ids(self):
        return {pid: info.title for pid, info in self.pages.items()}

    async def page_infos(self, page_ids):
        return [self.pages[pid] for pid in page_ids]

    async def page_details(self, page_ids):
        self.detail_requests.append(list(page_ids))
        return {pid: (self.categories[pid], self.templates[pid]) for pid in page_ids}

    async def subcategories(self, parent):
        return self.subcats.get(parent, [])

    async def redirects(self, page_ids):
        return {pid: self.redirect_titles.get(pid, ()) for pid in page_ids}

    async def changed_templates(self, since):
        self.template_since.append(since)
        return self.changed

    async def deleted_titles(self, since):
        return self.deleted

    async def parse(self, page_id):
        if page_id in self.broken:
            raise WikiSourceError("HTTP 503")
        self.parsed.append(page_id)
        info = self.pages[page_id]
        return ParsedPage(
            page_id, info.title, info.last_revid, "<p/>", (), (), (), {}, "u", "CC BY-SA", NOW
        )


class FakeInventory:
    def __init__(self) -> None:
        self.states = {}
        self.runs = {}
        self.locked = False

    async def load(self):
        return dict(self.states)

    async def upsert(self, states):
        self.states.update({s.page_id: s for s in states})

    async def last_successful_run(self):
        done = [r for r in self.runs.values() if r.status == RunStatus.SUCCEEDED]
        return max(done, key=lambda r: r.started_at, default=None)

    async def record_run(self, run):
        self.runs[run.run_id] = run

    async def abandon_unfinished_runs(self, finished_at):
        stale = [r for r in self.runs.values() if r.status == RunStatus.RUNNING]
        for run in stale:
            self.runs[run.run_id] = replace(run, status="abandoned", finished_at=finished_at)
        return len(stale)

    @asynccontextmanager
    async def exclusive_run(self):
        yield not self.locked


class FakeBronze:
    def save(self, page):
        return f"bronze/{page.page_id}/{page.revid}.json.gz"


@pytest.fixture
def source():
    return FakeSource()


@pytest.fixture
def inventory():
    return FakeInventory()


def _service(source, inventory, *, now=NOW, rules=RULES):
    return WikiSyncService(source, inventory, FakeBronze(), rules, clock=lambda: now)


async def test_first_sync_classifies_and_fetches_only_enabled_tiers(source, inventory) -> None:
    source.add(1, "Chisa", categories=("Category:Resonators",))
    source.add(2, "Black Shores", categories=("Category:Black Shores",))
    source.add(3, "Some Echo", categories=("Category:Echoes",))
    source.add(4, "Main Page")

    report = await _service(source, inventory).sync()

    assert report.status == RunStatus.SUCCEEDED
    assert sorted(source.parsed) == [1, 2]
    assert inventory.states[2].family == "faction"
    assert inventory.states[3].family is None
    assert inventory.states[1].bronze_key == "bronze/1/1.json.gz"
    assert report.stats["in_scope"] == 2 and report.stats["fetched"] == 2
    assert inventory.runs[report.run_id].status == RunStatus.SUCCEEDED


async def test_second_sync_without_changes_fetches_nothing_and_skips_details(
    source, inventory
) -> None:
    source.add(1, "Chisa", categories=("Category:Resonators",))
    await _service(source, inventory).sync()
    source.parsed.clear()
    source.detail_requests.clear()

    report = await _service(source, inventory).sync()

    assert source.parsed == [] and source.detail_requests == []
    assert report.stats["planned"] == 0


async def test_plan_writes_nothing(source, inventory) -> None:
    source.add(1, "Chisa", categories=("Category:Resonators",))

    report = await _service(source, inventory).plan()

    assert [d.reason for d in report.decisions] == [FetchReason.NEW]
    assert inventory.states == {} and inventory.runs == {} and source.parsed == []


async def test_navbox_touch_is_ignored_but_content_template_touch_refetches(
    source, inventory
) -> None:
    templates = ("Template:Resonator Navbox", "Template:Infobox Resonator")
    source.add(1, "Chisa", categories=("Category:Resonators",), templates=templates)
    await _service(source, inventory).sync()
    source.parsed.clear()
    source.add(
        1,
        "Chisa",
        touched=NOW - timedelta(hours=1),
        categories=("Category:Resonators",),
        templates=templates,
    )

    source.changed = frozenset({"Template:Resonator Navbox"})
    navbox = await _service(source, inventory).sync()
    source.changed = frozenset({"Template:Infobox Resonator"})
    infobox = await _service(source, inventory).sync()

    assert navbox.stats["planned"] == 0
    assert [d.reason for d in infobox.decisions] == [FetchReason.CONTENT_TEMPLATE]
    assert source.template_since[-1] == OLD


async def test_recent_revision_waits_for_stabilisation(source, inventory) -> None:
    source.add(1, "Chisa", categories=("Category:Resonators",))
    await _service(source, inventory).sync()
    source.add(
        1,
        "Chisa",
        revid=2,
        touched=NOW,
        revised=NOW - timedelta(hours=2),
        categories=("Category:Resonators",),
    )

    waiting = await _service(source, inventory).sync()
    later = await _service(source, inventory, now=NOW + timedelta(days=1)).sync()

    assert waiting.stats["planned"] == 0
    assert [d.reason for d in later.decisions] == [FetchReason.REVISION]
    assert inventory.states[1].fetched_revid == 2


async def test_rename_keeps_page_and_records_alias(source, inventory) -> None:
    source.add(1, "Chisa", categories=("Category:Resonators",))
    await _service(source, inventory).sync()
    source.add(1, "Kuchiba Chisa", revid=2, touched=NOW, categories=("Category:Resonators",))

    await _service(source, inventory, now=NOW + timedelta(days=2)).sync()

    assert inventory.states[1].title == "Kuchiba Chisa"
    assert inventory.states[1].aliases == ("Chisa",)


async def test_deletion_needs_two_absences_and_a_log_entry(source, inventory) -> None:
    source.add(1, "Chisa", categories=("Category:Resonators",))
    await _service(source, inventory).sync()
    del source.pages[1]

    await _service(source, inventory).sync()
    assert inventory.states[1].status is PageStatus.PENDING_DELETE
    await _service(source, inventory).sync()
    assert inventory.states[1].status is PageStatus.PENDING_DELETE
    source.deleted = frozenset({"Chisa"})
    await _service(source, inventory).sync()
    assert inventory.states[1].status is PageStatus.DELETED


async def test_page_that_returns_is_reactivated(source, inventory) -> None:
    source.add(1, "Chisa", categories=("Category:Resonators",))
    await _service(source, inventory).sync()
    info = source.pages.pop(1)
    await _service(source, inventory).sync()
    source.pages[1] = info

    await _service(source, inventory).sync()

    assert inventory.states[1].status is PageStatus.ACTIVE


async def test_budget_cuts_the_plan(source, inventory) -> None:
    for pid in range(1, 6):
        source.add(pid, f"R{pid}", categories=("Category:Resonators",))
    rules = replace(RULES, policy=replace(RULES.policy, budget=2))

    report = await _service(source, inventory, rules=rules).sync()

    assert source.parsed == [1, 2]
    assert report.stats["planned"] == 2


async def test_parse_failures_are_partial_and_repeated_failures_stop_fetching(
    source, inventory
) -> None:
    for pid in range(1, 9):
        source.add(pid, f"R{pid}", categories=("Category:Resonators",))
    source.broken = {1, 2, 3, 4, 5}

    report = await _service(source, inventory).sync()

    assert report.status == RunStatus.PARTIAL
    assert len(report.failures) == 5 and source.parsed == []
    assert inventory.states[6].fetched_revid is None


async def test_one_bad_page_does_not_stop_the_run(source, inventory) -> None:
    for pid in range(1, 4):
        source.add(pid, f"R{pid}", categories=("Category:Resonators",))
    source.broken = {2}

    report = await _service(source, inventory).sync()

    assert source.parsed == [1, 3]
    assert report.failures == ((2, "HTTP 503"),)


async def test_source_error_during_reconcile_fails_the_run(source, inventory) -> None:
    async def broken():
        raise WikiSourceError("expected JSON; possible challenge page")

    source.list_page_ids = broken

    report = await _service(source, inventory).sync()

    assert report.status == RunStatus.FAILED
    assert inventory.runs[report.run_id].status == RunStatus.FAILED
    assert await inventory.last_successful_run() is None


async def test_concurrent_run_is_refused(source, inventory) -> None:
    inventory.locked = True

    report = await _service(source, inventory).sync()

    assert report.status == RunStatus.LOCKED and inventory.runs == {}


async def test_changed_family_rules_reclassify_without_asking_the_wiki(source, inventory) -> None:
    source.add(1, "Resonator", categories=("Category:Resonators", "Category:Terminology"))
    await _service(source, inventory).sync()
    source.detail_requests.clear()
    vetoed = FamilyRule(
        "resonator", "A", categories=("Resonators",), excluded_categories=("Terminology",)
    )
    rules = replace(RULES, catalog=replace(RULES.catalog, rules=(vetoed,)))

    await _service(source, inventory, rules=rules).sync()

    assert inventory.states[1].family is None
    assert source.detail_requests == []


async def test_rows_without_stored_categories_get_details_once(source, inventory) -> None:
    source.add(1, "Chisa", categories=("Category:Resonators",))
    await _service(source, inventory).sync()
    inventory.states[1] = replace(inventory.states[1], categories=())
    source.detail_requests.clear()

    await _service(source, inventory).sync()
    await _service(source, inventory).sync()

    assert source.detail_requests == [[1]]
    assert inventory.states[1].family == "resonator"


async def test_a_run_that_died_is_marked_abandoned_by_the_next_one(source, inventory) -> None:
    source.add(1, "Chisa", categories=("Category:Resonators",))
    dead = SyncRun("dead", OLD, None, RunStatus.RUNNING, {})
    await inventory.record_run(dead)

    await _service(source, inventory).sync()

    assert inventory.runs["dead"].status == "abandoned"
    assert inventory.runs["dead"].finished_at == NOW


async def test_redirects_are_refreshed_for_in_scope_pages_every_run(source, inventory) -> None:
    source.add(1, "Chisa", categories=("Category:Resonators",))
    source.add(2, "Main Page")
    await _service(source, inventory).sync()
    assert inventory.states[1].redirects == ()

    source.redirect_titles = {1: ("Kuchiba Chisa",), 2: ("Home",)}
    await _service(source, inventory).sync()

    assert inventory.states[1].redirects == ("Kuchiba Chisa",)
    assert inventory.states[2].redirects == ()
