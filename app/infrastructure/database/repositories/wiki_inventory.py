"""PostgreSQL wiki inventory: page states, sync-run log and the single-writer lock (ING-013)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import fields

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domain.ingestion.pages import PageState, PageStatus
from app.domain.interfaces.wiki_ingestion import SyncRun
from app.infrastructure.database.models.wiki_inventory import WikiPageModel, WikiSyncRunModel

# Arbitrary but fixed key shared by every process that may run the wiki sync.
SYNC_LOCK_KEY = 0x57494B49
UPSERT_BATCH = 500
SUCCEEDED = "succeeded"
_PAGE_COLUMNS = tuple(field.name for field in fields(PageState))


def _to_state(row: WikiPageModel) -> PageState:
    return PageState(
        page_id=row.page_id,
        title=row.title,
        last_revid=row.last_revid,
        touched=row.touched,
        family=row.family,
        tier=row.tier,
        templates=tuple(row.templates),
        status=PageStatus(row.status),
        fetched_revid=row.fetched_revid,
        fetched_touched=row.fetched_touched,
        fetched_at=row.fetched_at,
        bronze_key=row.bronze_key,
        aliases=tuple(row.aliases),
    )


def _to_row(state: PageState) -> dict[str, object]:
    row = {name: getattr(state, name) for name in _PAGE_COLUMNS}
    return {
        **row,
        "status": state.status.value,
        "templates": list(state.templates),
        "aliases": list(state.aliases),
    }


class PostgresWikiInventory:
    """Each call opens its own short session, so a long sync never pins a pooled transaction."""

    def __init__(
        self, engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory

    async def load(self) -> dict[int, PageState]:
        async with self._session_factory() as session:
            rows = (await session.scalars(select(WikiPageModel))).all()
        return {row.page_id: _to_state(row) for row in rows}

    async def upsert(self, states: Iterable[PageState]) -> None:
        rows = [_to_row(state) for state in states]
        async with self._session_factory() as session:
            for start in range(0, len(rows), UPSERT_BATCH):
                statement = insert(WikiPageModel).values(rows[start : start + UPSERT_BATCH])
                updates = {
                    name: statement.excluded[name] for name in _PAGE_COLUMNS if name != "page_id"
                }
                await session.execute(
                    statement.on_conflict_do_update(index_elements=["page_id"], set_=updates)
                )
            await session.commit()

    async def last_successful_run(self) -> SyncRun | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(WikiSyncRunModel)
                .where(WikiSyncRunModel.status == SUCCEEDED)
                .order_by(WikiSyncRunModel.started_at.desc())
                .limit(1)
            )
        if row is None:
            return None
        return SyncRun(row.run_id, row.started_at, row.finished_at, row.status, dict(row.stats))

    async def record_run(self, run: SyncRun) -> None:
        values = {
            "run_id": run.run_id,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "status": run.status,
            "stats": run.stats,
        }
        statement = insert(WikiSyncRunModel).values(values)
        async with self._session_factory() as session:
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["run_id"],
                    set_={
                        key: statement.excluded[key] for key in ("finished_at", "status", "stats")
                    },
                )
            )
            await session.commit()

    @asynccontextmanager
    async def exclusive_run(self) -> AsyncIterator[bool]:
        # The lock lives on one connection; a Session would return it to the pool on commit.
        async with self._engine.connect() as connection:
            acquired = bool(
                await connection.scalar(select(func.pg_try_advisory_lock(SYNC_LOCK_KEY)))
            )
            await connection.commit()
            try:
                yield acquired
            finally:
                if acquired:
                    await connection.scalar(select(func.pg_advisory_unlock(SYNC_LOCK_KEY)))
                    await connection.commit()
