"""
Abstract Interface for Image Storage Providers in Kuchiba Chisa.
Location: app/domain/interfaces/image_storage.py
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class IImageStorageProvider(ABC):
    """
    Abstract contract for pluggable image storage providers.
    Supported backends: Local Storage, AWS S3, Cloudflare R2, MinIO, Cloudinary.
    """

    @abstractmethod
    async def save_sanitized_image(
        self,
        sanitized_result: Dict[str, Any],
        is_ephemeral: bool = False,
        sub_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Saves sanitized WebP image bytes and thumbnail, returning metadata
        containing image_id, public url, thumbnail_url, width, height, size_bytes.
        """
        pass

    @abstractmethod
    async def delete_image(self, image_id: str) -> bool:
        """
        Deletes an image and its associated thumbnail by image_id.
        """
        pass

    @abstractmethod
    async def enforce_quota(self) -> None:
        """
        Executes quota cleanup / lifecycle policy enforcement (e.g. LRU eviction).
        """
        pass
