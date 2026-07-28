"""Smoke test for PHA 3: Canonical Layer Builder & Writer."""

import sys
from datetime import datetime
from pathlib import Path

# Force stdout to UTF-8 for Windows console support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SAMPLE_PATH = Path(r"d:\Hoc_Tap\Code\Du_An_Ca_Nhan\Chisa_bot\kuchiba_chisa\data\lore\world_lore\startorch_academy.md")

from app.infrastructure.ingestion.canonical.builder import build_canonical_page
from app.infrastructure.ingestion.canonical.writer import (
    CanonicalWriter,
    read_canonical_stream,
    write_canonical_stream,
)
from app.infrastructure.ingestion.models.canonical_page import (
    CanonicalPage,
    ContentTypeEnum,
    PageTypeEnum,
)
from app.infrastructure.ingestion.models.raw_page import RawPage, RawPageMeta


def test_build_canonical_synthetic():
    print("=== Test 1: Build CanonicalPage from Synthetic RawPage ===")
    meta = RawPageMeta(
        page_id=101,
        title="Kuchiba Chisa",
        revision_id=999,
        revision_timestamp=datetime(2026, 7, 20, 12, 0),
        categories=["Resonators", "5-Star Resonators"],
    )
    wikitext = """{{Character Infobox
|name = Kuchiba Chisa
|element = Spectro
|weapon = Sword
|rarity = 5
|region = Lahai-Roi
}}

'''Kuchiba Chisa''' is a student at Startorch Academy.

== Skills ==

Chisa uses thread perception in combat.

=== Resonance Skill: Thread Weave ===

Rover: "Chisa, watch out!"
Chisa: "Don't worry, my threads are already in position."

== Trivia ==

Chisa loves school festivals.
"""
    raw = RawPage(meta=meta, wikitext=wikitext)
    canonical = build_canonical_page(raw, pipeline_version="2.1.0")

    assert canonical.identity.page_id == 101
    assert canonical.identity.title == "Kuchiba Chisa"
    assert canonical.identity.canonical_slug == "kuchiba_chisa"
    assert canonical.identity.page_type == PageTypeEnum.CHARACTER
    assert canonical.document_metadata.element == "Spectro"
    assert canonical.document_metadata.weapon_type == "Sword"
    assert canonical.document_metadata.rarity == 5
    assert canonical.document_metadata.region == "Lahai-Roi"
    assert len(canonical.sections) >= 3

    # Dialogue content type check
    dialogue_sec = [s for s in canonical.sections if "Resonance Skill" in s.title]
    assert len(dialogue_sec) == 1
    assert dialogue_sec[0].content_type == ContentTypeEnum.DIALOGUE

    print(f"  Page ID: {canonical.identity.page_id}")
    print(f"  Title: {canonical.identity.title}")
    print(f"  Slug: {canonical.identity.canonical_slug}")
    print(f"  Page Type: {canonical.identity.page_type.value} ({canonical.identity.page_type_confidence})")
    print(f"  Element: {canonical.document_metadata.element}, Weapon: {canonical.document_metadata.weapon_type}")
    print(f"  Sections count: {len(canonical.sections)}")
    print("  PASS\n")


import pytest


@pytest.fixture
def canonical_page() -> CanonicalPage:
    return test_build_canonical_real_data()


def test_build_canonical_real_data():
    print("=== Test 2: Build CanonicalPage from Real Startorch Academy Data ===")
    raw_text = SAMPLE_PATH.read_text(encoding="utf-8")

    meta = RawPageMeta(
        page_id=54321,
        title="Startorch Academy",
        revision_id=789012,
        revision_timestamp=datetime(2026, 7, 20, 14, 30),
        categories=["Organizations", "Lahai-Roi", "Schools"],
    )
    raw_page = RawPage(meta=meta, wikitext=raw_text)

    canonical = build_canonical_page(raw_page)

    assert canonical.identity.page_id == 54321
    assert canonical.identity.canonical_slug == "startorch_academy"
    assert len(canonical.sections) >= 1
    assert canonical.quality.tables_parsed >= 0

    # Provenance check
    sources = canonical.sections[0].sources
    assert len(sources) >= 1
    assert sources[0].origin == "wiki_crawl"

    print(f"  Slug: {canonical.identity.canonical_slug}")
    print(f"  Page Type: {canonical.identity.page_type.value}")
    print(f"  Sections: {len(canonical.sections)}")
    print(f"  Tables Parsed: {canonical.quality.tables_parsed}")
    print(f"  Quality Score: {canonical.quality.parser_confidence}")
    print("  PASS\n")
    return canonical


def test_canonical_jsonl_roundtrip(canonical_page: CanonicalPage):
    print("=== Test 3: Streaming JSONL Writer & Reader Round-trip ===")
    test_dir = Path("scratch/test_canonical")
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "test_canonical.jsonl"

    # Write
    written_count = write_canonical_stream([canonical_page], filepath=test_file, mode="w")
    assert written_count == 1
    assert test_file.exists()

    # Read back
    read_pages = list(read_canonical_stream(test_file))
    assert len(read_pages) == 1

    restored = read_pages[0]
    assert restored.identity.page_id == canonical_page.identity.page_id
    assert restored.identity.canonical_slug == canonical_page.identity.canonical_slug
    assert len(restored.sections) == len(canonical_page.sections)
    assert restored.quality.tables_parsed == canonical_page.quality.tables_parsed

    print(f"  Written to: {test_file}")
    print(f"  File size: {test_file.stat().st_size} bytes")
    print(f"  Round-trip verified: page_id {restored.identity.page_id}")
    print("  PASS\n")


def test_canonical_writer_context_manager():
    print("=== Test 4: CanonicalWriter Context Manager Batch Write ===")
    test_file = Path("scratch/test_canonical/test_batch.jsonl")

    # Create 3 pages
    pages = []
    for i in range(3):
        meta = RawPageMeta(
            page_id=200 + i,
            title=f"Test Page {i}",
            revision_id=100 + i,
            revision_timestamp=datetime.utcnow(),
        )
        raw = RawPage(meta=meta, wikitext=f"== Section ==\nContent {i}")
        pages.append(build_canonical_page(raw))

    with CanonicalWriter(test_file, mode="w") as writer:
        count = writer.write_pages(pages)
        assert count == 3

    # Read back
    restored = list(read_canonical_stream(test_file))
    assert len(restored) == 3
    assert [p.identity.page_id for p in restored] == [200, 201, 202]

    print(f"  Batch written & read back 3 records successfully.")
    print("  PASS\n")


def test_hierarchical_raw_directory_scan(tmp_path: Path):
    print("=== Test 5: Build Canonical Pages from Hierarchical Directory Tree ===")
    nested_dir = tmp_path / "raw_wiki" / "Resonators" / "chisa"
    nested_dir.mkdir(parents=True, exist_ok=True)

    wikitext_file = nested_dir / "37333_backstory.wikitext"
    wikitext_file.write_text("== Character Stories ==\nChisa is a student at Startorch Academy.", encoding="utf-8")

    meta_file = nested_dir / "37333_backstory.meta.json"
    import json
    meta_file.write_text(
        json.dumps(
            {
                "page_id": 37333,
                "title": "Chisa/Backstory",
                "categories": ["Resonators"],
                "revision_id": 12,
            }
        ),
        encoding="utf-8",
    )

    found_files = list(tmp_path.rglob("*.wikitext"))
    assert len(found_files) == 1
    assert found_files[0] == wikitext_file

    meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
    raw_page = RawPage(
        meta=RawPageMeta(
            page_id=meta_data["page_id"],
            title=meta_data["title"],
            categories=meta_data["categories"],
            revision_id=meta_data["revision_id"],
            revision_timestamp=datetime.utcnow(),
        ),
        wikitext=wikitext_file.read_text(encoding="utf-8"),
    )
    canonical = build_canonical_page(raw_page)
    assert canonical.identity.page_id == 37333
    assert canonical.identity.title == "Chisa/Backstory"
    print("  Hierarchical directory scan and build verified successfully.")
    print("  PASS\n")


if __name__ == "__main__":
    test_build_canonical_synthetic()
    real_page = test_build_canonical_real_data()
    test_canonical_jsonl_roundtrip(real_page)
    test_canonical_writer_context_manager()
    from pathlib import Path
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        test_hierarchical_raw_directory_scan(Path(tmpdir))
    print("=" * 55)
    print("ALL 5 TESTS PASSED — CANONICAL LAYER COMPLETE")
    print("=" * 55)

