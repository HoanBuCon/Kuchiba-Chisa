"""A v2 turn queues its memory job in its own transaction; the worker obeys consent (MEM-005)."""

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
from app.infrastructure.background.thread_memory_handler import ThreadMemoryExtractionJobHandler
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.background_job import DurableBackgroundJobModel
from app.infrastructure.database.repositories.background_job_queue import (
    PostgresDurableBackgroundJobQueue,
)
from app.infrastructure.database.repositories.privacy_preference import (
    SqlAlchemyPrivacyPreferenceRepository,
)
from app.infrastructure.database.repositories.thread_store import PostgresThreadStore
from app.infrastructure.database.repositories.turn_commit import PostgresTurnCommit, memory_job
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str


class Extractor:
    def __init__(self) -> None:
        self.calls = []

    async def extract_and_store_batch(self, **arguments) -> None:
        self.calls.append(arguments)


def _turn(thread_id, question="Anh thích cà phê muối.") -> TurnRecord:
    return TurnRecord(
        thread_id=thread_id,
        turn_id=uuid4(),
        question=question,
        answer="Em nhớ rồi Senpai.",
        mode_requested=ChatMode.ADVANCED,
        mode_effective=ChatMode.ADVANCED,
        lane="companion",
        status="companion",
    )


async def _member(consent: bool) -> str:
    owner = normalize_user_id_str(f"it-memory-{uuid4()}")
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


async def _queued(owner: str) -> int:
    job_type = BackgroundJobType.THREAD_MEMORY_EXTRACTION.value
    async with AsyncSessionFactory() as session:
        return await session.scalar(
            select(func.count()).where(
                DurableBackgroundJobModel.principal_id == normalize_user_id(owner),
                DurableBackgroundJobModel.job_type == job_type,
            )
        )


def _claimed(record: TurnRecord, owner: str) -> ClaimedBackgroundJob:
    job = memory_job(record, owner)
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


def _handler(extractor: Extractor) -> ThreadMemoryExtractionJobHandler:
    return ThreadMemoryExtractionJobHandler(
        AsyncSessionFactory, BackgroundTurnSourceReader(AsyncSessionFactory), extractor
    )


async def test_the_memory_job_is_queued_once_with_the_turn_and_only_when_asked() -> None:
    owner = await _member(consent=True)
    threads = PostgresThreadStore(AsyncSessionFactory)
    queue = PostgresDurableBackgroundJobQueue(AsyncSessionFactory)
    commit = PostgresTurnCommit(AsyncSessionFactory, queue=queue)
    thread = await threads.create(owner, "web", ChatMode.ADVANCED)
    record = _turn(thread.id)

    await commit.commit(_turn(thread.id), owner, {})
    assert await _queued(owner) == 0

    assert await commit.commit(record, owner, {}, remember=True)
    assert not await commit.commit(record, owner, {}, remember=True)
    assert await _queued(owner) == 1


async def test_the_worker_extracts_from_the_stored_turn_with_its_history() -> None:
    owner = await _member(consent=True)
    threads = PostgresThreadStore(AsyncSessionFactory)
    thread = await threads.create(owner, "web", ChatMode.ADVANCED)
    await threads.save_turn(_turn(thread.id, question="Anh tên là Khoa."))
    record = _turn(thread.id)
    await threads.save_turn(record)
    extractor = Extractor()

    await _handler(extractor).handle(_claimed(record, owner))

    call = extractor.calls[0]
    assert call["user_id"] == owner
    assert call["current_user_message"] == "Anh thích cà phê muối."
    assert call["history"][0] == {"role": "user", "content": "Anh tên là Khoa."}


async def test_the_worker_stores_nothing_without_consent_or_for_another_owner() -> None:
    owner = await _member(consent=False)
    stranger = await _member(consent=True)
    threads = PostgresThreadStore(AsyncSessionFactory)
    thread = await threads.create(owner, "web", ChatMode.ADVANCED)
    record = _turn(thread.id)
    await threads.save_turn(record)
    extractor = Extractor()

    with pytest.raises(DurableJobPayloadError):
        await _handler(extractor).handle(_claimed(record, owner))
    with pytest.raises(DurableJobPayloadError):
        await _handler(extractor).handle(_claimed(record, stranger))

    assert extractor.calls == []
