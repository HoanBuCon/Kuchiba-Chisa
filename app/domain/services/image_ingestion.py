"""
Image Ingestion Service for Multimodal Vision in Kuchiba Chisa.
Location: app/domain/services/image_ingestion.py
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any

import httpx

from app.domain.interfaces.image_storage import IImageStorageProvider
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.storage.factory import get_image_storage_provider
from app.shared.security.vision_security import (
    ImageSanitizer,
    ImageValidationError,
    SecureImageFetcher,
    VisionSecurityError,
)

log = get_logger(__name__)


class ImageIngestionService:
    """
    Orchestrates the safe downloading, pure pixel sanitization,
    WebP conversion, thumbnail generation, and base64 payload preparation for LLM Vision.
    """

    def __init__(
        self,
        storage: IImageStorageProvider | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.storage = storage or get_image_storage_provider()
        self.http_client = http_client

    async def ingest_images(
        self,
        image_inputs: list[str],
        save_to_disk: bool = True,
        is_ephemeral: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Ingests a list of image inputs (either HTTP URLs or Base64 Data URIs).
        Returns a list of processed image metadata objects.
        """
        if not image_inputs:
            return []

        processed_images: list[dict[str, Any]] = []

        for idx, item in enumerate(image_inputs):
            item_str = str(item).strip()
            if not item_str:
                continue

            try:
                raw_bytes = await self._resolve_raw_bytes(item_str)
                if not raw_bytes:
                    continue

                # 1. Pure Pixel Sanitization & WebP conversion & EXIF stripping
                sanitized_result = await ImageSanitizer.sanitize_image(
                    raw_data=raw_bytes,
                    target_max_dim=1536,
                )

                # 2. Base64 Data URI for LLM Vision Payload
                b64_str = base64.b64encode(sanitized_result["sanitized_bytes"]).decode("utf-8")
                data_uri = f"data:{sanitized_result['mime_type']};base64,{b64_str}"

                # 3. Local Storage Management (if save_to_disk is enabled)
                if save_to_disk:
                    stored_meta = await self.storage.save_sanitized_image(
                        sanitized_result=sanitized_result,
                        is_ephemeral=is_ephemeral,
                    )
                    stored_meta["base64_data_uri"] = data_uri
                    stored_meta["raw_input"] = (
                        item_str if len(item_str) < 500 else item_str[:100] + "..."
                    )
                    processed_images.append(stored_meta)
                else:
                    # In-memory only (e.g. temporary un-saved references)
                    processed_images.append({
                        "image_id": f"ephemeral_{idx}",
                        "local_path": None,
                        "url": data_uri,
                        "width": sanitized_result["width"],
                        "height": sanitized_result["height"],
                        "size_bytes": sanitized_result["size_bytes"],
                        "mime_type": sanitized_result["mime_type"],
                        "base64_data_uri": data_uri,
                        "is_ephemeral": True,
                    })

            except VisionSecurityError as sec_err:
                log.warning(
                    "Image ingestion security violation",
                    error=str(sec_err),
                    item_index=idx,
                )
                continue
            except Exception as err:
                log.error("Image ingestion failure", error=str(err), item_index=idx)
                continue

        return processed_images

    async def _resolve_raw_bytes(self, item_str: str) -> bytes | None:
        """Resolves raw binary bytes from URL or Base64 Data URI."""
        if item_str.startswith("http://") or item_str.startswith("https://"):
            return await SecureImageFetcher.fetch_image(url=item_str, http_client=self.http_client)
        elif item_str.startswith("data:image/"):
            # Base64 Data URI
            match = re.match(r"^data:image\/[a-zA-Z0-9\+\-\.]+;base64,(.+)$", item_str)
            if not match:
                raise ImageValidationError("Invalid Base64 Data URI format")
            try:
                return base64.b64decode(match.group(1), validate=True)
            except (ValueError, binascii.Error) as error:
                raise ImageValidationError("Invalid Base64 image payload") from error
        else:
            # Assume raw base64 string
            try:
                return base64.b64decode(item_str, validate=True)
            except (ValueError, binascii.Error) as error:
                raise ImageValidationError(
                    "Unrecognized image input format (expected HTTP URL or Base64)"
                ) from error
