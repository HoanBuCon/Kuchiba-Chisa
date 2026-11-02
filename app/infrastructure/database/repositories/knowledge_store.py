"""PostgreSQL knowledge store: each corpus version is written in one transaction (KNW-004)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.ingestion.knowledge import (
    Alias,
    Entity,
    GlossaryTerm,
    KnowledgeBase,
    LocationEdge,
    Quest,
    knowledge_counts,
)
from app.infrastructure.database.models.knowledge import (
    KbAliasModel,
    KbEntityModel,
    KbGlossaryModel,
    KbLocationEdgeModel,
    KbQuestModel,
)

INSERT_BATCH = 500
TABLES = (KbEntityModel, KbAliasModel, KbGlossaryModel, KbQuestModel, KbLocationEdgeModel)


def _entity_row(version: str, entity: Entity) -> dict[str, Any]:
    return {
        "corpus_version": version,
        "page_id": entity.page_id,
        "title": entity.title,
        "entity_type": entity.entity_type,
        "fields": entity.fields,
        "nation": entity.nation,
        "nation_source": entity.nation_source,
        "game_version": entity.game_version,
        "version_source": entity.version_source,
    }


def _quest_row(version: str, quest: Quest) -> dict[str, Any]:
    return {
        "corpus_version": version,
        "page_id": quest.page_id,
        "title": quest.title,
        "fields": quest.fields,
        "description": quest.description,
        "summary": quest.summary,
        "steps": list(quest.steps),
        "narration": list(quest.narration),
        "speakers": list(quest.speakers),
        "locations": list(quest.locations),
    }


def _positioned(version: str, position: int, values: dict[str, Any]) -> dict[str, Any]:
    return {"corpus_version": version, "position": position, **values}


def _rows(version: str, knowledge: KnowledgeBase) -> Iterable[tuple[type, list[dict[str, Any]]]]:
    yield KbEntityModel, [_entity_row(version, entity) for entity in knowledge.entities]
    yield KbQuestModel, [_quest_row(version, quest) for quest in knowledge.quests]
    yield (
        KbAliasModel,
        [
            _positioned(
                version,
                position,
                {
                    "alias": alias.alias,
                    "target": alias.target,
                    "kind": alias.kind,
                    "confidence": alias.confidence,
                    "evidence": list(alias.evidence),
                },
            )
            for position, alias in enumerate(knowledge.aliases)
        ],
    )
    yield (
        KbGlossaryModel,
        [
            _positioned(
                version,
                position,
                {
                    "term": term.term,
                    "definition": term.definition,
                    "pages": term.pages,
                    "variants": list(term.variants),
                },
            )
            for position, term in enumerate(knowledge.glossary)
        ],
    )
    yield (
        KbLocationEdgeModel,
        [
            _positioned(
                version,
                position,
                {"child": edge.child, "parent": edge.parent, "source": edge.source},
            )
            for position, edge in enumerate(knowledge.locations)
        ],
    )


def _batches(rows: Sequence[dict[str, Any]]) -> Iterable[Sequence[dict[str, Any]]]:
    for start in range(0, len(rows), INSERT_BATCH):
        yield rows[start : start + INSERT_BATCH]


class PostgresKnowledgeStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def publish(self, version: str, knowledge: KnowledgeBase) -> dict[str, int]:
        """A failed write leaves the previous rows of this version untouched."""
        async with self._session_factory() as session, session.begin():
            for table in TABLES:
                await session.execute(delete(table).where(table.corpus_version == version))
            for target, rows in _rows(version, knowledge):
                for batch in _batches(rows):
                    await session.execute(insert(target), batch)
        return knowledge_counts(knowledge)

    async def count(self, version: str) -> dict[str, int]:
        async with self._session_factory() as session:
            counts: dict[str, int] = {}
            for name, table in (
                ("entities", KbEntityModel),
                ("aliases", KbAliasModel),
                ("glossary", KbGlossaryModel),
                ("quests", KbQuestModel),
                ("location_edges", KbLocationEdgeModel),
            ):
                statement = select(func.count()).select_from(table)
                stored = await session.scalar(statement.where(table.corpus_version == version))
                counts[name] = stored or 0
        return counts

    async def load(self, version: str) -> KnowledgeBase:
        async with self._session_factory() as session:

            async def rows(table: Any, order: Any) -> Sequence[Any]:
                statement = select(table).where(table.corpus_version == version).order_by(order)
                return (await session.scalars(statement)).all()

            entities = await rows(KbEntityModel, KbEntityModel.page_id)
            quests = await rows(KbQuestModel, KbQuestModel.page_id)
            aliases = await rows(KbAliasModel, KbAliasModel.position)
            glossary = await rows(KbGlossaryModel, KbGlossaryModel.position)
            edges = await rows(KbLocationEdgeModel, KbLocationEdgeModel.position)
        return KnowledgeBase(
            entities=tuple(
                Entity(
                    r.page_id,
                    r.title,
                    r.entity_type,
                    dict(r.fields),
                    r.nation,
                    r.nation_source,
                    r.game_version,
                    r.version_source,
                )
                for r in entities
            ),
            aliases=tuple(
                Alias(r.alias, r.target, r.kind, r.confidence, tuple(r.evidence)) for r in aliases
            ),
            glossary=tuple(
                GlossaryTerm(r.term, r.definition, r.pages, tuple(r.variants)) for r in glossary
            ),
            quests=tuple(
                Quest(
                    r.page_id,
                    r.title,
                    dict(r.fields),
                    r.description,
                    r.summary,
                    tuple(r.steps),
                    tuple(r.narration),
                    tuple(r.speakers),
                    tuple(r.locations),
                )
                for r in quests
            ),
            locations=tuple(LocationEdge(r.child, r.parent, r.source) for r in edges),
        )
