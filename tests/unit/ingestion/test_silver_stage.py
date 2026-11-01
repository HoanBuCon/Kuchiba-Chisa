"""Silver stage: incremental re-cleaning, last-known-good fallback, stability hold (ING-006)."""

import re
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.application.ingestion.silver_stage import SilverStage
from app.domain.ingestion.documents import Block, BlockKind, CanonicalDocument
from app.domain.ingestion.page_checks import CheckPolicy, Verdict
from app.domain.ingestion.pages import PageState
from app.domain.interfaces.silver import CleaningError
from app.domain.interfaces.wiki_ingestion import ParsedPage

NOW = datetime(2026, 11, 2, tzinfo=UTC)
POLICY = CheckPolicy(residue=re.compile(r"\{\{"))


class FakeInventory:
    def __init__(self, *states: PageState) -> None:
        self.states = {s.page_id: s for s in states}

    async def load(self):
        return dict(self.states)


class FakeBronze:
    """Bronze keys map straight to the page text the fake cleaner turns into one block."""

    def __init__(self) -> None:
        self.texts: dict[str, str] = {}

    def load(self, key):
        if key not in self.texts:
            raise FileNotFoundError(key)
        return ParsedPage(1, "P", 1, self.texts[key], (), (), (), {}, "u", "l", NOW)


class FakeCleaner:
    version = "v1"

    def __init__(self) -> None:
        self.calls = 0

    def clean(self, page, family):
        self.calls += 1
        if page.html == "<broken>":
            raise CleaningError("bad")
        blocks = (Block(BlockKind.PROSE, (), page.html),) if page.html else ()
        return CanonicalDocument(page.page_id, page.title, page.revid, family, self.version, blocks)


class FakeSilver:
    def __init__(self) -> None:
        self.saved: dict[str, CanonicalDocument] = {}

    def path_for(self, page_id, key):
        return f"silver/{page_id}/{key}"

    def save(self, key, document):
        path = self.path_for(document.page_id, key)
        self.saved[path] = document
        return path

    def load(self, path):
        return self.saved[path]


class FakeLedger:
    def __init__(self) -> None:
        self.entries = {}

    async def load(self):
        return dict(self.entries)

    async def upsert(self, entries):
        self.entries.update({e.page_id: e for e in entries})


def _state(bronze_key="b1", **changes) -> PageState:
    base = PageState(
        1, "Page", 1, NOW, family="lore", tier="A", bronze_key=bronze_key, fetched_revid=1
    )
    return replace(base, **changes)


@pytest.fixture
def parts():
    return FakeInventory(_state()), FakeBronze(), FakeCleaner(), FakeSilver(), FakeLedger()


def _stage(parts, contracts=None) -> SilverStage:
    inventory, bronze, cleaner, silver, ledger = parts
    return SilverStage(
        inventory,
        bronze,
        cleaner,
        silver,
        ledger,
        policy=POLICY,
        contracts=contracts or {},
        clock=lambda: NOW,
    )


def _set_text(parts, text, key="b1") -> None:
    inventory, bronze, *_ = parts
    bronze.texts[key] = text
    inventory.states[1] = _state(bronze_key=key)


async def test_accepted_page_becomes_its_own_last_known_good(parts) -> None:
    _set_text(parts, "x" * 100)

    report = await _stage(parts).run()

    entry = parts[4].entries[1]
    assert report.stats == {"checked": 1, "accept": 1}
    assert entry.verdict is Verdict.ACCEPT and entry.lkg_path == entry.silver_path


async def test_unchanged_bronze_is_not_cleaned_again(parts) -> None:
    _set_text(parts, "x" * 100)
    await _stage(parts).run()

    report = await _stage(parts).run()

    assert report.stats == {"checked": 0, "unchanged": 1}
    assert parts[2].calls == 1


async def test_new_cleaner_version_recleans(parts) -> None:
    _set_text(parts, "x" * 100)
    await _stage(parts).run()
    parts[2].version = "v2"

    report = await _stage(parts).run()

    assert report.stats["checked"] == 1


async def test_quarantined_page_keeps_the_previous_good_silver(parts) -> None:
    _set_text(parts, "x" * 100)
    await _stage(parts).run()
    good = parts[4].entries[1].lkg_path
    _set_text(parts, "broken {{ markup", key="b2")

    report = await _stage(parts).run()

    entry = parts[4].entries[1]
    assert entry.verdict is Verdict.QUARANTINE and entry.lkg_path == good
    assert report.flagged == (("Page", ("residue:{{",)),)


async def test_shrunken_page_is_held_until_stable_for_two_runs(parts) -> None:
    _set_text(parts, "x" * 100)
    await _stage(parts).run()
    good = parts[4].entries[1].lkg_path
    _set_text(parts, "x" * 10, key="b2")

    verdicts = []
    for _ in range(3):
        await _stage(parts).run()
        verdicts.append(parts[4].entries[1].verdict)

    assert verdicts == [Verdict.HOLD, Verdict.HOLD, Verdict.ACCEPT]
    assert parts[4].entries[1].lkg_path != good


async def test_out_of_scope_and_unfetched_pages_are_skipped(parts) -> None:
    inventory = parts[0]
    inventory.states = {1: _state(family=None), 2: _state(bronze_key=None, page_id=2)}

    report = await _stage(parts).run()

    assert report.stats == {"checked": 0}


async def test_unreadable_bronze_or_html_is_reported_not_fatal(parts) -> None:
    inventory, bronze, *_ = parts
    bronze.texts["b2"] = "<broken>"
    inventory.states = {
        1: _state(bronze_key="missing"),
        2: _state(bronze_key="b2", page_id=2, title="Two"),
    }

    report = await _stage(parts).run()

    assert report.stats == {"checked": 0, "failed": 2}
    assert {title for title, _ in report.flagged} == {"Page", "Two"}
