"""Application service orchestration for BE-01 durable workers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from time import monotonic

from app.domain.interfaces.background_jobs import (
    IBackgroundJobHandler,
    IDurableBackgroundJobQueue,
    StaleJobLeaseError,
)
from app.domain.interfaces.observability import (
    CounterSignal,
    GaugeSignal,
    HistogramSignal,
    IOperationalTelemetry,
    NoopOperationalTelemetry,
    TelemetryDimensions,
    TraceOperation,
)
from app.domain.models.background_job import (
    BackgroundJobStatus,
    BackgroundJobType,
    ClaimedBackgroundJob,
)

log = logging.getLogger(__name__)


class DurableBackgroundWorker:
    """Claim bounded batches, execute typed handlers, and fence terminal writes."""

    def __init__(
        self,
        *,
        queue: IDurableBackgroundJobQueue,
        handlers: Mapping[BackgroundJobType, IBackgroundJobHandler],
        worker_id: str,
        concurrency: int = 1,
        lease_seconds: int = 300,
        poll_seconds: float = 1.0,
        shutdown_grace_seconds: float = 30.0,
        queue_snapshot_interval_seconds: float = 30.0,
        telemetry: IOperationalTelemetry | None = None,
    ) -> None:
        if not 1 <= concurrency <= 4:
            raise ValueError("worker concurrency must be between 1 and 4")
        if queue_snapshot_interval_seconds <= 0:
            raise ValueError("queue snapshot interval must be positive")
        self._queue = queue
        self._handlers = dict(handlers)
        self._worker_id = worker_id
        self._concurrency = concurrency
        self._lease_seconds = lease_seconds
        self._poll_seconds = poll_seconds
        self._shutdown_grace_seconds = shutdown_grace_seconds
        self._queue_snapshot_interval_seconds = queue_snapshot_interval_seconds
        self._telemetry = telemetry or NoopOperationalTelemetry()
        self._stopping = asyncio.Event()
        self._active_jobs = 0

    def request_shutdown(self) -> None:
        """Stop future claims; active work is drained by ``run``."""
        self._stopping.set()

    async def run_once(self) -> int:
        """Claim and finish one bounded batch; useful for tests and supervisors."""
        if self._stopping.is_set():
            return 0
        jobs = await self._queue.claim(
            worker_id=self._worker_id,
            limit=self._concurrency,
            lease_seconds=self._lease_seconds,
        )
        if not jobs:
            return 0
        await self._drain_batch(jobs, watch_shutdown=False)
        return len(jobs)

    async def run(self) -> None:
        """Run until shutdown, never claiming after the stop signal is set."""
        queue_monitor = asyncio.create_task(self._monitor_queue())
        try:
            while not self._stopping.is_set():
                jobs = await self._queue.claim(
                    worker_id=self._worker_id,
                    limit=self._concurrency,
                    lease_seconds=self._lease_seconds,
                )
                if jobs:
                    await self._drain_batch(jobs, watch_shutdown=True)
                    continue
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=self._poll_seconds)
                except TimeoutError:
                    continue
        finally:
            queue_monitor.cancel()
            await asyncio.gather(queue_monitor, return_exceptions=True)

    async def _drain_batch(self, jobs: list[ClaimedBackgroundJob], *, watch_shutdown: bool) -> None:
        tasks = [asyncio.create_task(self._execute(job)) for job in jobs]
        batch = asyncio.gather(*tasks, return_exceptions=True)
        if not watch_shutdown:
            await batch
            return

        stop_wait = asyncio.create_task(self._stopping.wait())
        done, _ = await asyncio.wait((batch, stop_wait), return_when=asyncio.FIRST_COMPLETED)
        if batch in done:
            stop_wait.cancel()
            await asyncio.gather(stop_wait, return_exceptions=True)
            return

        try:
            await asyncio.wait_for(asyncio.shield(batch), timeout=self._shutdown_grace_seconds)
        except TimeoutError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute(self, job: ClaimedBackgroundJob) -> None:
        dimensions = TelemetryDimensions(job_type=job.job_type.value)
        started_at = monotonic()
        outcome = "error"
        failure_class: str | None = None
        self._active_jobs += 1
        self._record_active_jobs()
        with self._telemetry.span(TraceOperation.WORKER_JOB, dimensions) as span:
            try:
                handler = self._handlers.get(job.job_type)
                if handler is None:
                    failure_class = "queue_failure"
                    status = await self._queue.fail(
                        job=job, error_code="unsupported_job_type"
                    )
                    outcome = status.value
                    return
                heartbeat = asyncio.create_task(self._heartbeat(job))
                try:
                    await handler.handle(job)
                except asyncio.CancelledError:
                    outcome = "released"
                    failure_class = "client_cancelled"
                    try:
                        await self._queue.release(
                            job_id=job.job_id,
                            lease_token=job.lease_token,
                            reason="worker_shutdown",
                        )
                    except StaleJobLeaseError:
                        log.warning("Shutdown release lost job lease for job %s", job.job_id)
                    raise
                except Exception as exc:
                    failure_class = _failure_class(exc)
                    status = await self._queue.fail(job=job, error_code=type(exc).__name__)
                    outcome = status.value
                else:
                    await self._queue.complete(
                        job_id=job.job_id, lease_token=job.lease_token
                    )
                    outcome = BackgroundJobStatus.SUCCEEDED.value
                finally:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
            except Exception as exc:
                if outcome == "error":
                    failure_class = _failure_class(exc)
                raise
            finally:
                span.set_status(
                    _span_status(outcome),
                    failure_class,
                )
                self._record_job_result(
                    dimensions=dimensions,
                    outcome=outcome,
                    failure_class=failure_class,
                    duration_seconds=monotonic() - started_at,
                )
                self._active_jobs -= 1
                self._record_active_jobs()

    async def _heartbeat(self, job: ClaimedBackgroundJob) -> None:
        interval = max(1.0, self._lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            await self._queue.renew(
                job_id=job.job_id,
                lease_token=job.lease_token,
                lease_seconds=self._lease_seconds,
            )

    async def _monitor_queue(self) -> None:
        while True:
            try:
                snapshot = await self._queue.snapshot()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(
                    "Background queue metrics snapshot unavailable: %s",
                    _failure_class(exc),
                )
            else:
                for status, count in snapshot.counts.items():
                    self._telemetry.set_gauge(
                        GaugeSignal.WORKER_QUEUE_DEPTH,
                        count,
                        TelemetryDimensions(status=status.value),
                    )
                self._telemetry.set_gauge(
                    GaugeSignal.WORKER_QUEUE_OLDEST_READY_AGE,
                    snapshot.oldest_ready_age_seconds or 0.0,
                    TelemetryDimensions(),
                )
            try:
                await asyncio.wait_for(
                    self._stopping.wait(),
                    timeout=self._queue_snapshot_interval_seconds,
                )
            except TimeoutError:
                continue
            return

    def _record_active_jobs(self) -> None:
        self._telemetry.set_gauge(
            GaugeSignal.WORKER_ACTIVE,
            self._active_jobs,
            TelemetryDimensions(),
        )

    def _record_job_result(
        self,
        *,
        dimensions: TelemetryDimensions,
        outcome: str,
        failure_class: str | None,
        duration_seconds: float,
    ) -> None:
        result_dimensions = TelemetryDimensions(
            job_type=dimensions.job_type,
            status=outcome,
            failure_class=failure_class,
        )
        self._telemetry.observe(
            HistogramSignal.WORKER_JOB_DURATION,
            duration_seconds,
            result_dimensions,
        )
        self._telemetry.count(CounterSignal.WORKER_JOBS, result_dimensions)
        if failure_class is not None and failure_class != "client_cancelled":
            self._telemetry.count(CounterSignal.WORKER_FAILURES, result_dimensions)
        if outcome == BackgroundJobStatus.RETRY_SCHEDULED.value:
            self._telemetry.count(CounterSignal.WORKER_RETRIES, result_dimensions)
        elif outcome == BackgroundJobStatus.DEAD_LETTER.value:
            self._telemetry.count(CounterSignal.WORKER_DLQ, result_dimensions)


def _failure_class(error: BaseException) -> str:
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, ConnectionError):
        return "transport"
    if isinstance(error, StaleJobLeaseError):
        return "queue_failure"
    return "unhandled"


def _span_status(outcome: str) -> str:
    if outcome == BackgroundJobStatus.SUCCEEDED.value:
        return "ok"
    if outcome == "released":
        return "cancelled"
    return "error"
