"""
Canonical Dataset Writer — Streaming JSONL persistence for canonical.jsonl.

Implements Stage 5A (Canonicalization output) of the Architecture Document.

File location:
    data/canonical/canonical.jsonl

Features:
    1. Streaming JSONL writer: Write CanonicalPage records line-by-line without loading full corpus in RAM.
    2. File creation & directory auto-provisioning.
    3. Idempotent upsert / append modes.
    4. Streaming reader (generator): Iterates over canonical.jsonl yielding CanonicalPage instances.
    5. Atomic flushing and stats tracking.
"""

from __future__ import annotations

from collections.abc import Generator, Iterable
from pathlib import Path
from typing import Any

import structlog

from app.infrastructure.ingestion.models.canonical_page import CanonicalPage

logger = structlog.get_logger(__name__)

DEFAULT_CANONICAL_PATH = Path("data/canonical/canonical.jsonl")


class CanonicalWriter:
    """
    Streaming writer for canonical.jsonl files.

    Ensures target directory exists, writes single or batch records,
    and flushes changes efficiently.

    Example::

        writer = CanonicalWriter("data/canonical/canonical.jsonl")
        writer.write_page(page)
        writer.close()
    """

    def __init__(
        self,
        filepath: str | Path = DEFAULT_CANONICAL_PATH,
        mode: str = "a",
    ):
        """
        Initialize the CanonicalWriter.

        Args:
            filepath: Path to canonical.jsonl file.
            mode: File open mode ('w' for overwrite, 'a' for append).
        """
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.filepath, mode=mode, encoding="utf-8")
        self._written_count = 0

    def write_page(self, page: CanonicalPage) -> None:
        """
        Write a single CanonicalPage record to JSONL.

        Args:
            page: CanonicalPage instance to serialize and append.
        """
        line = page.model_dump_json(by_alias=True)
        self._file.write(line + "\n")
        self._written_count += 1

    def write_pages(self, pages: Iterable[CanonicalPage]) -> int:
        """
        Write a batch of CanonicalPage records to JSONL.

        Args:
            pages: Iterable of CanonicalPage instances.

        Returns:
            Number of records written.
        """
        count = 0
        for page in pages:
            self.write_page(page)
            count += 1
        self.flush()
        return count

    def flush(self) -> None:
        """Flush the underlying file buffer."""
        self._file.flush()

    def close(self) -> None:
        """Flush and close the file."""
        if not self._file.closed:
            self.flush()
            self._file.close()
            logger.info(
                "canonical_writer_closed",
                filepath=str(self.filepath),
                records_written=self._written_count,
            )

    def __enter__(self) -> CanonicalWriter:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


def write_canonical_stream(
    pages: Iterable[CanonicalPage],
    filepath: str | Path = DEFAULT_CANONICAL_PATH,
    mode: str = "w",
) -> int:
    """
    Convenience function to write an iterable of CanonicalPages to JSONL.

    Args:
        pages: Iterable of CanonicalPage instances.
        filepath: Path to output JSONL file.
        mode: 'w' for overwrite (default), 'a' for append.

    Returns:
        Number of records written.
    """
    with CanonicalWriter(filepath=filepath, mode=mode) as writer:
        return writer.write_pages(pages)


def read_canonical_stream(
    filepath: str | Path = DEFAULT_CANONICAL_PATH,
) -> Generator[CanonicalPage, None, None]:
    """
    Streaming reader yielding CanonicalPage instances from canonical.jsonl.

    Memory-efficient generator: processes one record at a time.

    Args:
        filepath: Path to canonical.jsonl file.

    Yields:
        CanonicalPage objects parsed from line JSON.
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning("canonical_file_not_found", filepath=str(path))
        return

    count = 0
    with open(path, mode="r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue

            try:
                page = CanonicalPage.model_validate_json(line_str)
                count += 1
                yield page
            except Exception as exc:
                logger.error(
                    "canonical_read_error",
                    line=line_num,
                    error=str(exc),
                    filepath=str(path),
                )
                continue

    logger.debug("canonical_stream_read_complete", count=count, filepath=str(path))
