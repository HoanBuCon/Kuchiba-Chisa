"""Turn and emotion commit together on isolated PostgreSQL; a lost race moves nothing (REL-007)."""

from __future__ import annotations

from uuid import uuid4

from app.domain.models.thread import ChatMode, TurnRecord
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.repositories.emotion_repository import (
    SqlAlchemyEmotionRepository,
)
from app.infrastructure.database.repositories.thread_store import PostgresThreadStore
from app.infrastructure.database.repositories.turn_commit import PostgresTurnCommit
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.shared.utils.user_identity import normalize_user_id

SENTIMENT = {
    "reaction": "cheerful_joy",
    "user_stance": "loving",
    "intensity": 0.9,
    "variance": 0.5,
}


def _turn(thread_id) -> TurnRecord:
    return TurnRecord(
        thread_id=thread_id,
        turn_id=uuid4(),
        question="Question?",
        answer="Answer.",
        mode_requested=ChatMode.ADVANCED,
        mode_effective=ChatMode.ADVANCED,
        lane="companion",
        status="companion",
    )


async def _emotion(owner: str):
    user_id = normalize_user_id(owner)
    async with AsyncSessionFactory() as session:
        await SqlAlchemyUserRepository(session).get_or_create_user(user_id)
        state = await SqlAlchemyEmotionRepository(session).get_emotion_state(user_id)
        await session.commit()
        return state


async def test_turn_and_emotion_commit_together_and_a_retry_moves_nothing() -> None:
    owner = f"it-commit-{uuid4()}"
    threads = PostgresThreadStore(AsyncSessionFactory)
    commit = PostgresTurnCommit(AsyncSessionFactory)
    thread = await threads.create(owner, "web", ChatMode.ADVANCED)
    record = _turn(thread.id)
    before = await _emotion(owner)

    first = await commit.commit(record, owner, SENTIMENT)
    after_first = await _emotion(owner)
    second = await commit.commit(record, owner, SENTIMENT)
    after_second = await _emotion(owner)

    assert (first, second) == (True, False)
    assert await threads.find_turn(thread.id, record.turn_id) is not None
    assert after_first.values() != before.values()
    assert after_second.values() == after_first.values()


async def test_a_turn_without_sentiment_leaves_emotion_alone() -> None:
    owner = f"it-commit-{uuid4()}"
    threads = PostgresThreadStore(AsyncSessionFactory)
    thread = await threads.create(owner, "web", ChatMode.ADVANCED)
    before = await _emotion(owner)

    assert await PostgresTurnCommit(AsyncSessionFactory).commit(_turn(thread.id), owner, {})

    assert (await _emotion(owner)).values() == before.values()
