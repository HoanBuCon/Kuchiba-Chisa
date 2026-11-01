"""Silver ledger against isolated PostgreSQL: round trip and overwrite of the latest check."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from app.domain.ingestion.page_checks import Verdict
from app.domain.interfaces.silver import SilverEntry
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.wiki_silver import WikiPageSilverModel
from app.infrastructure.database.repositories.wiki_silver import PostgresSilverLedger

PAGE_ID = 920_001
ENTRY = SilverEntry(
    page_id=PAGE_ID,
    silver_path="silver/920001/a.json.gz",
    output_hash="h" * 64,
    verdict=Verdict.ACCEPT,
    reasons=(),
    unchanged_runs=0,
    checked_at=datetime(2026, 11, 2, tzinfo=UTC),
    lkg_path="silver/920001/a.json.gz",
)


@pytest.fixture
async def ledger():
    yield PostgresSilverLedger(AsyncSessionFactory)
    async with AsyncSessionFactory() as session:
        await session.execute(
            delete(WikiPageSilverModel).where(WikiPageSilverModel.page_id == PAGE_ID)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_entries_round_trip_and_latest_check_wins(ledger) -> None:
    await ledger.upsert([ENTRY])
    held = replace(
        ENTRY,
        silver_path="silver/920001/b.json.gz",
        verdict=Verdict.HOLD,
        reasons=("shrink",),
        unchanged_runs=1,
    )
    await ledger.upsert([held])

    loaded = await ledger.load()

    assert loaded[PAGE_ID] == held
    assert loaded[PAGE_ID].lkg_path == ENTRY.lkg_path
