"""Smoke test for PHA 5: State Management & CLI Subcommands."""

import sys
from datetime import datetime
from pathlib import Path

# Force stdout to UTF-8 for Windows console support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from click.testing import CliRunner

from app.infrastructure.ingestion.cli import cli
from app.infrastructure.ingestion.models import Chunk, PageTypeEnum
from app.infrastructure.ingestion.storage import (
    IngestionStateDB,
    PageStateRecord,
    QdrantSyncManager,
    map_page_type_to_collection,
)


def test_state_db_basic():
    print("=== Test 1: IngestionStateDB — Basic CRUD & Hashing ===")
    test_db_path = Path("scratch/test_storage/test_ingestion.sqlite")
    if test_db_path.exists():
        test_db_path.unlink()

    db = IngestionStateDB(test_db_path)

    record = PageStateRecord(
        page_id=54321,
        canonical_slug="startorch_academy",
        title="Startorch Academy",
        page_type="REGION",
        text_hash="sha256:abc123hash",
        chunk_count=36,
        last_updated=datetime.utcnow(),
        status="PROCESSED",
    )

    # Upsert & Read back
    db.upsert_page_state(record)
    fetched = db.get_page_state(54321)

    assert fetched is not None
    assert fetched.page_id == 54321
    assert fetched.canonical_slug == "startorch_academy"
    assert fetched.chunk_count == 36
    assert fetched.status == "PROCESSED"

    # Check is_page_unchanged
    assert db.is_page_unchanged(54321, "sha256:abc123hash") is True
    assert db.is_page_unchanged(54321, "sha256:different_hash") is False

    stats = db.get_summary_stats()
    assert stats["total_processed_pages"] == 1
    assert stats["total_chunks_stored"] == 36

    print(f"  DB initialized at: {test_db_path}")
    print(f"  Record fetched: page_id={fetched.page_id}, slug={fetched.canonical_slug}")
    print(f"  Summary stats: {stats}")
    print("  PASS\n")


def test_orphan_detection():
    print("=== Test 2: IngestionStateDB — Orphan Cleanup Detection ===")
    test_db_path = Path("scratch/test_storage/test_orphan.sqlite")
    if test_db_path.exists():
        test_db_path.unlink()

    db = IngestionStateDB(test_db_path)

    # Insert 3 pages into DB
    for i in range(1, 4):
        db.upsert_page_state(
            PageStateRecord(
                page_id=100 + i,
                canonical_slug=f"page_{i}",
                title=f"Page {i}",
                page_type="CHARACTER",
                text_hash=f"hash_{i}",
                chunk_count=5,
            )
        )

    # Active pages in new crawl: only page 101 and 102 (page 103 was deleted!)
    active_ids = {101, 102}
    orphans = db.detect_orphans(active_ids)

    assert len(orphans) == 1
    assert orphans[0].page_id == 103
    assert orphans[0].status == "DELETED"

    # Delete orphan from DB
    db.delete_page_state(103)
    assert db.get_page_state(103) is None

    stats = db.get_summary_stats()
    assert stats["total_processed_pages"] == 2

    print(f"  Detected orphans: {[o.page_id for o in orphans]}")
    print("  PASS\n")


def test_collection_mapping():
    print("=== Test 3: Qdrant Collection Routing ===")
    assert map_page_type_to_collection("CHARACTER") == "character_lore"
    assert map_page_type_to_collection("QUEST") == "story_lore"
    assert map_page_type_to_collection("DIALOGUE") == "story_lore"
    assert map_page_type_to_collection("TIMELINE") == "story_lore"
    assert map_page_type_to_collection("REGION") == "world_lore"
    assert map_page_type_to_collection("WEAPON") == "world_lore"
    assert map_page_type_to_collection("GENERIC") == "world_lore"

    print("  CHARACTER -> character_lore: OK")
    print("  QUEST -> story_lore: OK")
    print("  REGION -> world_lore: OK")
    print("  PASS\n")


def test_cli_end_to_end():
    print("=== Test 4: CLI End-to-End Execution ===")
    runner = CliRunner()

    raw_test_dir = Path("scratch/test_cli/raw")
    raw_test_dir.mkdir(parents=True, exist_ok=True)
    sample_file = raw_test_dir / "test_page.wikitext"
    sample_file.write_text(
        "== Startorch Academy ==\nStartorch Academy is a comprehensive research facility and educational institution "
        "built by the Spacetrek Collective for Resonators in Lahai-Roi. It trains Synchronists and conducts advanced research.",
        encoding="utf-8"
    )

    # 1. status command
    res_status = runner.invoke(cli, ["status"])
    assert res_status.exit_code == 0
    assert "Kuchiba Chisa" in res_status.output

    # 2. build-canonical command
    res_build = runner.invoke(
        cli,
        [
            "build-canonical",
            "--raw-dir",
            str(raw_test_dir),
            "--output",
            "scratch/test_cli/canonical.jsonl",
        ],
    )
    assert res_build.exit_code == 0
    assert "Successfully wrote" in res_build.output

    # 3. process-chunks command
    res_chunks = runner.invoke(
        cli,
        [
            "process-chunks",
            "--input",
            "scratch/test_cli/canonical.jsonl",
            "--output",
            "scratch/test_cli/chunks.jsonl",
            "--target-size",
            "200",
        ],
    )
    assert res_chunks.exit_code == 0
    assert "Total" in res_chunks.output

    # 4. sync-qdrant command
    res_sync = runner.invoke(
        cli,
        [
            "sync-qdrant",
            "--input",
            "scratch/test_cli/chunks.jsonl",
            "--db",
            "scratch/test_cli/ingestion.sqlite",
            "--staging-version",
            "cli_test",
        ],
    )
    if res_sync.exit_code != 0:
        print(f"res_sync output: {res_sync.output}")
        print(f"res_sync exception: {res_sync.exception}")
    assert res_sync.exit_code == 0
    assert "Staged and acknowledged" in res_sync.output

    # 5. cleanup-orphans command
    res_clean = runner.invoke(
        cli,
        [
            "cleanup-orphans",
            "--db",
            "scratch/test_cli/ingestion.sqlite",
        ],
    )
    assert res_clean.exit_code == 0

    print("  CLI build-canonical: OK")
    print("  CLI process-chunks: OK")
    print("  CLI sync-qdrant: OK")
    print("  CLI cleanup-orphans: OK")
    print("  CLI status: OK")
    print("  PASS\n")


if __name__ == "__main__":
    test_state_db_basic()
    test_orphan_detection()
    test_collection_mapping()
    test_cli_end_to_end()
    print("=" * 55)
    print("ALL 4 TESTS PASSED — PHA 5 COMPLETE")
    print("=" * 55)
