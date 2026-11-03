"""Whole-wiki infoboxes kept beside the gold corpus, with relative paths only (ING-007, ING-014)."""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping
from pathlib import Path

from app.domain.ingestion.knowledge import StructuredPage

STRUCTURED_PATH = "structured/infoboxes.json.gz"


class FileStructuredStore:
    def __init__(self, root: Path) -> None:
        self._path = root / STRUCTURED_PATH

    def load(self) -> dict[int, StructuredPage]:
        if not self._path.is_file():
            return {}
        raw = json.loads(gzip.decompress(self._path.read_bytes()))
        return {
            int(page_id): StructuredPage(
                page["revid"], tuple(page["infoboxes"]), tuple(page.get("redirects", ()))
            )
            for page_id, page in raw.items()
        }

    def save(self, pages: Mapping[int, StructuredPage]) -> None:
        records = {
            str(page_id): {
                "revid": page.revid,
                "infoboxes": list(page.infoboxes),
                "redirects": list(page.redirects),
            }
            for page_id, page in sorted(pages.items())
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_bytes(
            gzip.compress(json.dumps(records, ensure_ascii=False).encode("utf-8"))
        )
        temporary.replace(self._path)
