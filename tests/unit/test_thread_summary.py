"""Rolling thread summary: store versioning, commit outbox, job handler (CONV-002..004, REL-007)."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.domain.models.background_job import BackgroundJobType, ClaimedBackgroundJob
from app.domain.models.thread import ChatMode, ThreadSummary, TurnRecord
from app.domain.services.conversation_window import SUMMARY_KEEP_RECENT_TURNS
from app.infrastructure.background.job_handlers import DurableJobPayloadError
from app.infrastructure.background.llm_thread_summarizer import (
    LlmThreadSummarizer,
    ThreadSummaryError,
)
from app.infrastructure.background.thread_summary_handler import (
    MAX_TURNS_PER_SUMMARY,
    ThreadSummaryJobHandler,
)
from app.infrastructure.database.models.thread import ThreadSummaryModel
from app.infrastructure.database.repositories.thread_summary_store import (
    PostgresThreadSummaryStore,
    _first_version,
    _next_version,
)
from app.infrastructure.database.repositories.turn_commit import PostgresTurnCommit, summary_job
from app.infrastructure.observability.otel import _JOB_TYPES
from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str

OWNER = normalize_user_id_str("summary-owner")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _record(thread_id: uuid.UUID | None = None) -> TurnRecord:
    return TurnRecord(
        thread_id=thread_id or uuid.uuid4(),
        turn_id=uuid.uuid4(),
        question="Anh hỏi gì đó.",
        answer="Em trả lời.",
        mode_requested=ChatMode.ADVANCED,
        mode_effective=ChatMode.ADVANCED,
        lane="advanced",
        status="grounded",
    )


class Session:
    """Stands in for an AsyncSession; the result of every statement is a fixed rowcount."""

    def __init__(self, rowcount: int = 1, error: Exception | None = None) -> None:
        self.rowcount = rowcount
        self.error = error
        self.statements = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def execute(self, statement):
        self.statements.append(statement)
        if self.error:
            raise self.error
        return SimpleNamespace(rowcount=self.rowcount)

    async def commit(self) -> None:
        self.committed = True


class Queue:
    def __init__(self) -> None:
        self.jobs = []

    async def enqueue(self, session, submission) -> uuid.UUID:
        self.jobs.append(submission)
        return uuid.uuid4()


async def test_commit_queues_a_summary_job_in_the_turn_transaction() -> None:
    session, queue = Session(), Queue()
    record = _record()

    stored = await PostgresTurnCommit(lambda: session, queue=queue).commit(
        record, OWNER, {}, summarize=True
    )

    assert stored and session.committed
    (job,) = queue.jobs
    assert job.job_type is BackgroundJobType.THREAD_SUMMARY
    assert job.principal_id == normalize_user_id(OWNER)
    assert job.idempotency_key == f"thread-summary:{record.thread_id}:{record.turn_id}"
    assert job.payload["through_turn_id"] == str(record.turn_id)
    assert record.question not in str(job.payload)


async def test_commit_queues_no_summary_job_when_none_is_due() -> None:
    session, queue = Session(), Queue()

    await PostgresTurnCommit(lambda: session, queue=queue).commit(_record(), OWNER, {})

    assert queue.jobs == []


async def test_a_retry_that_lost_the_race_queues_nothing() -> None:
    session, queue = Session(rowcount=0), Queue()

    stored = await PostgresTurnCommit(lambda: session, queue=queue).commit(
        _record(), OWNER, {}, remember=True, summarize=True
    )

    assert not stored
    assert queue.jobs == []


async def test_memory_and_summary_jobs_share_one_commit() -> None:
    session, queue = Session(), Queue()

    await PostgresTurnCommit(lambda: session, queue=queue).commit(
        _record(), OWNER, {}, remember=True, summarize=True
    )

    assert [job.job_type for job in queue.jobs] == [
        BackgroundJobType.THREAD_MEMORY_EXTRACTION,
        BackgroundJobType.THREAD_SUMMARY,
    ]


def test_summary_job_type_is_allowed_in_telemetry() -> None:
    assert BackgroundJobType.THREAD_SUMMARY.value in _JOB_TYPES


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_update_is_guarded_by_the_expected_version() -> None:
    sql = _sql(_next_version(uuid.uuid4(), "text", uuid.uuid4(), 3))

    assert "UPDATE thread_summaries" in sql
    assert "thread_summaries.version = %(version_1)s" in sql
    assert "SET summary=%(summary)s, version=%(version)s" in sql


def test_first_write_never_replaces_an_existing_row() -> None:
    sql = _sql(_first_version(uuid.uuid4(), "text", uuid.uuid4()))

    assert "ON CONFLICT (thread_id) DO NOTHING" in sql


async def test_store_reports_a_lost_race_as_false() -> None:
    session = Session(rowcount=0)
    store = PostgresThreadSummaryStore(lambda: session)

    saved = await store.save(uuid.uuid4(), "text", uuid.uuid4(), expected_version=2)

    assert saved is False


async def test_store_reports_a_deleted_thread_as_false() -> None:
    session = Session(error=IntegrityError("insert", {}, Exception("fk")))
    store = PostgresThreadSummaryStore(lambda: session)

    assert not await store.save(uuid.uuid4(), "text", uuid.uuid4(), expected_version=None)


def test_summary_row_is_removed_with_its_thread() -> None:
    (foreign_key,) = ThreadSummaryModel.__table__.c.thread_id.foreign_keys
    migration = next(
        (PROJECT_ROOT / "alembic_migrations" / "versions").glob("*_add_thread_summaries.py")
    )

    assert foreign_key.ondelete == "CASCADE"
    assert ThreadSummaryModel.__table__.c.thread_id.primary_key
    assert 'ondelete="CASCADE"' in migration.read_text(encoding="utf-8")


class SummaryStore:
    """Versioned like the real store: a save succeeds only against the version it read."""

    def __init__(self, current: ThreadSummary | None = None) -> None:
        self.current = current
        self.saves = []

    async def get(self, thread_id):
        return self.current

    async def save(self, thread_id, summary, covered_turn_id, *, expected_version):
        self.saves.append((summary, covered_turn_id, expected_version))
        stored = self.current.version if self.current else None
        if stored != expected_version:
            return False
        self.current = ThreadSummary(summary, (stored or 0) + 1, covered_turn_id)
        return True


class Summarizer:
    def __init__(self) -> None:
        self.calls = []

    async def summarize(self, previous, turns):
        self.calls.append((previous, list(turns)))
        return "Tóm tắt mới."


def _stored_turns(count: int) -> list[SimpleNamespace]:
    start = datetime(2026, 11, 15, tzinfo=UTC)
    return [
        SimpleNamespace(
            turn_id=uuid.uuid4(),
            question=f"q{number}",
            answer=f"a{number}",
            created_at=start + timedelta(minutes=number),
        )
        for number in range(count)
    ]


def _job(through: uuid.UUID) -> ClaimedBackgroundJob:
    owner = normalize_user_id(OWNER)
    return ClaimedBackgroundJob(
        job_id=uuid.uuid4(),
        job_type=BackgroundJobType.THREAD_SUMMARY,
        idempotency_key="thread-summary:test",
        payload={
            "user_id": str(owner),
            "thread_id": str(uuid.uuid4()),
            "through_turn_id": str(through),
        },
        payload_version=1,
        principal_id=owner,
        tenant_id=None,
        attempt_count=1,
        max_attempts=3,
        lease_owner="worker",
        lease_token=uuid.uuid4(),
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def _handler(store, summarizer, turns):
    handler = ThreadSummaryJobHandler(lambda: None, store, summarizer)

    async def uncovered(*_arguments):
        return turns

    handler._uncovered = uncovered
    return handler


async def test_handler_writes_the_next_version_and_keeps_the_newest_turns_out() -> None:
    turns = _stored_turns(6)
    store = SummaryStore(ThreadSummary("Cũ.", 4, uuid.uuid4()))
    summarizer = Summarizer()

    await _handler(store, summarizer, turns).handle(_job(turns[-1].turn_id))

    covered = turns[:-SUMMARY_KEEP_RECENT_TURNS]
    assert summarizer.calls[0][0] == "Cũ."
    assert [turn.question for turn in summarizer.calls[0][1]] == [t.question for t in covered]
    assert store.current == ThreadSummary("Tóm tắt mới.", 5, covered[-1].turn_id)


async def test_handler_creates_the_first_summary_without_a_previous_one() -> None:
    turns = _stored_turns(5)
    store, summarizer = SummaryStore(), Summarizer()

    await _handler(store, summarizer, turns).handle(_job(turns[-1].turn_id))

    assert summarizer.calls[0][0] is None
    assert store.current.version == 1


async def test_handler_loses_a_race_without_overwriting() -> None:
    turns = _stored_turns(6)
    winner = ThreadSummary("Của job khác.", 5, turns[1].turn_id)
    store = SummaryStore(ThreadSummary("Cũ.", 4, uuid.uuid4()))
    summarizer = Summarizer()
    handler = _handler(store, summarizer, turns)
    original_save = store.save

    async def racing_save(*arguments, **keywords):
        store.current = winner
        return await original_save(*arguments, **keywords)

    store.save = racing_save

    await handler.handle(_job(turns[-1].turn_id))

    assert store.current == winner


async def test_handler_does_nothing_when_only_the_newest_turns_are_uncovered() -> None:
    turns = _stored_turns(SUMMARY_KEEP_RECENT_TURNS)
    store, summarizer = SummaryStore(), Summarizer()

    await _handler(store, summarizer, turns).handle(_job(turns[-1].turn_id))

    assert summarizer.calls == [] and store.saves == []


async def test_handler_summarizes_a_bounded_batch() -> None:
    turns = _stored_turns(MAX_TURNS_PER_SUMMARY + 10)
    store, summarizer = SummaryStore(), Summarizer()

    await _handler(store, summarizer, turns).handle(_job(turns[-1].turn_id))

    assert len(summarizer.calls[0][1]) == MAX_TURNS_PER_SUMMARY
    assert store.current.covered_turn_id == turns[MAX_TURNS_PER_SUMMARY - 1].turn_id


async def test_handler_rejects_a_payload_for_another_principal() -> None:
    job = replace(_job(uuid.uuid4()), principal_id=uuid.uuid4())

    with pytest.raises(DurableJobPayloadError):
        await _handler(SummaryStore(), Summarizer(), []).handle(job)


async def test_handler_rejects_a_foreign_job_type() -> None:
    foreign = replace(_job(uuid.uuid4()), job_type=BackgroundJobType.PRIVATE_SUMMARY)

    with pytest.raises(DurableJobPayloadError):
        await _handler(SummaryStore(), Summarizer(), []).handle(foreign)


class Llm:
    def __init__(self, parsed) -> None:
        self.parsed = parsed
        self.prompts = []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(parsed=self.parsed)


async def test_summarizer_sends_previous_summary_and_turns_through_the_gateway() -> None:
    llm = Llm({"summary": "  Gọn.  "})
    turns = _stored_turns(2)

    text = await LlmThreadSummarizer(llm).summarize("Cũ.", turns)

    prompt = llm.prompts[0]
    assert text == "Gọn."
    assert prompt.purpose.value == "conversation_summary"
    assert "Cũ." in prompt.user_message and "q1" in prompt.user_message


async def test_summarizer_refuses_an_empty_summary() -> None:
    with pytest.raises(ThreadSummaryError):
        await LlmThreadSummarizer(Llm({"summary": " "})).summarize(None, _stored_turns(1))


def test_summary_job_idempotency_key_is_per_thread_and_turn() -> None:
    record = _record()

    first = summary_job(record, OWNER).idempotency_key
    assert first == summary_job(record, OWNER).idempotency_key
    assert first != summary_job(_record(), OWNER).idempotency_key
