"""Knowledge store against isolated PostgreSQL: round trip, version isolation, atomic replace."""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.domain.ingestion.knowledge import (
    Alias,
    AliasKind,
    Entity,
    GlossaryTerm,
    KnowledgeBase,
    LocationEdge,
    Quest,
)
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.repositories.knowledge_store import (
    TABLES,
    PostgresKnowledgeStore,
)

VERSION = "it-2026.11.02-1"
OTHER = "it-2026.11.02-2"
KB = KnowledgeBase(
    entities=(
        Entity(1, "Chisa", "resonator", {"age": "18"}, "Lahai-Roi", "infobox", "3.0", "category"),
    ),
    aliases=(
        Alias("Honami", "Chronorift Metropolis", AliasKind.INFERRED, "inferred", ("Honami Park",)),
    ),
    glossary=(GlossaryTerm("Tacet", "A definition.", 2, ("Another.",)),),
    quests=(
        Quest(
            5,
            "A Quest",
            {"chapter": "I"},
            "Desc",
            None,
            ("Go",),
            ("Head out",),
            ("Rover",),
            ("Jinzhou",),
        ),
    ),
    locations=(LocationEdge("Honami Park", "Chronorift Metropolis", "category:x"),),
)


@pytest.fixture
async def store():
    yield PostgresKnowledgeStore(AsyncSessionFactory)
    async with AsyncSessionFactory() as session:
        for table in TABLES:
            await session.execute(delete(table).where(table.corpus_version.in_([VERSION, OTHER])))
        await session.commit()


@pytest.mark.asyncio
async def test_published_knowledge_reads_back_identically(store) -> None:
    await store.publish(VERSION, KB)

    assert await store.load(VERSION) == KB
    assert await store.count(VERSION) == {
        "entities": 1,
        "aliases": 1,
        "glossary": 1,
        "quests": 1,
        "location_edges": 1,
    }


@pytest.mark.asyncio
async def test_versions_are_isolated_and_republish_replaces(store) -> None:
    await store.publish(VERSION, KB)
    await store.publish(OTHER, KnowledgeBase((), (), (), (), ()))
    await store.publish(VERSION, KnowledgeBase(KB.entities, (), (), (), ()))

    assert (await store.load(OTHER)).entities == ()
    reloaded = await store.load(VERSION)
    assert reloaded.entities == KB.entities and reloaded.aliases == ()


@pytest.mark.asyncio
async def test_failed_publish_keeps_the_previous_rows(store) -> None:
    await store.publish(VERSION, KB)
    duplicate = Entity(1, "Duplicate key", "resonator", {}, None, None, None, None)
    broken = KnowledgeBase((*KB.entities, duplicate), (), (), (), ())

    with pytest.raises(Exception, match="(?i)duplicate|unique"):
        await store.publish(VERSION, broken)

    assert await store.load(VERSION) == KB
