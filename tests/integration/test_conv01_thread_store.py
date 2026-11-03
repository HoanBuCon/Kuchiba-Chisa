"""Thread store against isolated PostgreSQL: owner scoping, idempotent turns, cascade delete."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.models.thread import ChatMode, TurnRecord
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.repositories.core_memory_store import (
    PostgresCoreMemoryStore,
    SqlAlchemyPersonalDataPurge,
)
from app.infrastructure.database.repositories.thread_store import PostgresThreadStore

OWNER = f"it-owner-{uuid4()}"
OTHER = f"it-other-{uuid4()}"


def _turn(thread_id, turn_id=None, answer="Answer.") -> TurnRecord:
    return TurnRecord(
        thread_id=thread_id,
        turn_id=turn_id or uuid4(),
        question="Question?",
        answer=answer,
        mode_requested=ChatMode.ADVANCED,
        mode_effective=ChatMode.ADVANCED,
        lane="advanced",
        status="answered",
        llm_calls=2,
        citations=({"evidence_id": "wiki:1:a"},),
        degraded=("translation_failed",),
    )


@pytest.fixture
def store() -> PostgresThreadStore:
    return PostgresThreadStore(AsyncSessionFactory)


async def test_a_thread_is_visible_only_to_its_owner(store) -> None:
    thread = await store.create(OWNER, "web", ChatMode.ADVANCED)

    assert (await store.get(thread.id, OWNER)).id == thread.id
    assert await store.get(thread.id, OTHER) is None
    assert await store.update(thread.id, OTHER, title="x", mode=None) is None
    assert not await store.delete(thread.id, OTHER)
    assert thread.id in {item.id for item in await store.list_for(OWNER, 50)}
    assert thread.id not in {item.id for item in await store.list_for(OTHER, 50)}


async def test_update_changes_title_and_mode(store) -> None:
    thread = await store.create(OWNER, "web", ChatMode.ADVANCED)

    updated = await store.update(thread.id, OWNER, title="Lore", mode=ChatMode.AGENTIC)

    assert (updated.title, updated.mode) == ("Lore", ChatMode.AGENTIC)


async def test_a_retried_turn_is_stored_once_and_keeps_its_first_answer(store) -> None:
    thread = await store.create(OWNER, "web", ChatMode.ADVANCED)
    turn_id = uuid4()

    await store.save_turn(_turn(thread.id, turn_id, "First."))
    await store.save_turn(_turn(thread.id, turn_id, "Second."))

    assert (await store.find_turn(thread.id, turn_id)).answer == "First."
    assert len(await store.recent_turns(thread.id, 10)) == 1


async def test_turn_round_trip_keeps_audit_fields(store) -> None:
    thread = await store.create(OWNER, "web", ChatMode.ADVANCED)
    record = _turn(thread.id)

    await store.save_turn(record)

    assert await store.find_turn(thread.id, record.turn_id) == record


async def test_deleting_a_thread_deletes_its_turns(store) -> None:
    thread = await store.create(OWNER, "web", ChatMode.ADVANCED)
    record = _turn(thread.id)
    await store.save_turn(record)

    assert await store.delete(thread.id, OWNER)

    assert await store.find_turn(thread.id, record.turn_id) is None


async def test_purge_removes_threads_turns_and_core_memory(store) -> None:
    owner = f"it-purge-{uuid4()}"
    thread = await store.create(owner, "web", ChatMode.ADVANCED)
    record = _turn(thread.id)
    await store.save_turn(record)
    core = PostgresCoreMemoryStore(AsyncSessionFactory)
    await core.put(owner, {"nickname": "A"})

    async with AsyncSessionFactory() as session:
        purge = SqlAlchemyPersonalDataPurge(session)
        await purge.delete_threads(owner)
        await purge.delete_core_memory(owner)
        await session.commit()

    assert await store.get(thread.id, owner) is None
    assert await store.find_turn(thread.id, record.turn_id) is None
    assert await core.get(owner) is None


async def test_core_memory_round_trip_and_version(store) -> None:
    owner = f"it-core-{uuid4()}"
    core = PostgresCoreMemoryStore(AsyncSessionFactory)

    await core.put(owner, {"nickname": "A"})
    await core.put(owner, {"nickname": "B"})

    assert await core.get(owner) == {"nickname": "B"}
    assert await core.delete(owner)
    assert not await core.delete(owner)
