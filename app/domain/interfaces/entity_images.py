"""Ports of the entity image flow (ING-019)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain.ingestion.entity_images import ImageInfo, ImageRecord, InspectedImage


class ImageRejectedError(ValueError):
    """The file is unsafe or not what the wiki declared; it must not be stored."""


class ImageDownloadError(RuntimeError):
    """The file could not be fetched this run; a later run may succeed."""


class IImageSource(Protocol):
    async def image_info(self, names: Sequence[str]) -> list[ImageInfo]: ...

    async def download(self, url: str) -> bytes: ...


class IImageInspector(Protocol):
    def inspect(self, content: bytes, declared_mime: str) -> InspectedImage: ...

    def display_copy(self, content: bytes) -> bytes: ...


class IImageVault(Protocol):
    def has(self, record: ImageRecord) -> bool: ...

    def save(self, sha256: str, mime: str, original: bytes, display: bytes) -> tuple[str, str]:
        """Store both copies by content hash; returns (original path, display path)."""
        ...

    def load_index(self) -> dict[str, ImageRecord]: ...

    def save_index(self, records: Sequence[ImageRecord]) -> None: ...
