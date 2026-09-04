"""
AWS S3 / Cloudflare R2 / MinIO Storage Provider for Kuchiba Chisa.
Location: app/infrastructure/storage/s3_storage.py
"""

from __future__ import annotations

import asyncio
import io
import re
import time
import uuid
from datetime import datetime
from typing import Any

from app.domain.interfaces.image_storage import IImageStorageProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

_IMAGE_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


class S3ImageStorageProvider(IImageStorageProvider):
    """
    Object Storage Provider compatible with AWS S3, Cloudflare R2, and MinIO.
    Uses boto3 / aioboto3 or HTTP PUT presigned endpoints.
    """

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region_name: str = "auto",
        public_domain: str | None = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.region_name = region_name
        self.public_domain = (public_domain or "").rstrip("/")

    async def save_sanitized_image(
        self,
        sanitized_result: dict[str, Any],
        is_ephemeral: bool = False,
        sub_dir: str | None = None,
    ) -> dict[str, Any]:
        """
        Uploads WebP image and thumbnail to S3/R2/MinIO bucket.
        """
        now = datetime.now()
        prefix = sub_dir or ("ephemeral" if is_ephemeral else f"{now.year}/{now.month:02d}")
        image_id = uuid.uuid4().hex

        main_key = f"uploads/{prefix}/{image_id}.webp"

        # Construct public URL
        if self.public_domain:
            main_url = f"{self.public_domain}/{main_key}"
        elif self.endpoint_url:
            main_url = f"{self.endpoint_url.rstrip('/')}/{self.bucket_name}/{main_key}"
        else:
            main_url = f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{main_key}"

        try:
            await asyncio.to_thread(
                self._upload_s3_sync,
                main_key,
                sanitized_result["sanitized_bytes"],
                "image/webp",
            )
        except ImportError as error:
            raise RuntimeError("S3 storage SDK is required for the configured backend") from error
        except Exception as error:
            log.error(
                "S3 image upload failed",
                bucket=self.bucket_name,
                error_type=type(error).__name__,
            )
            raise RuntimeError("S3 image upload failed") from error

        return {
            "image_id": image_id,
            "local_path": None,
            "url": main_url,
            "width": sanitized_result["width"],
            "height": sanitized_result["height"],
            "size_bytes": sanitized_result["size_bytes"],
            "mime_type": sanitized_result["mime_type"],
            "is_ephemeral": is_ephemeral,
            "storage_backend": "s3_compatible",
            "created_at": time.time(),
        }

    def _upload_s3_sync(self, key: str, data: bytes, content_type: str) -> None:
        s3_client = self._client()
        s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=io.BytesIO(data),
            ContentType=content_type,
        )

    async def delete_image(self, image_id: str) -> bool:
        """Delete every stored object for a validated image ID, or fail closed."""
        self._validate_image_id(image_id)
        log.info("Deleting image from S3/R2", image_id=image_id)
        try:
            await asyncio.to_thread(self._delete_s3_sync, image_id)
        except ImportError as error:
            raise RuntimeError("S3 storage SDK is required for the configured backend") from error
        except Exception as error:
            log.error(
                "S3 image deletion failed",
                bucket=self.bucket_name,
                error_type=type(error).__name__,
            )
            raise RuntimeError("S3 image deletion failed") from error
        return True

    @staticmethod
    def _validate_image_id(image_id: str) -> None:
        if not _IMAGE_ID_PATTERN.fullmatch(image_id):
            raise ValueError("invalid stored image identifier")

    def _client(self):
        import boto3

        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name,
        )

    def _delete_s3_sync(self, image_id: str) -> None:
        """Locate and delete matching uploads without accepting a key from callers."""
        s3_client = self._client()
        continuation_token: str | None = None
        suffix = f"/{image_id}.webp"
        while True:
            request: dict[str, Any] = {"Bucket": self.bucket_name, "Prefix": "uploads/"}
            if continuation_token is not None:
                request["ContinuationToken"] = continuation_token
            response = s3_client.list_objects_v2(**request)
            keys = [
                item["Key"]
                for item in response.get("Contents", [])
                if item.get("Key", "").endswith(suffix)
            ]
            if keys:
                deletion = s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
                )
                if deletion.get("Errors"):
                    raise RuntimeError("S3 object deletion was not acknowledged")
            if not response.get("IsTruncated"):
                return
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                raise RuntimeError("S3 object listing returned an invalid continuation token")

    async def enforce_quota(self) -> None:
        # S3 lifecycle policies handle lifecycle automatically
        pass
