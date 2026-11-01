"""Change detection: revision, content template, stabilisation, rolling refresh, deletion."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.domain.ingestion.change_detection import (
    FetchPolicy,
    FetchReason,
    TemplateClassifier,
    mark_absent,
    plan_fetches,
)
from app.domain.ingestion.families import FamilyCatalog, FamilyRule
from app.domain.ingestion.pages import PageState, PageStatus, WikiPageInfo

NOW = datetime(2026, 11, 1, tzinfo=UTC)
CLASSIFIER = TemplateClassifier(chrome_patterns=(r"navbox", r"^Template:Stub$"))
POLICY = FetchPolicy(stabilization=timedelta(hours=24), rolling_fraction=0.0, budget=100)


def _fetched(page_id: int, **changes) -> PageState:
    base = PageState(
        page_id=page_id,
        title=f"Page {page_id}",
        last_revid=10,
        touched=NOW - timedelta(days=3),
        family="lore",
        tier="A",
        templates=("Template:Lore Navbox", "Template:Quote"),
        fetched_revid=10,
        fetched_touched=NOW - timedelta(days=3),
        fetched_at=NOW - timedelta(days=3),
    )
    return replace(base, **changes)


def _plan(states, *, changed=frozenset(), revision_times=None, policy=POLICY):
    return plan_fetches(
        states,
        revision_times=revision_times or {},
        changed_templates=changed,
        classifier=CLASSIFIER,
        policy=policy,
        now=NOW,
    )


def test_new_pages_and_aged_revisions_are_fetched_first() -> None:
    new = replace(_fetched(1), fetched_revid=None, fetched_at=None)
    revised = _fetched(2, last_revid=11)
    plan = _plan([revised, new], revision_times={2: NOW - timedelta(days=2)})
    assert [(d.page_id, d.reason) for d in plan] == [
        (1, FetchReason.NEW),
        (2, FetchReason.REVISION),
    ]


def test_fresh_revisions_wait_for_the_stabilisation_window() -> None:
    revised = _fetched(2, last_revid=11)
    assert _plan([revised], revision_times={2: NOW - timedelta(hours=3)}) == []


def test_only_content_template_edits_trigger_a_refetch() -> None:
    retouched = _fetched(3, touched=NOW - timedelta(hours=1))
    assert _plan([retouched], changed=frozenset({"Template:Lore Navbox"})) == []
    plan = _plan([retouched], changed=frozenset({"Template:Quote"}))
    assert [d.reason for d in plan] == [FetchReason.CONTENT_TEMPLATE]


def test_unknown_templates_are_treated_as_content() -> None:
    page = _fetched(4, touched=NOW, templates=("Template:Brand New Box",))
    assert [d.reason for d in _plan([page], changed=frozenset({"Template:Brand New Box"}))] == [
        FetchReason.CONTENT_TEMPLATE
    ]


def test_rolling_refresh_takes_the_stalest_pages_and_budget_caps_the_run() -> None:
    pages = [_fetched(i, fetched_at=NOW - timedelta(days=i)) for i in range(1, 11)]
    plan = _plan(pages, policy=FetchPolicy(timedelta(hours=24), rolling_fraction=0.2, budget=100))
    assert [d.page_id for d in plan] == [9, 10]
    capped = _plan(pages, policy=FetchPolicy(timedelta(hours=24), rolling_fraction=1.0, budget=3))
    assert len(capped) == 3


def test_out_of_scope_pages_are_never_fetched() -> None:
    outside = replace(_fetched(5), family=None, fetched_revid=None)
    assert _plan([outside]) == []


def test_deletion_needs_two_absences_and_a_log_entry() -> None:
    states = {1: _fetched(1), 2: _fetched(2, status=PageStatus.PENDING_DELETE), 3: _fetched(3)}
    first = mark_absent(states, present_ids=frozenset({3}), confirmed_deleted=frozenset())
    assert first[1].status is PageStatus.PENDING_DELETE
    assert 2 not in first  # pending but no deletion log yet: stays pending
    second = mark_absent(
        {**states, **first}, present_ids=frozenset({3}), confirmed_deleted=frozenset({1, 2})
    )
    assert second[1].status is PageStatus.DELETED and second[2].status is PageStatus.DELETED


def test_rename_keeps_page_id_and_records_the_old_title() -> None:
    state = _fetched(7, title="Old Name")
    renamed = state.observe(WikiPageInfo(page_id=7, title="New Name", last_revid=10, touched=NOW))
    assert renamed.title == "New Name" and renamed.aliases == ("Old Name",)


def test_family_catalog_matches_suffix_category_and_tier() -> None:
    catalog = FamilyCatalog(
        rules=(
            FamilyRule("backstory", "A", suffixes=("Backstory",)),
            FamilyRule("resonator", "A", categories=("Resonators",)),
            FamilyRule("npc", "B", categories=("Characters",)),
        ),
        excluded_suffixes=("Gallery",),
    )
    assert catalog.classify("Chisa/Backstory", ["Category:Resonators"]).name == "backstory"
    assert catalog.classify("Chisa", ["Category:Resonators"]).name == "resonator"
    assert catalog.classify("Some NPC", ["Category:Characters"]) is None  # tier B disabled
    assert catalog.classify("Chisa/Gallery", ["Category:Resonators"]) is None


def test_subcategory_parents_expand_into_member_categories() -> None:
    catalog = FamilyCatalog(
        rules=(
            FamilyRule("faction", "A", categories=("Factions",), subcategory_parents=("Factions",)),
        )
    )
    expanded = catalog.with_subcategories({"Factions": ["Black Shores"]})
    assert catalog.classify("Shorekeeper", ["Category:Black Shores"]) is None
    assert expanded.classify("Shorekeeper", ["Category:Black Shores"]).name == "faction"
