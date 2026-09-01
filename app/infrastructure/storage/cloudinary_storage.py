"""
Cloudinary Image Storage Provider for Kuchiba Chisa.
Location: app/infrastructure/storage/cloudinary_storage.py
"""

from __future__ import annotations

import asyncio
import importlib
import re
import time
import uuid
from datetime import datetime
from typing import Any

from app.domain.interfaces.image_storage import IImageStorageProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

_IMAGE_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


class CloudinaryImageStorageProvider(IImageStorageProvider):
    """
    Image Storage Provider powered by Cloudinary API.
    """

    def __init__(
        self,
        cloud_name: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        self.cloud_name = cloud_name
        self.api_key = api_key
        self.api_secret = api_secret

    async def save_sanitized_image(
        self,
        sanitized_result: dict[str, Any],
        is_ephemeral: bool = False,
        sub_dir: str | None = None,
    ) -> dict[str, Any]:
        """
        Uploads WebP image to Cloudinary.
        """
        now = datetime.now()
        subfolder = sub_dir or ("ephemeral" if is_ephemeral else f"{now.year}_{now.month:02d}")
        folder = f"chisa_vision/{subfolder}"
        image_id = uuid.uuid4().hex

        # Construct Cloudinary public URL
        main_url = (
            f"https://res.cloudinary.com/{self.cloud_name or 'demo'}"
            f"/image/upload/{folder}/{image_id}.webp"
        )

        try:
            self._configure_cloudinary()
            uploader = importlib.import_module("cloudinary.uploader")
            upload_res = await asyncio.to_thread(
                uploader.upload,
                sanitized_result["sanitized_bytes"],
                public_id=image_id,
                folder=folder,
                format="webp",
            )
            main_url = upload_res.get("secure_url", main_url)
        except ImportError as error:
            raise RuntimeError("Cloudinary SDK is required for the configured backend") from error
        except Exception as error:
            log.error("Cloudinary upload failed", error_type=type(error).__name__)
            raise RuntimeError("Cloudinary upload failed") from error

        return {
            "image_id": image_id,
            "local_path": None,
            "url": main_url,
            "width": sanitized_result["width"],
            "height": sanitized_result["height"],
            "size_bytes": sanitized_result["size_bytes"],
            "mime_type": sanitized_result["mime_type"],
            "is_ephemeral": is_ephemeral,
            "storage_backend": "cloudinary",
            "created_at": time.time(),
        }

    async def delete_image(self, image_id: str) -> bool:
        """Delete all matching Cloudinary objects, including historical folders."""
        if not _IMAGE_ID_PATTERN.fullmatch(image_id):
            raise ValueError("invalid stored image identifier")
        log.info("Deleting image from Cloudinary", image_id=image_id)
        try:
            await asyncio.to_thread(self._delete_cloudinary_sync, image_id)
        except ImportError as error:
            raise RuntimeError("Cloudinary SDK is required for the configured backend") from error
        except Exception as error:
            log.error("Cloudinary image deletion failed", error_type=type(error).__name__)
            raise RuntimeError("Cloudinary image deletion failed") from error
        return True

    def _configure_cloudinary(self) -> Any:
        import cloudinary

        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret,
            secure=True,
        )
        return cloudinary

    def _delete_cloudinary_sync(self, image_id: str) -> None:
        self._configure_cloudinary()
        api = importlib.import_module("cloudinary.api")
        uploader = importlib.import_module("cloudinary.uploader")

        cursor: str | None = None
        public_ids: list[str] = []
        suffix = f"/{image_id}"
        while True:
            request: dict[str, Any] = {
                "type": "upload",
                "prefix": "chisa_vision/",
                "max_results": 500,
            }
            if cursor is not None:
                request["next_cursor"] = cursor
            response = api.resources(**request)
            public_ids.extend(
                item["public_id"]
                for item in response.get("resources", [])
                if item.get("public_id", "").endswith(suffix)
            )
            cursor = response.get("next_cursor")
            if not cursor:
                break

        for public_id in public_ids:
            result = uploader.destroy(public_id, invalidate=True, resource_type="image")
            if result.get("result") not in {"ok", "not found"}:
                raise RuntimeError("Cloudinary object deletion was not acknowledged")

    async def enforce_quota(self) -> None:
        pass
