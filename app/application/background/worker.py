"""Application service orchestration for BE-01 durable workers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping

from app.domain.interfaces.background_jobs import (
    IBackgroundJobHandler,
    IDurableBackgroundJobQueue,
    StaleJobLeaseError,
)
from app.domain.models.background_job import BackgroundJobType, ClaimedBackgroundJob

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
    ) -> None:
        if not 1 <= concurrency <= 4:
            raise ValueError("worker concurrency must be between 1 and 4")
        self._queue = queue
        self._handlers = dict(handlers)
        self._worker_id = worker_id
        self._concurrency = concurrency
        self._lease_seconds = lease_seconds
        self._poll_seconds = poll_seconds
        self._shutdown_grace_seconds = shutdown_grace_seconds
        self._stopping = asyncio.Event()

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
        handler = self._handlers.get(job.job_type)
        if handler is None:
            await self._queue.fail(job=job, error_code="unsupported_job_type")
            return
        heartbeat = asyncio.create_task(self._heartbeat(job))
        try:
            await handler.handle(job)
        except asyncio.CancelledError:
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
            await self._queue.fail(job=job, error_code=type(exc).__name__)
        else:
            await self._queue.complete(job_id=job.job_id, lease_token=job.lease_token)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _heartbeat(self, job: ClaimedBackgroundJob) -> None:
        interval = max(1.0, self._lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            await self._queue.renew(
                job_id=job.job_id,
                lease_token=job.lease_token,
                lease_seconds=self._lease_seconds,
            )
