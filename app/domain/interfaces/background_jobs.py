"""Ports for transactional enqueue and durable worker queue operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from app.domain.interfaces.session import IDbSession
from app.domain.models.background_job import (
    BackgroundJobStatus,
    BackgroundJobSubmission,
    BackgroundQueueSnapshot,
    ClaimedBackgroundJob,
)


class StaleJobLeaseError(RuntimeError):
    """A worker tried to mutate a job using an expired or replaced lease."""


class IDurableBackgroundJobQueue(Protocol):
    async def enqueue(self, session: IDbSession, submission: BackgroundJobSubmission) -> uuid.UUID:
        """Insert an outbox job in the producer's existing transaction."""
        ...

    async def claim(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> list[ClaimedBackgroundJob]: ...

    async def complete(self, *, job_id: uuid.UUID, lease_token: uuid.UUID) -> None: ...

    async def renew(
        self,
        *,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        lease_seconds: int,
    ) -> None: ...

    async def fail(
        self,
        *,
        job: ClaimedBackgroundJob,
        error_code: str,
        now: datetime | None = None,
    ) -> BackgroundJobStatus: ...

    async def release(self, *, job_id: uuid.UUID, lease_token: uuid.UUID, reason: str) -> None: ...

    async def replay_dead_letter(
        self, *, job_id: uuid.UUID, actor: str, now: datetime | None = None
    ) -> None: ...

    async def snapshot(self, *, now: datetime | None = None) -> BackgroundQueueSnapshot: ...


class IBackgroundJobHandler(Protocol):
    async def handle(self, job: ClaimedBackgroundJob) -> None: ...
