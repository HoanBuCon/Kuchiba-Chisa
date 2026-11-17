"""Entity image links and serving: signed server URLs, never the wiki's own host (KNW-010)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.security.signed_image_url import ImageUrlSigner
from app.domain.ingestion.entity_images import ImageRecord
from app.domain.ingestion.entity_linking import fold_for_matching
from app.domain.interfaces.entity_images import IImageCatalog

FAIR_USE_NOTE = "Hình ảnh thuộc về chủ sở hữu; Chisa dùng theo fair use để minh hoạ, kèm nguồn."
DISPLAY_MIME = "image/webp"
IMAGE_ROUTE_PREFIX = "/api/v2/images"


@dataclass(frozen=True)
class ServedImage:
    content: bytes
    mime: str


class InvalidImageLinkError(PermissionError):
    """The signature is wrong or has expired."""


class EntityImageService:
    def __init__(self, catalog: IImageCatalog, signer: ImageUrlSigner, url_prefix: str) -> None:
        self._catalog = catalog
        self._signer = signer
        self._prefix = url_prefix
        self._by_title: dict[str, list[ImageRecord]] | None = None
        self._by_sha: dict[str, ImageRecord] = {}

    def for_entity(self, title: str) -> dict[str, Any] | None:
        """The entity's main image as a client-safe object, or None when it has none."""
        records = self._index().get(fold_for_matching(title))
        if not records:
            return None
        record = min(records, key=lambda item: (not _names_entity(item, title), item.name))
        return {
            "url": self._url(record.sha256, original=False),
            "original_url": self._url(record.sha256, original=True),
            "source_page": record.file_page_url,
            "attribution": FAIR_USE_NOTE,
        }

    def serve(self, sha256: str, *, original: bool, expires: int, signature: str) -> ServedImage:
        if not self._signer.verify(sha256, original=original, expires=expires, signature=signature):
            raise InvalidImageLinkError(sha256)
        self._index()
        record = self._by_sha.get(sha256)
        if record is None:
            raise FileNotFoundError(sha256)
        path = record.original_path if original else record.display_path
        content = self._catalog.read(path)
        if content is None:
            raise FileNotFoundError(sha256)
        return ServedImage(content, record.mime if original else DISPLAY_MIME)

    def _url(self, sha256: str, *, original: bool) -> str:
        expires, signature = self._signer.sign(sha256, original=original)
        query = f"expires={expires}&sig={signature}" + ("&original=1" if original else "")
        return f"{self._prefix}/{sha256}?{query}"

    def _index(self) -> dict[str, list[ImageRecord]]:
        """Loaded once: a new ingestion run is picked up on the next restart, like the corpus."""
        if self._by_title is None:
            by_title: dict[str, list[ImageRecord]] = {}
            for record in self._catalog.load_index().values():
                self._by_sha[record.sha256] = record
                for title in record.entities:
                    by_title.setdefault(fold_for_matching(title), []).append(record)
            self._by_title = by_title
        return self._by_title


def _names_entity(record: ImageRecord, title: str) -> bool:
    return fold_for_matching(title) in fold_for_matching(record.name)
