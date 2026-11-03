"""Pillow vetting and content-addressed storage of entity images (ING-019, ADR-0003)."""

from __future__ import annotations

import io
import json
import warnings
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

import yaml
from PIL import Image, UnidentifiedImageError

from app.domain.ingestion.entity_images import ImagePolicy, ImageRecord, InspectedImage
from app.domain.interfaces.entity_images import ImageRejectedError
from app.infrastructure.ingestion.silver.rules import CONFIG_DIR

MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}
EXTENSION_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
DISPLAY_QUALITY = 85
IMAGES_DIR = "images"
INDEX_FILE = "index.json"


def load_image_policy(path: Path = CONFIG_DIR / "images.yaml") -> ImagePolicy:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["allowed_hosts"] = tuple(raw["allowed_hosts"])
    raw["excluded_files"] = tuple(raw["excluded_files"])
    return ImagePolicy(**raw)


class PillowImageInspector:
    def __init__(self, policy: ImagePolicy) -> None:
        self._policy = policy

    def inspect(self, content: bytes, declared_mime: str) -> InspectedImage:
        if len(content) > self._policy.max_bytes:
            raise ImageRejectedError("file exceeds the byte limit")
        try:
            # A bomb is refused from its header, before any pixel is decoded.
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as image:
                    width, height = image.size
                    image_format = image.format
                    self._check_pixels(width, height)
                    image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
            raise ImageRejectedError("file is not a readable image") from error
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise ImageRejectedError("image is a decompression bomb") from error
        mime = MIME_BY_FORMAT.get(image_format or "")
        if mime is None:
            raise ImageRejectedError("image format is not allowed")
        if mime != declared_mime:
            raise ImageRejectedError("declared type does not match the file")
        return InspectedImage(mime=mime, width=width, height=height)

    def display_copy(self, content: bytes) -> bytes:
        """The first frame as WebP, shrunk but never enlarged."""
        edge = self._policy.display_edge
        try:
            with Image.open(io.BytesIO(content)) as image:
                clear = "A" in image.getbands() or "transparency" in image.info
                frame = image.convert("RGBA" if clear else "RGB")
        except OSError as error:
            # verify() does not decode pixels, so damage in the body first shows up here.
            raise ImageRejectedError("image data is damaged") from error
        frame.thumbnail((edge, edge))
        output = io.BytesIO()
        frame.save(output, format="WEBP", quality=DISPLAY_QUALITY)
        return output.getvalue()

    def _check_pixels(self, width: int, height: int) -> None:
        if width * height > self._policy.max_pixels:
            raise ImageRejectedError("image exceeds the pixel limit")


class FileImageVault:
    """Paths are relative to the ingestion root (ING-007), and images need no backup."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _original(self, sha256: str, mime: str) -> str:
        return f"{IMAGES_DIR}/original/{sha256[:2]}/{sha256}.{EXTENSION_BY_MIME[mime]}"

    def _display(self, sha256: str) -> str:
        return f"{IMAGES_DIR}/display/{sha256[:2]}/{sha256}.webp"

    def _write(self, relative: str, content: bytes) -> None:
        target = self._root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(target)

    def has(self, record: ImageRecord) -> bool:
        return (self._root / record.original_path).is_file() and (
            self._root / record.display_path
        ).is_file()

    def save(self, sha256: str, mime: str, original: bytes, display: bytes) -> tuple[str, str]:
        original_path, display_path = self._original(sha256, mime), self._display(sha256)
        self._write(original_path, original)
        self._write(display_path, display)
        return original_path, display_path

    def load_index(self) -> dict[str, ImageRecord]:
        path = self._root / IMAGES_DIR / INDEX_FILE
        if not path.is_file():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = (ImageRecord(**{**r, "entities": tuple(r["entities"])}) for r in raw)
        return {record.name: record for record in records}

    def save_index(self, records: Sequence[ImageRecord]) -> None:
        ordered = sorted(records, key=lambda record: record.name)
        text = json.dumps([asdict(record) for record in ordered], ensure_ascii=False, indent=1)
        self._write(f"{IMAGES_DIR}/{INDEX_FILE}", text.encode("utf-8"))
