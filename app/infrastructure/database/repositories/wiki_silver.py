"""PostgreSQL silver ledger: latest check and last-known-good pointer per page (ING-006)."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.ingestion.page_checks import Verdict
from app.domain.interfaces.silver import SilverEntry
from app.infrastructure.database.models.wiki_silver import WikiPageSilverModel

UPSERT_BATCH = 500
_COLUMNS = (
    "silver_path",
    "output_hash",
    "verdict",
    "reasons",
    "unchanged_runs",
    "checked_at",
    "lkg_path",
)


def _to_entry(row: WikiPageSilverModel) -> SilverEntry:
    return SilverEntry(
        page_id=row.page_id,
        silver_path=row.silver_path,
        output_hash=row.output_hash,
        verdict=Verdict(row.verdict),
        reasons=tuple(row.reasons),
        unchanged_runs=row.unchanged_runs,
        checked_at=row.checked_at,
        lkg_path=row.lkg_path,
    )


def _to_row(entry: SilverEntry) -> dict[str, object]:
    return {
        "page_id": entry.page_id,
        "silver_path": entry.silver_path,
        "output_hash": entry.output_hash,
        "verdict": entry.verdict.value,
        "reasons": list(entry.reasons),
        "unchanged_runs": entry.unchanged_runs,
        "checked_at": entry.checked_at,
        "lkg_path": entry.lkg_path,
    }


class PostgresSilverLedger:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load(self) -> dict[int, SilverEntry]:
        async with self._session_factory() as session:
            rows = (await session.scalars(select(WikiPageSilverModel))).all()
        return {row.page_id: _to_entry(row) for row in rows}

    async def upsert(self, entries: Iterable[SilverEntry]) -> None:
        rows = [_to_row(entry) for entry in entries]
        async with self._session_factory() as session:
            for start in range(0, len(rows), UPSERT_BATCH):
                statement = insert(WikiPageSilverModel).values(rows[start : start + UPSERT_BATCH])
                updates = {name: statement.excluded[name] for name in _COLUMNS}
                await session.execute(
                    statement.on_conflict_do_update(index_elements=["page_id"], set_=updates)
                )
            await session.commit()
