"""PostgreSQL transactional outbox and lease-based durable job queue."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.background_jobs import StaleJobLeaseError
from app.domain.interfaces.session import IDbSession
from app.domain.models.background_job import (
    BackgroundJobStatus,
    BackgroundJobSubmission,
    BackgroundJobType,
    BackgroundQueueSnapshot,
    ClaimedBackgroundJob,
)
from app.infrastructure.database.models.background_job import DurableBackgroundJobModel

SessionFactory = Callable[[], AsyncSession]


class PostgresDurableBackgroundJobQueue:
    """Use one PostgreSQL row as both transactional outbox event and job state."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        retry_base_seconds: float = 2.0,
        retry_max_seconds: float = 300.0,
    ) -> None:
        self._session_factory = session_factory
        self._retry_base_seconds = retry_base_seconds
        self._retry_max_seconds = retry_max_seconds

    async def enqueue(self, session: IDbSession, submission: BackgroundJobSubmission) -> uuid.UUID:
        db = _require_async_session(session)
        job_id = uuid.uuid4()
        now = datetime.now(UTC)
        model = DurableBackgroundJobModel(
            id=job_id,
            job_type=submission.job_type.value,
            idempotency_key=submission.idempotency_key,
            payload_version=submission.payload_version,
            payload=submission.payload,
            principal_id=submission.principal_id,
            tenant_id=submission.tenant_id,
            status=BackgroundJobStatus.PENDING.value,
            attempt_count=0,
            max_attempts=submission.max_attempts,
            available_at=now,
            replay_count=0,
        )
        try:
            async with db.begin_nested():
                db.add(model)
                await db.flush()
            return job_id
        except IntegrityError:
            existing = (
                await db.execute(
                    select(DurableBackgroundJobModel.id).where(
                        DurableBackgroundJobModel.idempotency_key == submission.idempotency_key
                    )
                )
            ).scalar_one()
            return existing

    async def claim(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> list[ClaimedBackgroundJob]:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("worker_id must contain 1..128 characters")
        if not 1 <= limit <= 16:
            raise ValueError("claim limit must be between 1 and 16")
        if not 1 <= lease_seconds <= 3_600:
            raise ValueError("lease_seconds must be between 1 and 3600")

        claim_time = now or datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(DurableBackgroundJobModel)
                .where(
                    DurableBackgroundJobModel.status == BackgroundJobStatus.RUNNING.value,
                    DurableBackgroundJobModel.lease_expires_at <= claim_time,
                    DurableBackgroundJobModel.attempt_count
                    >= DurableBackgroundJobModel.max_attempts,
                )
                .values(
                    status=BackgroundJobStatus.DEAD_LETTER.value,
                    lease_owner=None,
                    lease_token=None,
                    lease_expires_at=None,
                    terminal_at=claim_time,
                    last_error_code="lease_attempts_exhausted",
                    updated_at=claim_time,
                )
            )
            rows = (
                (
                    await session.execute(
                        select(DurableBackgroundJobModel)
                        .where(
                            or_(
                                (
                                    DurableBackgroundJobModel.status.in_(
                                        (
                                            BackgroundJobStatus.PENDING.value,
                                            BackgroundJobStatus.RETRY_SCHEDULED.value,
                                        )
                                    )
                                    & (DurableBackgroundJobModel.available_at <= claim_time)
                                ),
                                (
                                    DurableBackgroundJobModel.status
                                    == BackgroundJobStatus.RUNNING.value
                                )
                                & (DurableBackgroundJobModel.lease_expires_at <= claim_time),
                            ),
                            DurableBackgroundJobModel.attempt_count
                            < DurableBackgroundJobModel.max_attempts,
                        )
                        .order_by(
                            DurableBackgroundJobModel.available_at,
                            DurableBackgroundJobModel.created_at,
                        )
                        .with_for_update(skip_locked=True)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )

            claimed: list[ClaimedBackgroundJob] = []
            for row in rows:
                token = uuid.uuid4()
                row.status = BackgroundJobStatus.RUNNING.value
                row.attempt_count += 1
                row.lease_owner = worker_id
                row.lease_token = token
                row.lease_expires_at = claim_time + timedelta(seconds=lease_seconds)
                row.updated_at = claim_time
                claimed.append(_claimed_job(row, token))
            return claimed

    async def complete(self, *, job_id: uuid.UUID, lease_token: uuid.UUID) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(DurableBackgroundJobModel)
                .where(
                    DurableBackgroundJobModel.id == job_id,
                    DurableBackgroundJobModel.status == BackgroundJobStatus.RUNNING.value,
                    DurableBackgroundJobModel.lease_token == lease_token,
                    DurableBackgroundJobModel.lease_expires_at > now,
                )
                .values(
                    status=BackgroundJobStatus.SUCCEEDED.value,
                    lease_owner=None,
                    lease_token=None,
                    lease_expires_at=None,
                    completed_at=now,
                    updated_at=now,
                )
            )
            if _affected_rows(result) != 1:
                raise StaleJobLeaseError("job completion rejected for stale lease")

    async def renew(
        self,
        *,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        lease_seconds: int,
    ) -> None:
        if not 1 <= lease_seconds <= 3_600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(DurableBackgroundJobModel)
                .where(
                    DurableBackgroundJobModel.id == job_id,
                    DurableBackgroundJobModel.status == BackgroundJobStatus.RUNNING.value,
                    DurableBackgroundJobModel.lease_token == lease_token,
                    DurableBackgroundJobModel.lease_expires_at > now,
                )
                .values(
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                )
            )
            if _affected_rows(result) != 1:
                raise StaleJobLeaseError("job lease renewal rejected for stale lease")

    async def fail(
        self,
        *,
        job: ClaimedBackgroundJob,
        error_code: str,
        now: datetime | None = None,
    ) -> BackgroundJobStatus:
        failure_time = now or datetime.now(UTC)
        safe_code = _safe_error_code(error_code)
        exhausted = job.attempt_count >= job.max_attempts
        next_status = (
            BackgroundJobStatus.DEAD_LETTER if exhausted else BackgroundJobStatus.RETRY_SCHEDULED
        )
        available_at = failure_time
        if not exhausted:
            available_at += timedelta(seconds=self._retry_delay(job))

        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(DurableBackgroundJobModel)
                .where(
                    DurableBackgroundJobModel.id == job.job_id,
                    DurableBackgroundJobModel.status == BackgroundJobStatus.RUNNING.value,
                    DurableBackgroundJobModel.lease_token == job.lease_token,
                    DurableBackgroundJobModel.lease_expires_at > failure_time,
                )
                .values(
                    status=next_status.value,
                    available_at=available_at,
                    lease_owner=None,
                    lease_token=None,
                    lease_expires_at=None,
                    last_error_code=safe_code,
                    last_error_detail=None,
                    terminal_at=failure_time if exhausted else None,
                    updated_at=failure_time,
                )
            )
            if _affected_rows(result) != 1:
                raise StaleJobLeaseError("job failure rejected for stale lease")
        return next_status

    async def release(self, *, job_id: uuid.UUID, lease_token: uuid.UUID, reason: str) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(DurableBackgroundJobModel)
                .where(
                    DurableBackgroundJobModel.id == job_id,
                    DurableBackgroundJobModel.status == BackgroundJobStatus.RUNNING.value,
                    DurableBackgroundJobModel.lease_token == lease_token,
                    DurableBackgroundJobModel.lease_expires_at > now,
                )
                .values(
                    status=BackgroundJobStatus.RETRY_SCHEDULED.value,
                    available_at=now,
                    lease_owner=None,
                    lease_token=None,
                    lease_expires_at=None,
                    last_error_code=_safe_error_code(reason),
                    updated_at=now,
                )
            )
            if _affected_rows(result) != 1:
                raise StaleJobLeaseError("job release rejected for stale lease")

    async def replay_dead_letter(
        self, *, job_id: uuid.UUID, actor: str, now: datetime | None = None
    ) -> None:
        if not actor or len(actor) > 128:
            raise ValueError("replay actor must contain 1..128 characters")
        replay_time = now or datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(DurableBackgroundJobModel)
                .where(
                    DurableBackgroundJobModel.id == job_id,
                    DurableBackgroundJobModel.status == BackgroundJobStatus.DEAD_LETTER.value,
                )
                .values(
                    status=BackgroundJobStatus.PENDING.value,
                    attempt_count=0,
                    available_at=replay_time,
                    lease_owner=None,
                    lease_token=None,
                    lease_expires_at=None,
                    completed_at=None,
                    replay_count=DurableBackgroundJobModel.replay_count + 1,
                    last_replayed_by=actor,
                    last_replayed_at=replay_time,
                    updated_at=replay_time,
                )
            )
            if _affected_rows(result) != 1:
                raise ValueError("only dead-letter jobs may be replayed")

    async def get(self, job_id: uuid.UUID) -> DurableBackgroundJobModel | None:
        """Read job state for controlled operations and verification."""
        async with self._session_factory() as session:
            return await session.get(DurableBackgroundJobModel, job_id)

    async def snapshot(self, *, now: datetime | None = None) -> BackgroundQueueSnapshot:
        captured_at = now or datetime.now(UTC)
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        DurableBackgroundJobModel.status,
                        func.count(DurableBackgroundJobModel.id),
                    ).group_by(DurableBackgroundJobModel.status)
                )
            ).all()
            oldest_ready = await session.scalar(
                select(func.min(DurableBackgroundJobModel.available_at)).where(
                    DurableBackgroundJobModel.status.in_(
                        (
                            BackgroundJobStatus.PENDING.value,
                            BackgroundJobStatus.RETRY_SCHEDULED.value,
                        )
                    ),
                    DurableBackgroundJobModel.available_at <= captured_at,
                )
            )
        counts = {status: 0 for status in BackgroundJobStatus}
        for raw_status, count in rows:
            counts[BackgroundJobStatus(raw_status)] = int(count)
        age = (
            max(0.0, (captured_at - oldest_ready).total_seconds())
            if oldest_ready is not None
            else None
        )
        return BackgroundQueueSnapshot(
            counts=counts,
            oldest_ready_age_seconds=age,
            captured_at=captured_at,
        )

    def _retry_delay(self, job: ClaimedBackgroundJob) -> float:
        exponential = min(
            self._retry_max_seconds,
            self._retry_base_seconds * (2 ** max(job.attempt_count - 1, 0)),
        )
        digest = hashlib.sha256(f"{job.job_id}:{job.attempt_count}".encode()).digest()[0]
        jitter_factor = 0.8 + (digest / 255) * 0.4
        return min(self._retry_max_seconds, exponential * jitter_factor)


def _require_async_session(session: IDbSession) -> AsyncSession:
    if not isinstance(session, AsyncSession):
        raise TypeError("PostgreSQL durable outbox requires an AsyncSession")
    return session


def _claimed_job(row: DurableBackgroundJobModel, token: uuid.UUID) -> ClaimedBackgroundJob:
    if row.lease_owner is None or row.lease_expires_at is None:
        raise RuntimeError("claimed job is missing lease metadata")
    return ClaimedBackgroundJob(
        job_id=row.id,
        job_type=BackgroundJobType(row.job_type),
        idempotency_key=row.idempotency_key,
        payload=dict(row.payload),
        payload_version=row.payload_version,
        principal_id=row.principal_id,
        tenant_id=row.tenant_id,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        lease_owner=row.lease_owner,
        lease_token=token,
        lease_expires_at=row.lease_expires_at,
    )


def _safe_error_code(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in "_-" else "_" for char in value)
    return normalized[:128] or "background_job_error"


def _affected_rows(result: object) -> int:
    rowcount = getattr(result, "rowcount", None)
    if not isinstance(rowcount, int):
        raise RuntimeError("database driver did not report affected row count")
    return rowcount
