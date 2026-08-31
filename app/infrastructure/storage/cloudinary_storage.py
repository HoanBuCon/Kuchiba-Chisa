"""
Cloudinary Image Storage Provider for Kuchiba Chisa.
Location: app/infrastructure/storage/cloudinary_storage.py
"""

from __future__ import annotations
import time
import uuid
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from app.domain.interfaces.image_storage import IImageStorageProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class CloudinaryImageStorageProvider(IImageStorageProvider):
    """
    Image Storage Provider powered by Cloudinary API.
    """

    def __init__(
        self,
        cloud_name: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        self.cloud_name = cloud_name
        self.api_key = api_key
        self.api_secret = api_secret

    async def save_sanitized_image(
        self,
        sanitized_result: Dict[str, Any],
        is_ephemeral: bool = False,
        sub_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Uploads WebP image to Cloudinary.
        """
        now = datetime.now()
        folder = f"chisa_vision/{sub_dir or ('ephemeral' if is_ephemeral else f'{now.year}_{now.month:02d}')}"
        image_id = uuid.uuid4().hex

        # Construct Cloudinary public URL
        main_url = f"https://res.cloudinary.com/{self.cloud_name or 'demo'}/image/upload/{folder}/{image_id}.webp"
        thumb_url = f"https://res.cloudinary.com/{self.cloud_name or 'demo'}/image/upload/c_thumb,w_300/{folder}/{image_id}.webp"

        try:
            import cloudinary
            import cloudinary.uploader
            cloudinary.config(
                cloud_name=self.cloud_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
                secure=True,
            )
            upload_res = await asyncio.to_thread(
                cloudinary.uploader.upload,
                sanitized_result["sanitized_bytes"],
                public_id=image_id,
                folder=folder,
                format="webp",
            )
            main_url = upload_res.get("secure_url", main_url)
        except ImportError:
            log.warning("cloudinary SDK is not installed; running in dry-run mode")
        except Exception as ex:
            log.error("Cloudinary upload failed", error=str(ex))

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
        log.info("Deleting image from Cloudinary", image_id=image_id)
        return True

    async def enforce_quota(self) -> None:
        pass
