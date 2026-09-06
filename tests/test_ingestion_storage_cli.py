"""Smoke test for PHA 5: State Management & CLI Subcommands."""

import sys
import uuid
from datetime import datetime
from pathlib import Path

# Force stdout to UTF-8 for Windows console support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from click.testing import CliRunner

from app.application.ingestion.orchestrator import IngestionRunResult
from app.infrastructure.ingestion import cli as ingestion_cli
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


def test_cli_exposes_only_canonical_dag(monkeypatch):
    print("=== Test 4: Canonical CLI contract ===")
    runner = CliRunner()

    help_result = runner.invoke(cli, ["--help"])
    assert help_result.exit_code == 0
    assert "run-dag" in help_result.output
    for legacy_command in (
        "build-canonical",
        "process-chunks",
        "sync-qdrant",
        "cleanup-orphans",
        "run-pipeline",
    ):
        assert legacy_command not in help_result.output

    async def acknowledged_run(request):
        assert str(request.source_id) == "c7ad47e2-41a1-5a88-8a88-bc3c0b9c0638"
        assert request.staging_collection == "world_lore__v20260906"
        return IngestionRunResult(
            job_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            release_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            downloaded_pages=1,
            parsed_pages=1,
            parent_documents=1,
            staged_chunks=1,
            acknowledged_vectors=1,
            parent_manifest_checksum="parent-checksum",
            vector_manifest_checksum="vector-checksum",
        )

    monkeypatch.setattr(ingestion_cli, "run_application_dag", acknowledged_run)
    result = runner.invoke(
        cli,
        [
            "run-dag",
            "--source-id",
            "c7ad47e2-41a1-5a88-8a88-bc3c0b9c0638",
            "--staging-collection",
            "world_lore__v20260906",
        ],
    )
    assert result.exit_code == 0
    assert "[ACKNOWLEDGED]" in result.output
    print("  PASS\n")


if __name__ == "__main__":
    test_state_db_basic()
    test_orphan_detection()
    test_collection_mapping()
    print("=" * 55)
    print("DIRECT STORAGE CHECKS PASSED")
    print("=" * 55)
