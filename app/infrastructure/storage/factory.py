"""
Storage Provider Factory for Kuchiba Chisa.
Location: app/infrastructure/storage/factory.py
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from app.config.settings import Settings, get_settings
from app.domain.interfaces.image_storage import IImageStorageProvider
from app.shared.security.vision_security import SecureImageStorage
from app.infrastructure.storage.s3_storage import S3ImageStorageProvider
from app.infrastructure.storage.cloudinary_storage import CloudinaryImageStorageProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


def get_image_storage_provider(app_settings: Optional[Settings] = None) -> IImageStorageProvider:
    """
    Factory creating the configured Image Storage Provider:
    - 'local': Local filesystem WebP storage with 1GB LRU quota.
    - 's3' / 'r2' / 'minio': S3-compatible object storage.
    - 'cloudinary': Cloudinary cloud media hosting.
    """
    cfg = app_settings or get_settings()
    backend = (cfg.VISION_STORAGE_BACKEND or "local").lower().strip()

    if backend in ("s3", "r2", "minio"):
        log.info("Initializing S3/R2/MinIO Storage Provider", bucket=cfg.VISION_S3_BUCKET)
        return S3ImageStorageProvider(
            bucket_name=cfg.VISION_S3_BUCKET or "chisa-vision",
            endpoint_url=cfg.VISION_S3_ENDPOINT_URL,
            access_key=cfg.VISION_S3_ACCESS_KEY,
            secret_key=cfg.VISION_S3_SECRET_KEY,
            region_name=cfg.VISION_S3_REGION or "auto",
            public_domain=cfg.VISION_S3_PUBLIC_DOMAIN,
        )

    if backend == "cloudinary":
        log.info("Initializing Cloudinary Storage Provider", cloud_name=cfg.CLOUDINARY_CLOUD_NAME)
        return CloudinaryImageStorageProvider(
            cloud_name=cfg.CLOUDINARY_CLOUD_NAME,
            api_key=cfg.CLOUDINARY_API_KEY,
            api_secret=cfg.CLOUDINARY_API_SECRET,
        )

    # Default to Local Secure Image Storage
    base_dir = Path(cfg.VISION_LOCAL_STORAGE_DIR) if cfg.VISION_LOCAL_STORAGE_DIR else None
    return SecureImageStorage(
        base_storage_dir=base_dir,
        max_storage_mb=cfg.VISION_STORAGE_MAX_MB,
        base_url=cfg.VISION_STORAGE_BASE_URL or "/static/uploads",
    )
