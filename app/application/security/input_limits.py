"""Centralized, pre-decode admission policy for untrusted chat input."""

from __future__ import annotations

import re
from typing import Any

from app.config.settings import settings

_DATA_IMAGE_URI = re.compile(r"^data:image/[a-zA-Z0-9+.-]+;base64,", re.IGNORECASE)
_BASE64_PAYLOAD = re.compile(r"[A-Za-z0-9+/]*={0,2}")


class InputLimitError(ValueError):
    """The request exceeds a configured resource boundary."""


class InputLimitPolicy:
    """Applies resource limits before base64 decoding or image fetching."""

    @staticmethod
    def max_base64_chars() -> int:
        return 4 * ((settings.VISION_MAX_IMAGE_BYTES + 2) // 3)

    @classmethod
    def validate_images(cls, images: list[str] | None) -> None:
        if not images:
            return
        if len(images) > settings.VISION_MAX_IMAGES:
            raise InputLimitError("too many images")

        total_decoded_bytes = 0
        for image in images:
            if not isinstance(image, str):
                continue
            item = image.strip()
            if item.startswith(("https://", "http://")):
                if len(item) > settings.VISION_MAX_IMAGE_URL_CHARS:
                    raise InputLimitError("image URL is too long")
                continue

            encoded_payload = item
            if item.startswith("data:"):
                match = _DATA_IMAGE_URI.match(item)
                if match is None:
                    raise InputLimitError("invalid image data URI")
                encoded_payload = item[match.end() :]

            if not encoded_payload or len(encoded_payload) % 4 or not _BASE64_PAYLOAD.fullmatch(
                encoded_payload
            ):
                raise InputLimitError("invalid base64 image payload")
            if len(encoded_payload) > cls.max_base64_chars():
                raise InputLimitError("base64 image payload is too large")
            estimated_decoded_bytes = (len(encoded_payload.rstrip("=")) * 3) // 4
            if estimated_decoded_bytes > settings.VISION_MAX_IMAGE_BYTES:
                raise InputLimitError("decoded image payload is too large")
            total_decoded_bytes += estimated_decoded_bytes

        if total_decoded_bytes > settings.VISION_MAX_TOTAL_DECODED_BYTES:
            raise InputLimitError("aggregate decoded image payload is too large")

    @staticmethod
    def validate_community_history(messages: list[Any]) -> None:
        if len(messages) > settings.COMMUNITY_MAX_HISTORY_MESSAGES:
            raise InputLimitError("too many community history messages")
