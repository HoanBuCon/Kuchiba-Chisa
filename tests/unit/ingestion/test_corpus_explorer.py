"""Corpus Explorer: diff, grouping, escaped rendering with no server needed (ING-017)."""

from datetime import UTC, datetime

from app.application.ingestion.report_stage import CorpusReport, PageInspection
from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.corpus_report import (
    CorpusDiff,
    PageChange,
    diff_corpus,
    distributions,
    flagged_pages,
    knowledge_summary,
    pages_to_inspect,
)
from app.domain.ingestion.knowledge import Alias, KnowledgeBase
from app.domain.ingestion.page_checks import Verdict
from app.domain.ingestion.release_gates import GateCheck, GateReport
from app.domain.ingestion.units import Collection
from app.domain.interfaces.silver import SilverEntry
from app.infrastructure.ingestion.corpus_explorer import RAW_PREVIEW_CHARS, HtmlCorpusExplorer

ATTACK = "<script>alert(1)</script>"


def _chunk(page_id: int, text: str, family="lore", tokens=120, title=None) -> Chunk:
    return Chunk(
        evidence_id=f"wiki:{page_id}:{text}",
        point_id=f"p-{page_id}-{text}",
        page_id=page_id,
        title=title or f"Page {page_id}",
        family=family,
        collection=Collection.CANON,
        kind="prose",
        section=("S",),
        text=text,
        embedding_text=text,
        tokens=tokens,
    )


def _entry(page_id: int, verdict: Verdict, reasons=()) -> SilverEntry:
    return SilverEntry(
        page_id, "p", "h", verdict, reasons, 0, datetime(2026, 11, 4, tzinfo=UTC), "p"
    )


def test_diff_finds_added_changed_and_removed_pages() -> None:
    previous = [_chunk(1, "same"), _chunk(2, "old"), _chunk(3, "gone")]
    current = [_chunk(1, "same"), _chunk(2, "new"), _chunk(2, "more"), _chunk(4, "fresh")]

    diff = diff_corpus(current, previous)

    assert [c.page_id for c in diff.added] == [4]
    assert [(c.page_id, c.added_chunks, c.removed_chunks) for c in diff.changed] == [(2, 2, 1)]
    assert [c.page_id for c in diff.removed] == [3]


def test_identical_corpus_has_no_diff() -> None:
    chunks = [_chunk(1, "same")]

    assert diff_corpus(chunks, chunks) == CorpusDiff()


def test_only_quarantined_and_held_pages_are_flagged() -> None:
    entries = {
        1: _entry(1, Verdict.ACCEPT),
        2: _entry(2, Verdict.QUARANTINE, ("safety:x",)),
        3: _entry(3, Verdict.HOLD, ("shrink",)),
    }

    rows = flagged_pages(entries, {2: ("Two", "lore"), 3: ("Three", "region")})

    assert {(r.page_id, r.title, r.family) for r in rows} == {
        (2, "Two", "lore"),
        (3, "Three", "region"),
    }


def test_distribution_buckets_tokens_by_family() -> None:
    chunks = [_chunk(1, "a", tokens=120), _chunk(1, "b", tokens=149), _chunk(2, "c", tokens=300)]

    row = distributions(chunks)[0]

    assert (row.family, row.pages, row.chunks, row.median_tokens) == ("lore", 2, 3, 149)
    assert row.histogram == {100: 2, 300: 1}


def test_knowledge_summary_counts_inferred_aliases_with_evidence() -> None:
    aliases = (
        Alias("A", "T", "inferred", "low", ("page",)),
        Alias("B", "T", "inferred", "low"),
        Alias("C", "T", "redirect", "high"),
    )

    summary = knowledge_summary(KnowledgeBase((), aliases, (), (), ()))

    assert (summary.aliases, summary.inferred_aliases, summary.inferred_with_evidence) == (3, 2, 1)


def test_inspector_covers_changes_flags_and_a_sample_of_every_family() -> None:
    chunks = [_chunk(n, "t", family="lore") for n in range(1, 7)] + [
        _chunk(9, "t", family="region")
    ]
    diff = CorpusDiff(changed=(PageChange(6, "Six", 1, 0),))
    flagged = flagged_pages({5: _entry(5, Verdict.HOLD)}, {})

    assert pages_to_inspect(diff, flagged, chunks) == (1, 2, 3, 5, 6, 9)


def _report(evaluation=None) -> CorpusReport:
    page = PageInspection(
        page_id=1,
        title=f"Title {ATTACK}",
        url="https://w/P",
        raw_html=ATTACK + "x" * (RAW_PREVIEW_CHARS + 50),
        silver_blocks=(("prose", "S", f"Body {ATTACK}"),),
        removed={"navbox": 2},
        chunks=(_chunk(1, f"Chunk {ATTACK}"),),
    )
    chunks = [_chunk(1, "t"), _chunk(2, "t")]
    flagged = flagged_pages(
        {1: _entry(1, Verdict.QUARANTINE, ("safety:x",))}, {1: (f"Title {ATTACK}", "lore")}
    )
    return CorpusReport(
        version="2026.11.04-1",
        previous="2026.11.03-2",
        manifest={},
        gate=GateReport((GateCheck("uncovered_units", False, "2 (limit 0)"),)),
        diff=CorpusDiff(changed=(PageChange(1, f"Title {ATTACK}", 1, 1),)),
        flagged=flagged,
        distributions=distributions(chunks),
        knowledge=knowledge_summary(KnowledgeBase((), (), (), (), ())),
        inspections=(page,),
        evaluation=evaluation,
    )


def test_report_is_static_and_escapes_wiki_text(tmp_path) -> None:
    entry = HtmlCorpusExplorer(tmp_path).write(_report())

    index = (tmp_path / entry).read_text(encoding="utf-8")
    page = (tmp_path / "reports/2026.11.04-1/pages/1.html").read_text(encoding="utf-8")

    assert entry == "reports/2026.11.04-1/index.html"
    assert "<script" not in index and "<script" not in page
    assert "&lt;script&gt;" in page
    assert "http://" not in index and "src=" not in index
    assert 'href="pages/1.html"' in index
    assert "FAIL" in index and "uncovered_units" in index
    assert "safety:x" in index


def test_raw_html_is_previewed_not_copied_whole(tmp_path) -> None:
    HtmlCorpusExplorer(tmp_path).write(_report())

    page = (tmp_path / "reports/2026.11.04-1/pages/1.html").read_text(encoding="utf-8")

    assert f"{RAW_PREVIEW_CHARS} of {RAW_PREVIEW_CHARS + 50 + len(ATTACK)} characters" in page
    assert "navbox" in page


def test_report_shows_the_retrieval_evaluation_when_given(tmp_path) -> None:
    group = {"cases": 2, "hit_at_5": 0.5, "mrr_at_10": 0.25}
    evaluation = {
        "modes": {
            "translated_local": {
                "overall": group,
                "by_category": {"lore": group},
                "by_language": {},
            }
        },
        "gate": {"passed": False, "failures": ["hit_at_5"]},
    }

    entry = HtmlCorpusExplorer(tmp_path).write(_report(evaluation))

    index = (tmp_path / entry).read_text(encoding="utf-8")
    assert "translated_local" in index and "FAIL: hit_at_5" in index
