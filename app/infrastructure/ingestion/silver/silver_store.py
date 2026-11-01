"""File silver store: one gzip JSON per (page, silver key), relative paths (ING-007)."""

from __future__ import annotations

import gzip
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.domain.ingestion.documents import (
    Block,
    BlockKind,
    CanonicalDocument,
    DialogueTurn,
    GlossaryEntry,
    TurnKind,
)

SCHEMA_VERSION = 1


def document_to_dict(document: CanonicalDocument) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, **asdict(document)}


def document_from_dict(record: dict[str, Any]) -> CanonicalDocument:
    return CanonicalDocument(
        page_id=record["page_id"],
        title=record["title"],
        revid=record["revid"],
        family=record["family"],
        cleaner_version=record["cleaner_version"],
        blocks=tuple(_block(raw) for raw in record["blocks"]),
        infoboxes=tuple(record["infoboxes"]),
        glossary=tuple(GlossaryEntry(**entry) for entry in record["glossary"]),
        links=tuple(record["links"]),
        removed=dict(record["removed"]),
    )


def _block(raw: dict[str, Any]) -> Block:
    turns = tuple(
        DialogueTurn(TurnKind(t["kind"]), t["text"], t["speaker"], t["depth"]) for t in raw["turns"]
    )
    return Block(
        kind=BlockKind(raw["kind"]),
        section=tuple(raw["section"]),
        text=raw["text"],
        title=raw["title"],
        turns=turns,
        variant=raw["variant"],
    )


class FileSilverStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    @staticmethod
    def path_for(page_id: int, key: str) -> str:
        return f"silver/{page_id}/{key}.json.gz"

    def save(self, key: str, document: CanonicalDocument) -> str:
        path = self.path_for(document.page_id, key)
        target = self._root / path
        if target.exists():
            return path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        payload = json.dumps(document_to_dict(document), ensure_ascii=False).encode("utf-8")
        temporary.write_bytes(gzip.compress(payload))
        os.replace(temporary, target)
        return path

    def load(self, path: str) -> CanonicalDocument:
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root.resolve()):
            raise ValueError("silver path escapes the store root")
        return document_from_dict(json.loads(gzip.decompress(resolved.read_bytes())))
