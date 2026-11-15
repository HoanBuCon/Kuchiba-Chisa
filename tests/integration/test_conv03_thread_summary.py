"""The summary job rides the turn transaction, is versioned and dies with its thread (CONV-003)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.domain.models.background_job import BackgroundJobType, ClaimedBackgroundJob
from app.domain.models.thread import ChatMode, TurnRecord
from app.infrastructure.background.job_handlers import (
    BackgroundTurnSourceReader,
    DurableJobPayloadError,
)
from app.infrastructure.background.thread_summary_handler import ThreadSummaryJobHandler
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.background_job import DurableBackgroundJobModel
from app.infrastructure.database.models.thread import ThreadSummaryModel
from app.infrastructure.database.repositories.background_job_queue import (
    PostgresDurableBackgroundJobQueue,
)
from app.infrastructure.database.repositories.privacy_preference import (
    SqlAlchemyPrivacyPreferenceRepository,
)
from app.infrastructure.database.repositories.thread_store import PostgresThreadStore
from app.infrastructure.database.repositories.thread_summary_store import (
    PostgresThreadSummaryStore,
)
from app.infrastructure.database.repositories.turn_commit import PostgresTurnCommit, summary_job
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str


class Summarizer:
    def __init__(self) -> None:
        self.calls = []

    async def summarize(self, previous, turns):
        self.calls.append((previous, [turn.question for turn in turns]))
        return f"Tóm tắt {len(self.calls)}."


def _turn(thread_id, number: int) -> TurnRecord:
    return TurnRecord(
        thread_id=thread_id,
        turn_id=uuid4(),
        question=f"Câu hỏi {number}",
        answer=f"Trả lời {number}",
        mode_requested=ChatMode.ADVANCED,
        mode_effective=ChatMode.ADVANCED,
        lane="advanced",
        status="grounded",
    )


def _claimed(record: TurnRecord, owner: str) -> ClaimedBackgroundJob:
    job = summary_job(record, owner, 0)
    return ClaimedBackgroundJob(
        job_id=uuid4(),
        job_type=job.job_type,
        idempotency_key=job.idempotency_key,
        payload=job.payload,
        payload_version=1,
        principal_id=job.principal_id,
        tenant_id=None,
        attempt_count=1,
        max_attempts=3,
        lease_owner="test",
        lease_token=uuid4(),
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )


async def _member(consent: bool = True) -> str:
    owner = normalize_user_id_str(f"it-summary-{uuid4()}")
    user_id = normalize_user_id(owner)
    async with AsyncSessionFactory() as session:
        await SqlAlchemyUserRepository(session).get_or_create_user(user_id)
        await SqlAlchemyPrivacyPreferenceRepository(session).set_memory_policy(
            user_id,
            enabled=consent,
            retention_days=30 if consent else None,
            changed_at=datetime.now(UTC),
        )
        await session.commit()
    return owner


def _handler(store, summarizer) -> ThreadSummaryJobHandler:
    consent = BackgroundTurnSourceReader(AsyncSessionFactory)
    return ThreadSummaryJobHandler(AsyncSessionFactory, consent, store, summarizer)


async def _stored_thread(owner: str, turns: int):
    threads = PostgresThreadStore(AsyncSessionFactory)
    thread = await threads.create(owner, "web", ChatMode.ADVANCED)
    records = [_turn(thread.id, number) for number in range(turns)]
    for record in records:
        await threads.save_turn(record)
    return thread, records


async def _queued(owner: str) -> int:
    async with AsyncSessionFactory() as session:
        return await session.scalar(
            select(func.count()).where(
                DurableBackgroundJobModel.principal_id == normalize_user_id(owner),
                DurableBackgroundJobModel.job_type == BackgroundJobType.THREAD_SUMMARY.value,
            )
        )


async def test_the_summary_job_is_queued_once_per_summary_version() -> None:
    owner = await _member()
    thread, _ = await _stored_thread(owner, 0)
    queue = PostgresDurableBackgroundJobQueue(AsyncSessionFactory)
    commit = PostgresTurnCommit(AsyncSessionFactory, queue=queue)
    record = _turn(thread.id, 1)

    assert await commit.commit(record, owner, {}, summary_version=0)
    assert not await commit.commit(record, owner, {}, summary_version=0)
    assert await commit.commit(_turn(thread.id, 2), owner, {}, summary_version=0)
    assert await commit.commit(_turn(thread.id, 3), owner, {}, summary_version=1)

    assert await _queued(owner) == 2


async def test_the_worker_rolls_the_summary_forward_and_deleting_the_thread_removes_it() -> None:
    owner = await _member()
    thread, records = await _stored_thread(owner, 6)
    store = PostgresThreadSummaryStore(AsyncSessionFactory)
    summarizer = Summarizer()
    handler = _handler(store, summarizer)

    await handler.handle(_claimed(records[-1], owner))
    first = await store.get(thread.id)
    await handler.handle(_claimed(records[-1], owner))

    assert first is not None and first.version == 1
    assert first.covered_turn_id == records[3].turn_id
    # The second run finds only the two newest turns uncovered and leaves the summary alone.
    assert (await store.get(thread.id)) == first
    assert summarizer.calls == [(None, [r.question for r in records[:4]])]

    assert await PostgresThreadStore(AsyncSessionFactory).delete(thread.id, owner)
    async with AsyncSessionFactory() as session:
        remaining = await session.scalar(
            select(func.count()).where(ThreadSummaryModel.thread_id == thread.id)
        )
    assert remaining == 0


async def test_the_worker_summarizes_nothing_once_consent_is_withdrawn() -> None:
    owner = await _member(consent=False)
    thread, records = await _stored_thread(owner, 6)
    store = PostgresThreadSummaryStore(AsyncSessionFactory)
    summarizer = Summarizer()

    with pytest.raises(DurableJobPayloadError):
        await _handler(store, summarizer).handle(_claimed(records[-1], owner))

    assert summarizer.calls == [] and await store.get(thread.id) is None


async def test_a_stale_writer_cannot_overwrite_a_newer_summary() -> None:
    owner = normalize_user_id_str(f"it-summary-{uuid4()}")
    thread, records = await _stored_thread(owner, 3)
    store = PostgresThreadSummaryStore(AsyncSessionFactory)

    assert await store.save(thread.id, "Một.", records[0].turn_id, expected_version=None)
    assert await store.save(thread.id, "Hai.", records[1].turn_id, expected_version=1)
    assert not await store.save(thread.id, "Muộn.", records[2].turn_id, expected_version=1)
    assert not await store.save(thread.id, "Trùng.", records[2].turn_id, expected_version=None)

    current = await store.get(thread.id)
    assert (current.summary, current.version) == ("Hai.", 2)
