"""BE-01 worker orchestration, payload privacy, and idempotency regressions."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.background.worker import DurableBackgroundWorker
from app.domain.interfaces.observability import (
    CounterSignal,
    GaugeSignal,
    HistogramSignal,
    TelemetryDimensions,
    TraceOperation,
)
from app.domain.models.background_job import (
    BackgroundJobStatus,
    BackgroundJobSubmission,
    BackgroundJobType,
    BackgroundQueueSnapshot,
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
@pytest.mark.parametrize(
    ("durable_status", "expected_signal"),
    [
        (BackgroundJobStatus.RETRY_SCHEDULED, CounterSignal.WORKER_RETRIES),
        (BackgroundJobStatus.DEAD_LETTER, CounterSignal.WORKER_DLQ),
    ],
)
async def test_worker_reports_durable_retry_and_dlq_outcomes(
    durable_status: BackgroundJobStatus,
    expected_signal: CounterSignal,
) -> None:
    job = _job()
    queue = AsyncMock()
    queue.claim.return_value = [job]
    queue.fail.return_value = durable_status
    handler = AsyncMock()
    handler.handle.side_effect = TimeoutError("sensitive provider detail")
    telemetry = MagicMock()
    span = MagicMock()
    telemetry.span.return_value = nullcontext(span)
    worker = DurableBackgroundWorker(
        queue=queue,
        handlers={job.job_type: handler},
        worker_id="worker-a",
        telemetry=telemetry,
    )

    assert await worker.run_once() == 1

    dimensions = TelemetryDimensions(
        job_type=job.job_type.value,
        status=durable_status.value,
        failure_class="timeout",
    )
    telemetry.span.assert_called_once_with(
        TraceOperation.WORKER_JOB,
        TelemetryDimensions(job_type=job.job_type.value),
    )
    span.set_status.assert_called_once_with("error", "timeout")
    duration_call = telemetry.observe.call_args
    assert duration_call.args[0] is HistogramSignal.WORKER_JOB_DURATION
    assert duration_call.args[1] >= 0
    assert duration_call.args[2] == dimensions
    telemetry.count.assert_any_call(CounterSignal.WORKER_JOBS, dimensions)
    telemetry.count.assert_any_call(CounterSignal.WORKER_FAILURES, dimensions)
    telemetry.count.assert_any_call(expected_signal, dimensions)
    telemetry.set_gauge.assert_any_call(
        GaugeSignal.WORKER_ACTIVE,
        1,
        TelemetryDimensions(),
    )
    telemetry.set_gauge.assert_any_call(
        GaugeSignal.WORKER_ACTIVE,
        0,
        TelemetryDimensions(),
    )
    assert "sensitive provider detail" not in repr(telemetry.mock_calls)
    assert str(job.job_id) not in repr(telemetry.mock_calls)


@pytest.mark.asyncio
async def test_worker_success_is_observable_without_job_identity() -> None:
    job = _job()
    queue = AsyncMock()
    queue.claim.return_value = [job]
    telemetry = MagicMock()
    span = MagicMock()
    telemetry.span.return_value = nullcontext(span)
    worker = DurableBackgroundWorker(
        queue=queue,
        handlers={job.job_type: AsyncMock()},
        worker_id="worker-a",
        telemetry=telemetry,
    )

    await worker.run_once()

    dimensions = TelemetryDimensions(
        job_type=job.job_type.value,
        status=BackgroundJobStatus.SUCCEEDED.value,
    )
    telemetry.count.assert_any_call(CounterSignal.WORKER_JOBS, dimensions)
    span.set_status.assert_called_once_with("ok", None)
    assert str(job.job_id) not in repr(telemetry.mock_calls)


@pytest.mark.asyncio
async def test_worker_queue_monitor_reports_status_depth_and_ready_age() -> None:
    snapshot_ready = asyncio.Event()
    snapshot = BackgroundQueueSnapshot(
        counts={
            status: int(status is BackgroundJobStatus.PENDING)
            for status in BackgroundJobStatus
        },
        oldest_ready_age_seconds=12.5,
        captured_at=datetime.now(UTC),
    )

    async def read_snapshot() -> BackgroundQueueSnapshot:
        snapshot_ready.set()
        return snapshot

    queue = AsyncMock()
    queue.snapshot.side_effect = read_snapshot
    telemetry = MagicMock()
    worker = DurableBackgroundWorker(
        queue=queue,
        handlers={},
        worker_id="worker-a",
        telemetry=telemetry,
    )
    monitoring = asyncio.create_task(worker._monitor_queue())

    await snapshot_ready.wait()
    worker.request_shutdown()
    await monitoring

    for status, count in snapshot.counts.items():
        telemetry.set_gauge.assert_any_call(
            GaugeSignal.WORKER_QUEUE_DEPTH,
            count,
            TelemetryDimensions(status=status.value),
        )
    telemetry.set_gauge.assert_any_call(
        GaugeSignal.WORKER_QUEUE_OLDEST_READY_AGE,
        12.5,
        TelemetryDimensions(),
    )


@pytest.mark.asyncio
async def test_dead_letter_replay_metric_contains_no_actor_or_job_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import worker as worker_cli

    queue = AsyncMock()
    telemetry = MagicMock()
    monkeypatch.setitem(worker_cli.container.__dict__, "background_job_queue", queue)
    monkeypatch.setattr(worker_cli, "operational_telemetry", telemetry)
    monkeypatch.setattr(worker_cli, "configure_observability", MagicMock())
    monkeypatch.setattr(worker_cli, "shutdown_observability", MagicMock())
    monkeypatch.setattr(worker_cli, "connect_database", AsyncMock())
    monkeypatch.setattr(worker_cli, "disconnect_database", AsyncMock())
    job_id = uuid.uuid4()

    await worker_cli.replay_dead_letter(job_id, "project-owner")

    queue.replay_dead_letter.assert_awaited_once_with(
        job_id=job_id,
        actor="project-owner",
    )
    telemetry.count.assert_called_once_with(
        CounterSignal.WORKER_REPLAYS,
        TelemetryDimensions(status="succeeded"),
    )
    assert str(job_id) not in repr(telemetry.mock_calls)
    assert "project-owner" not in repr(telemetry.mock_calls)


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
    queue.snapshot.return_value = BackgroundQueueSnapshot(
        counts={status: 0 for status in BackgroundJobStatus},
        oldest_ready_age_seconds=None,
        captured_at=datetime.now(UTC),
    )
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
