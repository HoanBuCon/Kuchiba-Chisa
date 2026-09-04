"""Contained, atomic raw-revision storage for the application ingestion DAG."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import uuid
from pathlib import Path


class RawStoragePathError(ValueError):
    """Raised when a caller supplies a path outside the raw-storage namespace."""


class FileRawStorage:
    """Persist immutable raw revisions without accepting arbitrary filesystem paths.

    The returned opaque URI is derived from the page identifier and content digest;
    callers cannot use titles or relative paths to select a file during reads.
    """

    _URI_PATTERN = re.compile(r"^raw://(?P<page_id>[1-9][0-9]*)/(?P<digest>[0-9a-f]{64})\.wikitext$")

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir.expanduser().resolve()

    async def save_raw_page(self, title: str, page_id: int, content: str) -> str:
        """Atomically write a content-addressed revision and return its opaque URI."""
        del title  # Source titles never participate in filesystem path construction.
        if page_id < 1:
            raise ValueError("page_id must be positive")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        uri = f"raw://{page_id}/{digest}.wikitext"
        await asyncio.to_thread(self._write_if_absent, page_id, digest, content)
        return uri

    async def read_raw_page(self, file_path: str) -> str:
        """Read only a URI issued by this storage implementation."""
        page_id, digest = self._parse_uri(file_path)
        return await asyncio.to_thread(self._read, page_id, digest)

    def _parse_uri(self, uri: str) -> tuple[int, str]:
        match = self._URI_PATTERN.fullmatch(uri)
        if match is None:
            raise RawStoragePathError("raw storage URI is invalid")
        return int(match.group("page_id")), match.group("digest")

    def _target_path(self, page_id: int, digest: str) -> Path:
        candidate = (self._root_dir / str(page_id) / f"{digest}.wikitext").resolve()
        try:
            candidate.relative_to(self._root_dir)
        except ValueError as exc:  # Defence in depth if the storage root changes unexpectedly.
            raise RawStoragePathError("raw storage target escapes its configured root") from exc
        return candidate

    def _write_if_absent(self, page_id: int, digest: str, content: str) -> None:
        target = self._target_path(page_id, digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _read(self, page_id: int, digest: str) -> str:
        target = self._target_path(page_id, digest)
        try:
            return target.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise RawStoragePathError("raw revision does not exist") from exc
