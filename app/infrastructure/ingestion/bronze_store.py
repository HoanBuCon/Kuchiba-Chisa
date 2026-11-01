"""Immutable bronze store: one gzip JSON per (page_id, revid, render hash), relative keys."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from app.domain.interfaces.wiki_ingestion import ParsedPage

SCHEMA_VERSION = 1


def render_hash(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


class FileBronzeStore:
    """Keys are relative to the store root so artifacts move between machines (ING-007)."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, page: ParsedPage) -> str:
        key = f"bronze/{page.page_id}/{page.revid}-{render_hash(page.html)[:16]}.json.gz"
        target = self._root / key
        if target.exists():
            return key
        record = {
            "schema_version": SCHEMA_VERSION,
            **asdict(page),
            "fetched_at": page.fetched_at.isoformat(),
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(gzip.compress(json.dumps(record, ensure_ascii=False).encode("utf-8")))
        os.replace(temporary, target)
        return key

    def load(self, key: str) -> dict:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise ValueError("bronze key escapes the store root")
        return json.loads(gzip.decompress(path.read_bytes()))
