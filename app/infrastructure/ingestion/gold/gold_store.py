"""File gold store: `gold/<version>/` with gzip JSONL, a manifest and checksums (design L3)."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.knowledge import KnowledgeBase

CHUNKS_FILE = "chunks.jsonl.gz"
DUPLICATES_FILE = "duplicate_of.json.gz"
KNOWLEDGE_FILE = "knowledge.json.gz"
MANIFEST_FILE = "manifest.json"


def _gzip_bytes(payload: bytes) -> bytes:
    # mtime=0 keeps identical content byte-identical, so checksums compare across runs.
    return gzip.compress(payload, mtime=0)


class FileGoldStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._gold = root / "gold"

    def next_version(self, day: date) -> str:
        prefix = f"{day:%Y.%m.%d}-"
        taken = (
            {path.name for path in self._gold.glob(f"{prefix}*")} if self._gold.exists() else set()
        )
        number = 1
        while f"{prefix}{number}" in taken:
            number += 1
        return f"{prefix}{number}"

    def write(
        self,
        version: str,
        chunks: Sequence[Chunk],
        duplicate_of: Mapping[str, int],
        knowledge: KnowledgeBase,
        manifest: Mapping[str, Any],
    ) -> str:
        target = self._gold / version
        if target.exists():
            raise FileExistsError(f"corpus version {version} already exists")
        staging = self._gold / f".{version}.tmp"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        lines = "\n".join(json.dumps(asdict(chunk), ensure_ascii=False) for chunk in chunks)
        files = {
            CHUNKS_FILE: _gzip_bytes(lines.encode("utf-8")),
            DUPLICATES_FILE: _gzip_bytes(
                json.dumps(dict(duplicate_of), sort_keys=True).encode("utf-8")
            ),
            KNOWLEDGE_FILE: _gzip_bytes(
                json.dumps(asdict(knowledge), ensure_ascii=False).encode("utf-8")
            ),
        }
        for name, content in files.items():
            (staging / name).write_bytes(content)
        checksums = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
        document = json.dumps({**manifest, "checksums": checksums}, ensure_ascii=False, indent=1)
        (staging / MANIFEST_FILE).write_text(document, encoding="utf-8")
        # A reader sees a complete version or none at all.
        os.replace(staging, target)
        return f"gold/{version}"
