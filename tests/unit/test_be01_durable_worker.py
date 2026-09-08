"""BE-01 worker orchestration, payload privacy, and idempotency regressions."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.application.background.worker import DurableBackgroundWorker
from app.domain.models.background_job import (
    BackgroundJobStatus,
    BackgroundJobSubmission,
    BackgroundJobType,
    ClaimedBackgroundJob,
)
from app.infrastructure.background.job_handlers import (
    DurableJobPayloadError,
    MemoryExtractionJobHandler,
)


def _job(job_type: BackgroundJobType = BackgroundJobType.PRIVATE_SUMMARY) -> ClaimedBackgroundJob:
    now = datetime.now(UTC)
    return ClaimedBackgroundJob(
        job_id=uuid.uuid4(),
        job_type=job_type,
        idempotency_key=f"test-job:{uuid.uuid4()}",
        payload={},
        payload_version=1,
        principal_id=uuid.uuid4(),
        tenant_id=None,
        attempt_count=1,
        max_attempts=3,
        lease_owner="worker-a",
        lease_token=uuid.uuid4(),
        lease_expires_at=now + timedelta(minutes=5),
    )


def test_background_payload_rejects_secrets_and_unbounded_content() -> None:
    with pytest.raises(ValueError, match="forbidden persisted payload"):
        BackgroundJobSubmission(
            job_type=BackgroundJobType.PRIVATE_SUMMARY,
            idempotency_key="private-summary:one",
            payload={"api_key": "must-not-persist"},
            principal_id=uuid.uuid4(),
        )
    with pytest.raises(ValueError, match="too large"):
        BackgroundJobSubmission(
            job_type=BackgroundJobType.PRIVATE_SUMMARY,
            idempotency_key="private-summary:two",
            payload={"content": "x" * 8_193},
            principal_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_worker_completes_only_after_handler_success() -> None:
    job = _job()
    queue = AsyncMock()
    queue.claim.return_value = [job]
    handler = AsyncMock()
    worker = DurableBackgroundWorker(
        queue=queue,
        handlers={job.job_type: handler},
        worker_id="worker-a",
    )

    assert await worker.run_once() == 1

    handler.handle.assert_awaited_once_with(job)
    queue.complete.assert_awaited_once_with(
        job_id=job.job_id, lease_token=job.lease_token
    )
    queue.fail.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_records_failure_without_false_success() -> None:
    job = _job()
    queue = AsyncMock()
    queue.claim.return_value = [job]
    handler = AsyncMock()
    handler.handle.side_effect = TimeoutError("provider detail must not persist")
    worker = DurableBackgroundWorker(
        queue=queue,
        handlers={job.job_type: handler},
        worker_id="worker-a",
    )

    await worker.run_once()

    queue.complete.assert_not_awaited()
    queue.fail.assert_awaited_once_with(job=job, error_code="TimeoutError")


@pytest.mark.asyncio
async def test_long_running_handler_renews_its_lease() -> None:
    job = _job()
    queue = AsyncMock()
    queue.claim.return_value = [job]

    async def work(_: ClaimedBackgroundJob) -> None:
        await asyncio.sleep(1.05)

    handler = AsyncMock()
    handler.handle.side_effect = work
    worker = DurableBackgroundWorker(
        queue=queue,
        handlers={job.job_type: handler},
        worker_id="worker-a",
        lease_seconds=3,
    )

    await worker.run_once()

    queue.renew.assert_awaited_once_with(
        job_id=job.job_id,
        lease_token=job.lease_token,
        lease_seconds=3,
    )


@pytest.mark.asyncio
async def test_graceful_shutdown_releases_cancelled_job() -> None:
    job = _job()
    queue = AsyncMock()
    queue.claim.return_value = [job]
    entered = asyncio.Event()

    async def wait_forever(_: ClaimedBackgroundJob) -> None:
        entered.set()
        await asyncio.Event().wait()

    handler = AsyncMock()
    handler.handle.side_effect = wait_forever
    worker = DurableBackgroundWorker(
        queue=queue,
        handlers={job.job_type: handler},
        worker_id="worker-a",
        shutdown_grace_seconds=0.01,
    )
    running = asyncio.create_task(worker.run())
    await entered.wait()
    worker.request_shutdown()
    await running

    queue.release.assert_awaited_once_with(
        job_id=job.job_id,
        lease_token=job.lease_token,
        reason="worker_shutdown",
    )
    queue.complete.assert_not_awaited()


def test_background_status_has_explicit_dead_letter_state() -> None:
    assert BackgroundJobStatus.DEAD_LETTER.value == "dead_letter"


@pytest.mark.asyncio
async def test_handler_rejects_payload_principal_spoofing_before_side_effect() -> None:
    job = _job(BackgroundJobType.MEMORY_EXTRACTION)
    job = ClaimedBackgroundJob(
        **{
            **job.__dict__,
            "payload": {
                "user_id": str(uuid.uuid4()),
                "conversation_id": str(uuid.uuid4()),
                "user_message_id": str(uuid.uuid4()),
                "assistant_message_id": str(uuid.uuid4()),
                "guild_id": None,
            },
        }
    )
    source = AsyncMock()
    extractor = AsyncMock()

    with pytest.raises(DurableJobPayloadError, match="trusted envelope"):
        await MemoryExtractionJobHandler(source, extractor).handle(job)

    source.ensure_consent.assert_not_awaited()
    extractor.extract_and_store_batch.assert_not_awaited()
