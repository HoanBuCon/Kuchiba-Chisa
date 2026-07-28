"""
Cleanup script for clearing all crawled data, canonical/chunk datasets, and SQLite state DB.

Usage:
    python scripts/clear_ingestion_data.py
    python scripts/clear_ingestion_data.py --keep-raw  # Keep raw_wiki files, clear only pipeline outputs
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Force UTF-8 on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def clear_ingestion_data(clear_raw: bool = True) -> None:
    """Clear crawled raw files, canonical datasets, chunk datasets, and SQLite state DB."""
    print("==================================================")
    print("🧹 Kuchiba Chisa — Ingestion Data Cleanup")
    print("==================================================")

    # 1. Clear data/raw_wiki
    raw_dir = Path("data/raw_wiki")
    if raw_dir.exists() and clear_raw:
        count = 0
        for item in raw_dir.iterdir():
            if item.is_file() and item.name != ".gitkeep":
                item.unlink()
                count += 1
        print(f"  ✓ Cleared {count} raw files from: {raw_dir}")
    elif not clear_raw:
        print(f"  * Preserved raw files in: {raw_dir}")

    # 2. Clear data/canonical
    canonical_file = Path("data/canonical/canonical.jsonl")
    if canonical_file.exists():
        canonical_file.unlink()
        print(f"  ✓ Deleted Canonical dataset: {canonical_file}")

    # 3. Clear data/chunks
    chunks_file = Path("data/chunks/chunks.jsonl")
    if chunks_file.exists():
        chunks_file.unlink()
        print(f"  ✓ Deleted Chunks dataset: {chunks_file}")

    # 4. Clear data/ingestion.sqlite
    db_file = Path("data/ingestion.sqlite")
    if db_file.exists():
        db_file.unlink()
        print(f"  ✓ Deleted SQLite State DB: {db_file}")

    # 5. Clear scratch test folders
    scratch_dir = Path("scratch")
    if scratch_dir.exists():
        for test_folder in ("test_canonical", "test_cli", "test_storage"):
            target = scratch_dir / test_folder
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                print(f"  ✓ Cleaned temporary scratch dir: {target}")

    print("==================================================")
    print("✨ Ingestion data cleanup complete!")
    print("==================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clear ingestion pipeline data")
    parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="Keep raw_wiki files, clear only canonical/chunk datasets and SQLite DB.",
    )
    args = parser.parse_args()

    clear_ingestion_data(clear_raw=not args.keep_raw)
