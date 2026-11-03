"""Entity images come from structured infobox data, never from page sections (ING-019, ADR-0003)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

FAIR_USE = "fair_use"


@dataclass(frozen=True)
class ImagePolicy:
    allowed_hosts: tuple[str, ...]
    excluded_files: tuple[str, ...] = ()
    max_bytes: int = 25 * 1024 * 1024
    max_pixels: int = 60_000_000
    display_edge: int = 1024
    batch_size: int = 50
    max_failure_ratio: float = 0.02


@dataclass(frozen=True)
class ImageInfo:
    name: str
    url: str
    sha1: str
    size: int
    mime: str
    file_page_url: str
    revid: int


@dataclass(frozen=True)
class InspectedImage:
    mime: str
    width: int
    height: int


@dataclass(frozen=True)
class ImageRecord:
    name: str
    sha1: str
    sha256: str
    mime: str
    width: int
    height: int
    size: int
    original_path: str
    display_path: str
    file_page_url: str
    revid: int
    entities: tuple[str, ...]
    license: str = FAIR_USE


@dataclass(frozen=True)
class ImageReport:
    referenced: int = 0
    downloaded: int = 0
    reused: int = 0
    failures: dict[str, str] = field(default_factory=dict)
    # Files on the wiki that no entity references any more, kept until cleanup.
    orphans: int = 0
    max_failure_ratio: float = 0.0

    @property
    def passed(self) -> bool:
        return len(self.failures) <= self.referenced * self.max_failure_ratio


def _image_items(value: Any) -> Iterator[dict[str, Any]]:
    """Portable infobox items nest inside groups and panels, so images can sit at any depth."""
    if isinstance(value, list):
        for item in value:
            yield from _image_items(item)
    elif isinstance(value, dict):
        if value.get("type") == "image" and isinstance(value.get("data"), list):
            yield from (image for image in value["data"] if isinstance(image, dict))
        else:
            yield from _image_items(list(value.values()))


def infobox_image_files(properties: Mapping[str, str]) -> tuple[str, ...]:
    """File names in the page's infoboxes, skipping videos and malformed property data."""
    try:
        infoboxes = json.loads(properties.get("infoboxes") or "[]")
    except json.JSONDecodeError:
        return ()
    names = (
        image.get("name")
        for image in _image_items(infoboxes)
        if str(image.get("isVideo", False)).lower() != "true"
    )
    return tuple(dict.fromkeys(name for name in names if isinstance(name, str) and name))


def entities_by_file(
    pages: Iterable[tuple[str, Mapping[str, str]]], excluded: Iterable[str] = ()
) -> dict[str, tuple[str, ...]]:
    """Map each file to the entities showing it; `pages` are (title, page properties)."""
    skip = frozenset(excluded)
    linked: dict[str, list[str]] = {}
    for title, properties in pages:
        for name in infobox_image_files(properties):
            if name not in skip:
                linked.setdefault(name, []).append(title)
    return {name: tuple(titles) for name, titles in linked.items()}
