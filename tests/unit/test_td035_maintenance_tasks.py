from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.rag.retriever_image_memory import ImageMemoryRetriever
from app.shared.security.vision_security import LocalStorageManager
from app.shared.utils.maintenance_tasks import MaintenanceTaskSupervisor


@pytest.mark.asyncio
async def test_supervisor_retries_and_coalesces_same_key() -> None:
    gate = asyncio.Event()
    started = asyncio.Event()
    attempts = 0

    async def operation() -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("transient")
        started.set()
        await gate.wait()

    before = MaintenanceTaskSupervisor.snapshot()
    first = MaintenanceTaskSupervisor.schedule(
        key="td035:retry", operation=operation, retry_base_seconds=0
    )
    await started.wait()
    second = MaintenanceTaskSupervisor.schedule(
        key="td035:retry", operation=operation, retry_base_seconds=0
    )
    assert second is first
    gate.set()
    await MaintenanceTaskSupervisor.shutdown(grace_seconds=1)

    after = MaintenanceTaskSupervisor.snapshot()
    assert attempts == 3
    assert after.retries - before.retries == 2
    assert after.coalesced - before.coalesced == 1
    assert after.succeeded - before.succeeded == 1


@pytest.mark.asyncio
async def test_supervisor_gracefully_drains_before_timeout() -> None:
    release = asyncio.Event()
    completed = False

    async def operation() -> None:
        nonlocal completed
        await release.wait()
        completed = True

    task = MaintenanceTaskSupervisor.schedule(key="td035:drain", operation=operation)
    asyncio.get_running_loop().call_soon(release.set)
    await MaintenanceTaskSupervisor.shutdown(grace_seconds=1)

    assert task.done() and not task.cancelled()
    assert completed is True


@pytest.mark.asyncio
async def test_local_quota_work_is_coalesced_by_storage_root(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalStorageManager(base_storage_dir=tmp_path)
    release = asyncio.Event()

    async def wait_for_release() -> None:
        await release.wait()

    quota = AsyncMock(side_effect=wait_for_release)
    monkeypatch.setattr(storage, "enforce_lru_quota", quota)
    payload = {
        "sanitized_bytes": b"image",
        "width": 1,
        "height": 1,
        "size_bytes": 5,
        "mime_type": "image/webp",
    }
    before = MaintenanceTaskSupervisor.snapshot()

    await storage.save_sanitized_image(payload)
    await storage.save_sanitized_image(payload)
    release.set()
    await MaintenanceTaskSupervisor.shutdown(grace_seconds=1)

    after = MaintenanceTaskSupervisor.snapshot()
    assert after.submitted - before.submitted == 1
    assert after.coalesced - before.coalesced == 1


@pytest.mark.asyncio
async def test_orphan_cleanup_revalidates_exact_payload_before_delete(tmp_path) -> None:
    missing_path = str(tmp_path / "missing.webp")
    original_payload = {
        "image_id": "image-1",
        "local_path": missing_path,
        "url": "/static/image-1.webp",
        "visual_caption": "caption",
        "user_id": "user-1",
    }
    hit = SimpleNamespace(id="point-1", score=0.9, payload=original_payload)
    changed = SimpleNamespace(
        id="point-1", score=0.9, payload={**original_payload, "visual_caption": "repaired"}
    )
    client = AsyncMock()
    client.search.return_value = [hit]
    client.retrieve.return_value = [changed]
    vector_store = MagicMock()
    vector_store._client = client

    results = await ImageMemoryRetriever(vector_store).retrieve_image_memories(
        query_vector=[0.1], user_id="user-1"
    )
    await MaintenanceTaskSupervisor.shutdown(grace_seconds=1)

    assert results == []
    client.retrieve.assert_awaited_once()
    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_unchanged_orphan_is_deleted_with_server_side_identity_filter(tmp_path) -> None:
    missing_path = str(tmp_path / "missing.webp")
    payload = {
        "image_id": "image-1",
        "local_path": missing_path,
        "url": "/static/image-1.webp",
        "visual_caption": "caption",
        "user_id": "user-1",
    }
    hit = SimpleNamespace(id="point-1", score=0.9, payload=payload)
    client = AsyncMock()
    client.search.return_value = [hit]
    client.retrieve.return_value = [hit]
    vector_store = MagicMock()
    vector_store._client = client

    await ImageMemoryRetriever(vector_store).retrieve_image_memories(
        query_vector=[0.1], user_id="user-1"
    )
    await MaintenanceTaskSupervisor.shutdown(grace_seconds=1)

    call = client.delete.await_args
    assert call.kwargs["wait"] is True
    assert call.kwargs["points_selector"].filter.must[0].has_id == ["point-1"]
