"""
SQLite State Management DB — Incremental Ingestion Tracker & Orphan Cleanup (§1.1 & §10).

Database location:
    data/ingestion.sqlite

Table schema:
    CREATE TABLE IF NOT EXISTS ingestion_state (
        page_id INTEGER PRIMARY KEY,
        canonical_slug TEXT NOT NULL,
        title TEXT NOT NULL,
        page_type TEXT NOT NULL,
        text_hash TEXT NOT NULL,
        chunk_count INTEGER DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'PROCESSED'
    );

Features:
    1. Incremental Update Check: Skip re-ingesting pages whose text_hash is unchanged.
    2. Orphan Page Cleanup: Detect pages present in DB but removed from Wiki, enabling atomic Qdrant chunk purge.
    3. Pipeline Statistics: Track total pages, chunk counts, and processing state.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

import structlog
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger(__name__)

DEFAULT_DB_PATH = Path("data/ingestion.sqlite")


class PageStateRecord(BaseModel):
    """DB Record representing the ingestion state of a single Wiki page."""

    model_config = ConfigDict(extra="ignore")

    page_id: int = Field(..., description="MediaWiki page ID (PRIMARY KEY).")
    canonical_slug: str = Field(..., description="URL-safe slug.")
    title: str = Field(..., description="Page title.")
    page_type: str = Field(..., description="Page type classification.")
    text_hash: str = Field(..., description="SHA-256 hash of raw/canonical content.")
    chunk_count: int = Field(default=0, ge=0, description="Number of vector chunks generated.")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp.")
    status: str = Field(default="PROCESSED", description="State: PROCESSED, QUARANTINED, DELETED.")


class IngestionStateDB:
    """
    SQLite state management database wrapper for incremental ingestion and orphan cleanup.
    """

    def __init__(self, db_path: Union[str, Path] = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_state (
                    page_id INTEGER PRIMARY KEY,
                    canonical_slug TEXT NOT NULL,
                    title TEXT NOT NULL,
                    page_type TEXT NOT NULL,
                    text_hash TEXT NOT NULL,
                    chunk_count INTEGER DEFAULT 0,
                    last_updated TEXT NOT NULL,
                    status TEXT DEFAULT 'PROCESSED'
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_canonical_slug ON ingestion_state(canonical_slug);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_page_status ON ingestion_state(status);"
            )
            conn.commit()
            logger.debug("state_db_initialized", db_path=str(self.db_path))

    def upsert_page_state(self, record: PageStateRecord) -> None:
        """Insert or update a page state record."""
        updated_iso = record.last_updated.isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ingestion_state (
                    page_id, canonical_slug, title, page_type, text_hash, chunk_count, last_updated, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(page_id) DO UPDATE SET
                    canonical_slug=excluded.canonical_slug,
                    title=excluded.title,
                    page_type=excluded.page_type,
                    text_hash=excluded.text_hash,
                    chunk_count=excluded.chunk_count,
                    last_updated=excluded.last_updated,
                    status=excluded.status;
                """,
                (
                    record.page_id,
                    record.canonical_slug,
                    record.title,
                    record.page_type,
                    record.text_hash,
                    record.chunk_count,
                    updated_iso,
                    record.status,
                ),
            )
            conn.commit()
            logger.debug("page_state_upserted", page_id=record.page_id, slug=record.canonical_slug)

    def get_page_state(self, page_id: int) -> Optional[PageStateRecord]:
        """Fetch a page state record by page_id."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM ingestion_state WHERE page_id = ?;", (page_id,)
            ).fetchone()
            if not row:
                return None

            return PageStateRecord(
                page_id=row["page_id"],
                canonical_slug=row["canonical_slug"],
                title=row["title"],
                page_type=row["page_type"],
                text_hash=row["text_hash"],
                chunk_count=row["chunk_count"],
                last_updated=datetime.fromisoformat(row["last_updated"]),
                status=row["status"],
            )

    def is_page_unchanged(self, page_id: int, current_hash: str) -> bool:
        """Check if page text hash matches stored record (skip re-embedding if unchanged)."""
        state = self.get_page_state(page_id)
        if not state:
            return False
        return state.text_hash == current_hash and state.status == "PROCESSED"

    def detect_orphans(self, active_page_ids: Set[int]) -> List[PageStateRecord]:
        """
        Detect orphan pages stored in DB that are no longer in active_page_ids.

        Enables Orphan Cleanup (deleting old vector points when wiki pages are deleted).

        Args:
            active_page_ids: Set of page IDs present in the latest crawl/canonical dataset.

        Returns:
            List of PageStateRecord objects for pages that have been deleted/orphaned.
        """
        orphans: List[PageStateRecord] = []
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ingestion_state WHERE status = 'PROCESSED';"
            ).fetchall()

            for row in rows:
                p_id = row["page_id"]
                if p_id not in active_page_ids:
                    rec = PageStateRecord(
                        page_id=row["page_id"],
                        canonical_slug=row["canonical_slug"],
                        title=row["title"],
                        page_type=row["page_type"],
                        text_hash=row["text_hash"],
                        chunk_count=row["chunk_count"],
                        last_updated=datetime.fromisoformat(row["last_updated"]),
                        status="DELETED",
                    )
                    orphans.append(rec)

        logger.info("orphan_pages_detected", count=len(orphans))
        return orphans

    def delete_page_state(self, page_id: int) -> None:
        """Delete a page record from SQLite after orphan purge."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM ingestion_state WHERE page_id = ?;", (page_id,))
            conn.commit()
            logger.info("page_state_deleted", page_id=page_id)

    def get_summary_stats(self) -> Dict[str, Union[int, float, str]]:
        """Return summary statistics of ingestion state DB."""
        with self._get_connection() as conn:
            total_pages = conn.execute(
                "SELECT COUNT(*) FROM ingestion_state WHERE status = 'PROCESSED';"
            ).fetchone()[0]
            total_chunks = conn.execute(
                "SELECT SUM(chunk_count) FROM ingestion_state WHERE status = 'PROCESSED';"
            ).fetchone()[0] or 0
            quarantined = conn.execute(
                "SELECT COUNT(*) FROM ingestion_state WHERE status = 'QUARANTINED';"
            ).fetchone()[0]

            return {
                "total_processed_pages": total_pages,
                "total_chunks_stored": total_chunks,
                "quarantined_pages": quarantined,
                "db_path": str(self.db_path),
            }
