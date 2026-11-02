"""File gold store: `gold/<version>/` with gzip JSONL, a manifest and checksums (design L3)."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.knowledge import (
    Alias,
    Entity,
    GlossaryTerm,
    KnowledgeBase,
    LocationEdge,
    Quest,
)
from app.domain.ingestion.units import Collection

CHUNKS_FILE = "chunks.jsonl.gz"
DUPLICATES_FILE = "duplicate_of.json.gz"
KNOWLEDGE_FILE = "knowledge.json.gz"
MANIFEST_FILE = "manifest.json"
VERSION = re.compile(r"\d{4}\.\d{2}\.\d{2}-\d+")


def _version_order(version: str) -> tuple[str, int]:
    day, number = version.rsplit("-", 1)
    return day, int(number)


def _chunk(record: dict[str, Any]) -> Chunk:
    return Chunk(
        **{
            **record,
            "collection": Collection(record["collection"]),
            "section": tuple(record["section"]),
            "entities": tuple(record["entities"]),
        }
    )


def _knowledge(record: dict[str, Any]) -> KnowledgeBase:
    def tuples(item: dict[str, Any]) -> dict[str, Any]:
        return {k: tuple(v) if isinstance(v, list) else v for k, v in item.items()}

    return KnowledgeBase(
        entities=tuple(Entity(**item) for item in record["entities"]),
        aliases=tuple(Alias(**tuples(item)) for item in record["aliases"]),
        glossary=tuple(GlossaryTerm(**tuples(item)) for item in record["glossary"]),
        quests=tuple(Quest(**tuples(item)) for item in record["quests"]),
        locations=tuple(LocationEdge(**item) for item in record["locations"]),
    )


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

    def latest_version(self) -> str | None:
        versions = [p.name for p in self._gold.glob("*") if VERSION.fullmatch(p.name)]
        return max(versions, key=_version_order) if versions else None

    def read_chunks(self, version: str) -> list[Chunk]:
        raw = gzip.decompress((self._gold / version / CHUNKS_FILE).read_bytes())
        return [_chunk(json.loads(line)) for line in raw.decode("utf-8").splitlines()]

    def read_manifest(self, version: str) -> dict[str, Any]:
        return json.loads((self._gold / version / MANIFEST_FILE).read_text(encoding="utf-8"))

    def read_knowledge(self, version: str) -> KnowledgeBase:
        raw = gzip.decompress((self._gold / version / KNOWLEDGE_FILE).read_bytes())
        return _knowledge(json.loads(raw))

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
