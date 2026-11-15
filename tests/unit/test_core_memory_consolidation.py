"""Consolidation folds memories into core memory without overwriting the person (MEM-005/006)."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from app.domain.interfaces.core_memory_consolidation import ConsolidationState, EpisodicMemory
from app.domain.interfaces.llm_provider import LLMPurpose
from app.domain.models.background_job import BackgroundJobType, ClaimedBackgroundJob
from app.domain.services.core_memory import MAX_ITEM_CHARS, MAX_ITEMS
from app.domain.services.core_memory_consolidator import CoreMemoryConsolidator
from app.infrastructure.background.core_memory_consolidation_handler import (
    CONSOLIDATION_WINDOW_SECONDS,
    ConsolidationJobScheduler,
    CoreMemoryConsolidationJobHandler,
    consolidation_job,
)
from app.infrastructure.background.job_handlers import DurableJobPayloadError
from app.infrastructure.background.thread_memory_handler import ThreadMemoryExtractionJobHandler

USER = uuid.uuid4()


class Store:
    """In-memory twin of the Postgres store: same version check, same watermark rules."""

    def __init__(self, content=None, version=None, owned=None) -> None:
        self.content = content or {}
        self.version = version
        self.owned = owned or {}
        self.through = 0
        self.commits = 0

    async def load(self, owner):
        return ConsolidationState(dict(self.content), self.version, self.through, dict(self.owned))

    async def commit(self, owner, *, expected_version, content, job_owned, consolidated_through):
        if self.version != expected_version:
            return False
        if content is not None:
            self.content = dict(content)
            self.version = (self.version or 0) + 1
        self.owned = dict(job_owned)
        self.through = consolidated_through
        self.commits += 1
        return True

    def edit_by_person(self, content) -> None:
        self.content = content
        self.version = (self.version or 0) + 1


class Source:
    def __init__(self, memories) -> None:
        self.memories = memories
        self.requested_from = []

    async def list_user_memories_since(self, user_id, created_at_from, limit):
        self.requested_from.append(created_at_from)
        return [m for m in self.memories if m.created_at >= created_at_from][:limit]


class Llm:
    def __init__(self, parsed=None, error=None, during=None) -> None:
        self.parsed = parsed or {}
        self.error = error
        self.during = during
        self.prompts = []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        if self.during:
            self.during()
        if self.error:
            raise self.error
        return SimpleNamespace(parsed=self.parsed)


def _memories(*texts, start=100):
    return [EpisodicMemory(text, start + index) for index, text in enumerate(texts)]


def _consolidator(store, llm, memories):
    return CoreMemoryConsolidator(llm, store, Source(memories))


async def test_adds_new_facts_and_marks_them_job_owned() -> None:
    store = Store()
    llm = Llm({"add": {"preferences": ["Senpai thich ca phe muoi"]}, "retire": {}})

    assert await _consolidator(store, llm, _memories("Anh thich ca phe muoi")).consolidate("u")

    assert store.content["preferences"] == ["Senpai thich ca phe muoi"]
    assert store.owned["preferences"] == ["Senpai thich ca phe muoi"]
    assert store.version == 1
    assert llm.prompts[0].purpose is LLMPurpose.MEMORY_RECONCILIATION


async def test_person_written_entries_survive_even_when_the_model_retires_them() -> None:
    store = Store(
        {"preferences": ["Likes tea (typed by the person)", "Likes rain (job wrote it)"]},
        version=3,
        owned={"preferences": ["Likes rain (job wrote it)"]},
    )
    llm = Llm(
        {
            "add": {},
            "retire": {
                "preferences": ["Likes tea (typed by the person)", "Likes rain (job wrote it)"]
            },
        }
    )

    await _consolidator(store, llm, _memories("Anh khong thich mua nua")).consolidate("u")

    assert store.content["preferences"] == ["Likes tea (typed by the person)"]
    assert store.owned["preferences"] == []


async def test_entry_the_person_edited_stops_being_job_owned() -> None:
    store = Store(
        {"promises": ["Person reworded this entry"]},
        version=2,
        owned={"promises": ["Original job wording"]},
    )
    llm = Llm({"add": {}, "retire": {"promises": ["Original job wording"]}})

    await _consolidator(store, llm, _memories("Da doc xong cuon sach")).consolidate("u")

    assert store.content["promises"] == ["Person reworded this entry"]
    assert store.owned["promises"] == []


async def test_a_person_set_nickname_is_never_replaced() -> None:
    store = Store({"nickname": "Anh Hai"}, version=1)
    llm = Llm({"nickname": "Senpai", "add": {}, "retire": {}})

    await _consolidator(store, llm, _memories("Goi anh la Senpai")).consolidate("u")

    assert store.content["nickname"] == "Anh Hai"


async def test_lost_race_with_a_hand_edit_writes_nothing_and_keeps_the_watermark() -> None:
    store = Store({"preferences": ["Old entry typed earlier"]}, version=1)
    edited = {"preferences": ["Entry the person typed meanwhile"]}
    llm = Llm(
        {"add": {"preferences": ["Likes ca phe muoi a lot"]}, "retire": {}},
        during=lambda: store.edit_by_person(edited),
    )

    stored = await _consolidator(store, llm, _memories("Anh thich ca phe muoi")).consolidate("u")

    assert stored is False
    assert store.content == edited
    assert store.through == 0
    assert store.commits == 0


async def test_size_limits_hold_and_person_entries_are_never_evicted() -> None:
    typed = [f"Entry typed by the person {n}" for n in range(MAX_ITEMS - 2)]
    store = Store({"milestones": typed}, version=1)
    flood = [f"Generated milestone number {n}" for n in range(30)]
    flood.insert(0, "x" * (MAX_ITEM_CHARS + 50))
    llm = Llm({"add": {"milestones": flood}, "retire": {}})

    await _consolidator(store, llm, _memories("a lot happened")).consolidate("u")

    assert len(store.content["milestones"]) == MAX_ITEMS
    assert store.content["milestones"][: MAX_ITEMS - 2] == typed
    assert all(len(item) <= MAX_ITEM_CHARS for item in store.content["milestones"])


async def test_duplicates_and_personal_identifiers_are_not_stored() -> None:
    store = Store({"preferences": ["Likes jasmine tea"]}, version=1)
    llm = Llm(
        {
            "add": {
                "preferences": [
                    "likes   JASMINE tea",
                    "Contact: anh@example.com for news",
                    "Likes [REDACTED_PHONE] style",
                    "Plays guitar on weekends",
                ]
            },
            "retire": {},
        }
    )

    await _consolidator(store, llm, _memories("anh@example.com choi guitar")).consolidate("u")

    assert store.content["preferences"] == ["Likes jasmine tea", "Plays guitar on weekends"]


async def test_prompt_never_carries_raw_identifiers() -> None:
    llm = Llm()

    await _consolidator(Store(), llm, _memories("Email la anh@example.com")).consolidate("u")

    assert "anh@example.com" not in llm.prompts[0].user_message


async def test_watermark_moves_only_after_the_write_succeeded() -> None:
    store = Store()
    memories = _memories("first fact here", "second fact here", start=500)

    failing = _consolidator(store, Llm(error=RuntimeError("provider down")), memories)
    with pytest.raises(RuntimeError):
        await failing.consolidate("u")
    assert store.through == 0

    await _consolidator(store, Llm({"add": {}, "retire": {}}), memories).consolidate("u")
    assert store.through == 501


async def test_nothing_new_makes_no_llm_call() -> None:
    store = Store()
    store.through = 900
    llm = Llm()

    await _consolidator(store, llm, _memories("old fact only", start=100)).consolidate("u")

    assert llm.prompts == []
    assert store.commits == 0


async def test_unchanged_profile_only_moves_the_watermark() -> None:
    store = Store()

    await _consolidator(store, Llm({"add": {}, "retire": {}}), _memories("small talk")).consolidate(
        "u"
    )

    assert store.version is None
    assert store.through == 100


def _job(user_id=USER, principal=USER):
    return ClaimedBackgroundJob(
        job_id=uuid.uuid4(),
        job_type=BackgroundJobType.CORE_MEMORY_CONSOLIDATION,
        idempotency_key="core-memory-consolidation:key",
        payload={"user_id": str(user_id)},
        payload_version=1,
        principal_id=principal,
        tenant_id=None,
        attempt_count=1,
        max_attempts=3,
        lease_owner="w",
        lease_token=uuid.uuid4(),
        lease_expires_at=None,
    )


class Consent:
    def __init__(self, allowed=True) -> None:
        self.allowed = allowed

    async def ensure_consent(self, principal_id):
        if not self.allowed:
            raise DurableJobPayloadError("long-term memory consent is not active")
        return str(principal_id)


async def test_withdrawn_consent_blocks_the_job_before_any_read_or_write() -> None:
    store = Store()
    llm = Llm({"add": {"preferences": ["Likes ca phe muoi a lot"]}, "retire": {}})
    handler = CoreMemoryConsolidationJobHandler(
        Consent(allowed=False), _consolidator(store, llm, _memories("a fact"))
    )

    with pytest.raises(DurableJobPayloadError):
        await handler.handle(_job())

    assert llm.prompts == []
    assert store.commits == 0


async def test_handler_rejects_a_payload_for_another_person() -> None:
    handler = CoreMemoryConsolidationJobHandler(
        Consent(), _consolidator(Store(), Llm(), _memories("a fact"))
    )

    with pytest.raises(DurableJobPayloadError):
        await handler.handle(_job(user_id=uuid.uuid4()))


async def test_a_lost_race_is_a_quiet_no_op_for_the_queue() -> None:
    store = Store(version=1)
    llm = Llm({"add": {}, "retire": {}}, during=lambda: store.edit_by_person({}))
    handler = CoreMemoryConsolidationJobHandler(
        Consent(), _consolidator(store, llm, _memories("a fact"))
    )

    await handler.handle(_job())

    assert store.through == 0


def test_a_burst_inside_one_window_shares_one_idempotency_key() -> None:
    first = consolidation_job(USER, now=7_200.0)
    same_window = consolidation_job(USER, now=7_200.0 + CONSOLIDATION_WINDOW_SECONDS - 1)
    next_window = consolidation_job(USER, now=7_200.0 + CONSOLIDATION_WINDOW_SECONDS)
    other_person = consolidation_job(uuid.uuid4(), now=7_200.0)

    assert first.idempotency_key == same_window.idempotency_key
    assert first.idempotency_key != next_window.idempotency_key
    assert first.idempotency_key != other_person.idempotency_key
    assert first.payload == {"user_id": str(USER)}
    assert first.job_type is BackgroundJobType.CORE_MEMORY_CONSOLIDATION


class Queue:
    """Same contract as the Postgres outbox: a repeated key returns the existing job."""

    def __init__(self) -> None:
        self.jobs = {}

    async def enqueue(self, session, submission):
        return self.jobs.setdefault(submission.idempotency_key, submission)


class Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *error):
        return False

    async def commit(self):
        return None


class Extractor:
    def __init__(self, stored) -> None:
        self.stored = stored

    async def extract_and_store_batch(self, **arguments):
        return self.stored


def _extraction_handler(stored, queue):
    handler = ThreadMemoryExtractionJobHandler(
        Session,
        Consent(),
        Extractor(stored),
        ConsolidationJobScheduler(Session, queue),
    )
    turn = SimpleNamespace(question="q", answer="a")

    async def load(user_id, thread_id, turn_id):
        return turn, []

    handler._load = load
    return handler


def _extraction_job():
    job = _job()
    return ClaimedBackgroundJob(
        **{
            **job.__dict__,
            "job_type": BackgroundJobType.THREAD_MEMORY_EXTRACTION,
            "payload": {
                "user_id": str(USER),
                "thread_id": str(uuid.uuid4()),
                "turn_id": str(uuid.uuid4()),
            },
        }
    )


async def test_several_turns_that_store_memories_queue_one_consolidation_job() -> None:
    queue = Queue()
    handler = _extraction_handler(2, queue)

    for _ in range(3):
        await handler.handle(_extraction_job())

    assert len(queue.jobs) == 1


async def test_a_turn_that_stored_nothing_queues_no_consolidation() -> None:
    queue = Queue()

    await _extraction_handler(0, queue).handle(_extraction_job())

    assert queue.jobs == {}


async def test_a_queueing_failure_does_not_fail_the_extraction_job() -> None:
    class BrokenQueue:
        async def enqueue(self, session, submission):
            raise OperationalError("insert", {}, RuntimeError("database unavailable"))

    await _extraction_handler(1, BrokenQueue()).handle(_extraction_job())
