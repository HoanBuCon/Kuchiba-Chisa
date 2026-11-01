"""Wiki inventory against isolated PostgreSQL: round trip, upsert, run log and the advisory lock."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.domain.ingestion.pages import PageState, PageStatus
from app.domain.interfaces.wiki_ingestion import SyncRun
from app.infrastructure.database.engine import AsyncSessionFactory, engine
from app.infrastructure.database.models.wiki_inventory import WikiPageModel, WikiSyncRunModel
from app.infrastructure.database.repositories.wiki_inventory import PostgresWikiInventory

NOW = datetime(2026, 11, 2, tzinfo=UTC)
PAGE_IDS = (910_001, 910_002)


@pytest.fixture
async def inventory():
    yield PostgresWikiInventory(engine, AsyncSessionFactory)
    async with AsyncSessionFactory() as session:
        await session.execute(delete(WikiPageModel).where(WikiPageModel.page_id.in_(PAGE_IDS)))
        await session.execute(delete(WikiSyncRunModel).where(WikiSyncRunModel.run_id.like("it-%")))
        await session.commit()


def _state(page_id: int, **changes) -> PageState:
    base = PageState(
        page_id=page_id,
        title=f"IT Page {page_id}",
        last_revid=5,
        touched=NOW,
        family="lore",
        tier="A",
        templates=("Template:Quote",),
        aliases=("Old Title",),
    )
    return replace(base, **changes)


@pytest.mark.asyncio
async def test_states_round_trip_and_upsert_overwrites(inventory) -> None:
    first = _state(PAGE_IDS[0])
    await inventory.upsert([first, _state(PAGE_IDS[1])])
    fetched = _state(
        PAGE_IDS[0], fetched_revid=5, fetched_touched=NOW, fetched_at=NOW, bronze_key="bronze/x"
    )
    await inventory.upsert([fetched, _state(PAGE_IDS[1], status=PageStatus.PENDING_DELETE)])

    loaded = await inventory.load()

    assert loaded[PAGE_IDS[0]] == fetched
    assert loaded[PAGE_IDS[1]].status is PageStatus.PENDING_DELETE


@pytest.mark.asyncio
async def test_last_successful_run_ignores_failed_and_running(inventory) -> None:
    ok = SyncRun(
        f"it-{uuid.uuid4().hex[:8]}", NOW - timedelta(hours=2), NOW, "succeeded", {"fetched": 3}
    )
    await inventory.record_run(ok)
    await inventory.record_run(SyncRun(f"it-{uuid.uuid4().hex[:8]}", NOW, None, "failed", {}))
    running = SyncRun(f"it-{uuid.uuid4().hex[:8]}", NOW - timedelta(hours=1), None, "running", {})
    await inventory.record_run(running)
    await inventory.record_run(
        SyncRun(running.run_id, running.started_at, NOW, "succeeded", {"fetched": 1})
    )

    latest = await inventory.last_successful_run()

    assert latest is not None and latest.run_id == running.run_id and latest.stats == {"fetched": 1}


@pytest.mark.asyncio
async def test_advisory_lock_is_exclusive_and_released(inventory) -> None:
    async with inventory.exclusive_run() as first, inventory.exclusive_run() as second:
        assert first is True and second is False
    async with inventory.exclusive_run() as again:
        assert again is True
