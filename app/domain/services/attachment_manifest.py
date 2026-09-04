"""Server-owned image attachment manifests (SEC-06 / FR-RAG-012)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.config.settings import settings

_IMAGE_ID = re.compile(r"^[a-f0-9]{32}$")
_MAX_ATTACHMENTS = 2
_MIN_RETRIEVAL_SCORE = 0.68


@dataclass(frozen=True, slots=True)
class AttachmentManifest:
    """A delivery reference produced only from server-retrieved image evidence."""

    attachment_id: str
    delivery_url: str


def resolve_attachment_manifests(
    retrieved_images: Sequence[Mapping[str, Any]],
) -> list[AttachmentManifest]:
    """Return allowlisted manifests; LLM fields are deliberately not an input."""
    manifests: list[AttachmentManifest] = []
    for image in retrieved_images:
        if len(manifests) >= _MAX_ATTACHMENTS:
            break
        image_id = image.get("image_id")
        url = image.get("url")
        score = image.get("score")
        if not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id):
            continue
        if not isinstance(url, str) or not _is_server_owned_url(url, image_id):
            continue
        if not isinstance(score, int | float) or isinstance(score, bool):
            continue
        if score < _MIN_RETRIEVAL_SCORE:
            continue
        manifests.append(AttachmentManifest(attachment_id=image_id, delivery_url=url))
    return manifests


def _is_server_owned_url(url: str, image_id: str) -> bool:
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment or not parsed.path.endswith(f"/{image_id}.webp"):
        return False

    local_base = urlsplit(settings.VISION_STORAGE_BASE_URL).path.rstrip("/")
    if not parsed.scheme and not parsed.netloc:
        return parsed.path.startswith(f"{local_base}/") and "/../" not in parsed.path

    if parsed.scheme != "https":
        return False
    if settings.VISION_S3_PUBLIC_DOMAIN:
        public_base = urlsplit(settings.VISION_S3_PUBLIC_DOMAIN).geturl().rstrip("/")
        if url.startswith(f"{public_base}/uploads/"):
            return True
    if settings.CLOUDINARY_CLOUD_NAME:
        cloud_path = f"/{settings.CLOUDINARY_CLOUD_NAME}/image/upload/chisa_vision/"
        return parsed.netloc == "res.cloudinary.com" and parsed.path.startswith(cloud_path)
    return False
