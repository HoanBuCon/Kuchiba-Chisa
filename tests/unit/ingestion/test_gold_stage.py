"""Gold stage: last-known-good selection, coverage, quality numbers and the artifact layout."""

import gzip
import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from app.application.ingestion.gold_stage import (
    GoldSettings,
    GoldStage,
    corpus_fingerprint,
    uncovered_units,
)
from app.domain.ingestion.chunking import Chunker, ChunkPolicy
from app.domain.ingestion.dedup import OwnerPolicy
from app.domain.ingestion.documents import Block, BlockKind, CanonicalDocument
from app.domain.ingestion.knowledge import KnowledgeBase
from app.domain.ingestion.page_checks import Verdict
from app.domain.ingestion.pages import PageState, PageStatus
from app.domain.ingestion.units import Collection, Unit
from app.domain.interfaces.silver import SilverEntry
from app.infrastructure.ingestion.gold.config import load_gold_settings
from app.infrastructure.ingestion.gold.gold_store import FileGoldStore

NOW = datetime(2026, 11, 2, 8, tzinfo=UTC)
EMPTY_KNOWLEDGE = KnowledgeBase((), (), (), (), ())
SETTINGS = GoldSettings(
    assembler_version="gold-test",
    config_hash="abc",
    tokenizer_model="model",
    chunk_policy=ChunkPolicy(target_tokens=30, max_tokens=40, min_tokens=5, passage_prefix=""),
    owner_policy=OwnerPolicy(("resonator", "lore"), min_chars=10),
    tiny_chunk_tokens=3,
)


def _count(text: str) -> int:
    return len(text.split())


def _doc(page_id: int, text: str, family: str = "lore") -> CanonicalDocument:
    blocks = (Block(BlockKind.PROSE, ("S",), text),)
    return CanonicalDocument(page_id, f"P{page_id}", 7, family, "silver-x", blocks)


class FakeInventory:
    def __init__(self, *states) -> None:
        self.states = {s.page_id: s for s in states}

    async def load(self):
        return dict(self.states)


class FakeLedger:
    def __init__(self, *entries) -> None:
        self.entries = {e.page_id: e for e in entries}

    async def load(self):
        return dict(self.entries)


class FakeSilver:
    def __init__(self, documents) -> None:
        self.documents = documents

    def load(self, path):
        return self.documents[path]


def _state(page_id: int, **changes) -> PageState:
    return replace(PageState(page_id, f"P{page_id}", 1, NOW, family="lore", tier="A"), **changes)


def _entry(page_id: int, lkg: str | None, verdict=Verdict.ACCEPT) -> SilverEntry:
    return SilverEntry(page_id, f"latest/{page_id}", "h", verdict, (), 0, NOW, lkg)


def _stage(tmp_path, states, entries, documents) -> GoldStage:
    return GoldStage(
        FakeInventory(*states),
        FakeSilver(documents),
        FakeLedger(*entries),
        FileGoldStore(tmp_path),
        _count,
        SETTINGS,
        clock=lambda: NOW,
    )


def _read_chunks(tmp_path, report) -> list[dict]:
    raw = gzip.decompress((tmp_path / report.path / "chunks.jsonl.gz").read_bytes())
    return [json.loads(line) for line in raw.decode("utf-8").splitlines()]


async def test_corpus_uses_last_known_good_and_skips_pages_without_one(tmp_path) -> None:
    report = await _stage(
        tmp_path,
        [_state(1), _state(2), _state(3)],
        [_entry(1, "good/1", Verdict.QUARANTINE), _entry(2, None, Verdict.QUARANTINE)],
        {"good/1": _doc(1, "Previous good text of page one.")},
    ).run()

    assert [c["page_id"] for c in _read_chunks(tmp_path, report)] == [1]
    assert report.quality["pages"] == 1
    assert report.quality["pages_without_silver"] == 2


async def test_out_of_scope_and_deleted_pages_stay_out(tmp_path) -> None:
    report = await _stage(
        tmp_path,
        [_state(1, status=PageStatus.DELETED), _state(2, family=None)],
        [_entry(1, "x"), _entry(2, "x")],
        {"x": _doc(1, "Should not appear in the corpus.")},
    ).run()

    assert report.quality["chunks"] == 0 and report.quality["pages_without_silver"] == 0


async def test_shared_text_lives_on_its_owner_and_is_reported(tmp_path) -> None:
    shared = "A passage repeated across two different pages."
    report = await _stage(
        tmp_path,
        [_state(1), _state(2)],
        [_entry(1, "a"), _entry(2, "b")],
        {"a": _doc(1, shared, "lore"), "b": _doc(2, shared, "resonator")},
    ).run()

    assert [c["page_id"] for c in _read_chunks(tmp_path, report)] == [2]
    assert report.quality["units_removed_as_duplicates"] == 1
    assert report.quality["duplicate_bodies"] == 0
    assert report.quality["uncovered_units"] == 0


async def test_manifest_records_versions_snapshot_counts_and_checksums(tmp_path) -> None:
    report = await _stage(
        tmp_path, [_state(1)], [_entry(1, "a")], {"a": _doc(1, "Some page text here.")}
    ).run()

    assert report.corpus_version == "2026.11.02-1"
    directory = tmp_path / report.path
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_snapshot"] == {"1": 7}
    assert manifest["components"]["cleaners"] == ["silver-x"]
    assert manifest["components"]["assembler"] == "gold-test"
    assert manifest["counts"]["collection"] == {"lore_canon": 1}
    for name, checksum in manifest["checksums"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == checksum


async def test_each_run_gets_a_new_version_and_leaves_no_staging_directory(tmp_path) -> None:
    stage = _stage(tmp_path, [_state(1)], [_entry(1, "a")], {"a": _doc(1, "Some page text here.")})

    first, second = await stage.run(), await stage.run()

    assert (first.corpus_version, second.corpus_version) == ("2026.11.02-1", "2026.11.02-2")
    assert sorted(p.name for p in (tmp_path / "gold").iterdir()) == ["2026.11.02-1", "2026.11.02-2"]


def test_store_refuses_to_overwrite_a_version(tmp_path) -> None:
    store = FileGoldStore(tmp_path)
    store.write("2026.11.02-1", [], {}, EMPTY_KNOWLEDGE, {})

    with pytest.raises(FileExistsError):
        store.write("2026.11.02-1", [], {}, EMPTY_KNOWLEDGE, {})
    assert store.next_version(date(2026, 11, 2)) == "2026.11.02-2"


def test_coverage_check_finds_a_unit_missing_from_the_chunks() -> None:
    kept = Unit(1, "T", "lore", Collection.CANON, "prose", (), "g", "kept  text")
    lost = Unit(1, "T", "lore", Collection.CANON, "prose", (), "g", "lost text")
    chunks = Chunker(_count, SETTINGS.chunk_policy).chunk([kept])

    assert uncovered_units([kept, lost], chunks) == [lost]


def test_shipped_gold_config_loads_within_the_model_limit() -> None:
    settings = load_gold_settings()

    assert settings.chunk_policy.max_tokens == 450
    assert settings.chunk_policy.passage_prefix == "passage: "
    assert settings.owner_policy.family_priority[0] == "resonator_backstory"


def test_long_turn_cut_with_overlap_counts_as_covered_but_lost_sentences_do_not() -> None:
    sentences = [f"Sentence number {i} of the long report." for i in range(40)]
    turn = Unit(
        1, "T", "lore", Collection.DIALOGUE, "dialogue", (), "g", " ".join(sentences), True, 1
    )
    chunks = Chunker(_count, SETTINGS.chunk_policy).chunk([turn])

    assert len(chunks) > 1
    assert uncovered_units([turn], chunks) == []
    assert uncovered_units([turn], chunks[:-1]) == [turn]


def test_fingerprint_ignores_order_but_not_content() -> None:
    units = [
        Unit(1, "T", "lore", Collection.CANON, "prose", (), "a", "First text."),
        Unit(1, "T", "lore", Collection.CANON, "prose", (), "b", "Second text."),
    ]
    chunks = Chunker(_count, SETTINGS.chunk_policy).chunk(units)

    assert corpus_fingerprint(chunks) == corpus_fingerprint(list(reversed(chunks)))
    assert corpus_fingerprint(chunks) != corpus_fingerprint(chunks[:1])


async def test_knowledge_and_fingerprint_are_published_with_the_corpus(tmp_path) -> None:
    report = await _stage(
        tmp_path, [_state(1)], [_entry(1, "a")], {"a": _doc(1, "Some page text here.")}
    ).run()

    directory = tmp_path / report.path
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    knowledge = json.loads(gzip.decompress((directory / "knowledge.json.gz").read_bytes()))
    assert manifest["counts"]["knowledge"]["entities"] == 1
    assert len(manifest["logical_sha256"]) == 64
    assert "knowledge.json.gz" in manifest["checksums"]
    assert knowledge["entities"][0]["title"] == "P1"
    [chunk] = _read_chunks(tmp_path, report)
    assert chunk["entities"] == ["P1"]


async def test_published_knowledge_reads_back_unchanged(tmp_path) -> None:
    states = [
        _state(1, redirects=("Other Name",), categories=("Category:Released in Version 2.0",))
    ]
    report = await _stage(
        tmp_path, states, [_entry(1, "a")], {"a": _doc(1, "Some page text here.")}
    ).run()

    knowledge = FileGoldStore(tmp_path).read_knowledge(report.corpus_version)

    assert knowledge.entities[0].game_version == "2.0"
    assert knowledge.aliases[0].alias == "Other Name"
    assert isinstance(knowledge.aliases[0].evidence, tuple)
