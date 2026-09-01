"""SEC-04 regression tests for non-stub image-storage deletion acknowledgements."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.infrastructure.storage.cloudinary_storage import CloudinaryImageStorageProvider
from app.infrastructure.storage.s3_storage import S3ImageStorageProvider

_IMAGE_ID = "a" * 32


class _S3Client:
    def __init__(self) -> None:
        self.deleted: list[dict] = []

    def list_objects_v2(self, **kwargs):
        del kwargs
        return {
            "Contents": [
                {"Key": f"uploads/2026/09/{_IMAGE_ID}.webp"},
                {"Key": "uploads/2026/09/other.webp"},
            ],
            "IsTruncated": False,
        }

    def delete_objects(self, **kwargs):
        self.deleted.append(kwargs)
        return {"Deleted": kwargs["Delete"]["Objects"]}


def test_s3_erasure_deletes_only_matching_object_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _S3Client()
    provider = S3ImageStorageProvider(bucket_name="test-bucket")
    monkeypatch.setattr(provider, "_client", lambda: client)

    provider._delete_s3_sync(_IMAGE_ID)

    assert client.deleted == [
        {
            "Bucket": "test-bucket",
            "Delete": {
                "Objects": [{"Key": f"uploads/2026/09/{_IMAGE_ID}.webp"}],
                "Quiet": True,
            },
        }
    ]


@pytest.mark.asyncio
async def test_object_storage_deletion_rejects_untrusted_identifier_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s3_provider = S3ImageStorageProvider(bucket_name="test-bucket")
    cloudinary_provider = CloudinaryImageStorageProvider()

    with pytest.raises(ValueError):
        await s3_provider.delete_image("../outside")
    with pytest.raises(ValueError):
        await cloudinary_provider.delete_image("../outside")

    monkeypatch.setattr(
        s3_provider,
        "_delete_s3_sync",
        lambda image_id: (_ for _ in ()).throw(RuntimeError("provider error")),
    )
    monkeypatch.setattr(
        cloudinary_provider,
        "_delete_cloudinary_sync",
        lambda image_id: (_ for _ in ()).throw(RuntimeError("provider error")),
    )

    with pytest.raises(RuntimeError, match="S3 image deletion failed"):
        await s3_provider.delete_image(_IMAGE_ID)
    with pytest.raises(RuntimeError, match="Cloudinary image deletion failed"):
        await cloudinary_provider.delete_image(_IMAGE_ID)


@pytest.mark.asyncio
async def test_cloudinary_erasure_requires_successful_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = CloudinaryImageStorageProvider()
    call = SimpleNamespace(image_id=None)

    def delete(image_id: str) -> None:
        call.image_id = image_id

    monkeypatch.setattr(provider, "_delete_cloudinary_sync", delete)

    assert await provider.delete_image(_IMAGE_ID) is True
    assert call.image_id == _IMAGE_ID
