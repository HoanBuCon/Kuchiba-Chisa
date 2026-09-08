"""PostgreSQL integration evidence for BE-01 durability semantics."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.domain.interfaces.background_jobs import StaleJobLeaseError
from app.domain.models.background_job import (
    BackgroundJobStatus,
    BackgroundJobSubmission,
    BackgroundJobType,
)
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.background_job import DurableBackgroundJobModel
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.background_job_queue import (
    PostgresDurableBackgroundJobQueue,
)


def _submission(user_id: uuid.UUID, key: str, *, max_attempts: int = 3):
    return BackgroundJobSubmission(
        job_type=BackgroundJobType.PRIVATE_SUMMARY,
        idempotency_key=key,
        payload={"user_id": str(user_id), "conversation_id": str(uuid.uuid4())},
        principal_id=user_id,
        max_attempts=max_attempts,
    )


async def _clear_test_jobs() -> None:
    async with AsyncSessionFactory() as session:
        await session.execute(delete(DurableBackgroundJobModel))
        await session.commit()


@pytest.mark.asyncio
async def test_enqueue_is_atomic_and_idempotent(isolated_postgres: None) -> None:
    del isolated_postgres
    await _clear_test_jobs()
    user_id = uuid.uuid4()
    queue = PostgresDurableBackgroundJobQueue(AsyncSessionFactory)
    rolled_back_key = f"be01-rollback:{uuid.uuid4()}"
    committed_key = f"be01-idempotent:{uuid.uuid4()}"
    async with AsyncSessionFactory() as session:
        session.add(User(id=user_id, username=f"be01-{user_id}"))
        await session.commit()
        await queue.enqueue(session, _submission(user_id, rolled_back_key))
        await session.rollback()
        assert await session.scalar(
            select(DurableBackgroundJobModel.id).where(
                DurableBackgroundJobModel.idempotency_key == rolled_back_key
            )
        ) is None
        first = await queue.enqueue(session, _submission(user_id, committed_key))
        second = await queue.enqueue(session, _submission(user_id, committed_key))
        await session.commit()
        assert second == first

    async with AsyncSessionFactory() as session:
        count = len(
            (
                await session.scalars(
                    select(DurableBackgroundJobModel).where(
                        DurableBackgroundJobModel.idempotency_key == committed_key
                    )
                )
            ).all()
        )
        assert count == 1
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


@pytest.mark.asyncio
async def test_committed_job_survives_queue_process_restart(isolated_postgres: None) -> None:
    del isolated_postgres
    await _clear_test_jobs()
    user_id = uuid.uuid4()
    key = f"be01-restart:{uuid.uuid4()}"
    producer = PostgresDurableBackgroundJobQueue(AsyncSessionFactory)
    async with AsyncSessionFactory() as session:
        session.add(User(id=user_id, username=f"be01-{user_id}"))
        await session.flush()
        job_id = await producer.enqueue(session, _submission(user_id, key))
        await session.commit()

    del producer
    restarted_worker_queue = PostgresDurableBackgroundJobQueue(AsyncSessionFactory)
    claimed = await restarted_worker_queue.claim(
        worker_id="worker-after-restart",
        limit=1,
        lease_seconds=30,
    )
    assert [job.job_id for job in claimed] == [job_id]
    await restarted_worker_queue.complete(
        job_id=claimed[0].job_id,
        lease_token=claimed[0].lease_token,
    )

    async with AsyncSessionFactory() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


@pytest.mark.asyncio
async def test_claim_is_exclusive_and_expired_lease_is_fenced(
    isolated_postgres: None,
) -> None:
    del isolated_postgres
    await _clear_test_jobs()
    user_id = uuid.uuid4()
    queue = PostgresDurableBackgroundJobQueue(AsyncSessionFactory)
    key = f"be01-lease:{uuid.uuid4()}"
    async with AsyncSessionFactory() as session:
        session.add(User(id=user_id, username=f"be01-{user_id}"))
        await session.flush()
        await queue.enqueue(session, _submission(user_id, key))
        await session.commit()

    claim_time = datetime.now(UTC) + timedelta(seconds=1)
    claims = await asyncio.gather(
        queue.claim(worker_id="worker-a", limit=1, lease_seconds=30, now=claim_time),
        queue.claim(worker_id="worker-b", limit=1, lease_seconds=30, now=claim_time),
    )
    assert sorted(len(items) for items in claims) == [0, 1]
    first = next(items[0] for items in claims if items)

    reclaimed = await queue.claim(
        worker_id="worker-c",
        limit=1,
        lease_seconds=30,
        now=claim_time + timedelta(minutes=1),
    )
    assert len(reclaimed) == 1
    assert reclaimed[0].job_id == first.job_id
    assert reclaimed[0].lease_token != first.lease_token
    with pytest.raises(StaleJobLeaseError):
        await queue.complete(job_id=first.job_id, lease_token=first.lease_token)
    await queue.complete(
        job_id=reclaimed[0].job_id,
        lease_token=reclaimed[0].lease_token,
    )
    stored = await queue.get(first.job_id)
    assert stored is not None and stored.status == BackgroundJobStatus.SUCCEEDED.value

    async with AsyncSessionFactory() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


@pytest.mark.asyncio
async def test_bounded_retry_dead_letter_and_audited_manual_replay(
    isolated_postgres: None,
) -> None:
    del isolated_postgres
    await _clear_test_jobs()
    user_id = uuid.uuid4()
    queue = PostgresDurableBackgroundJobQueue(
        AsyncSessionFactory,
        retry_base_seconds=0.1,
        retry_max_seconds=1.0,
    )
    key = f"be01-dlq:{uuid.uuid4()}"
    async with AsyncSessionFactory() as session:
        session.add(User(id=user_id, username=f"be01-{user_id}"))
        await session.flush()
        job_id = await queue.enqueue(
            session,
            _submission(user_id, key, max_attempts=2),
        )
        await session.commit()

    first = (await queue.claim(worker_id="worker-a", limit=1, lease_seconds=30))[0]
    assert (
        await queue.fail(job=first, error_code="TimeoutError")
        is BackgroundJobStatus.RETRY_SCHEDULED
    )
    later = datetime.now(UTC) + timedelta(seconds=2)
    second = (
        await queue.claim(
            worker_id="worker-b",
            limit=1,
            lease_seconds=30,
            now=later,
        )
    )[0]
    assert await queue.fail(
        job=second,
        error_code="Provider/secret detail",
        now=later,
    ) is BackgroundJobStatus.DEAD_LETTER
    dead = await queue.get(job_id)
    assert dead is not None
    assert dead.last_error_code == "Provider_secret_detail"
    assert dead.last_error_detail is None

    await queue.replay_dead_letter(job_id=job_id, actor="project-owner")
    replayed = await queue.get(job_id)
    assert replayed is not None
    assert replayed.status == BackgroundJobStatus.PENDING.value
    assert replayed.replay_count == 1
    assert replayed.last_replayed_by == "project-owner"
    assert replayed.attempt_count == 0

    async with AsyncSessionFactory() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()
