"""Core memory in Postgres, the source of truth for what Chisa remembers (MEM-011)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.database.models.thread import CoreMemoryModel, ThreadModel


class PostgresCoreMemoryStore:
    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._sessions = session_factory

    async def get(self, owner: str) -> dict[str, Any] | None:
        async with self._sessions() as session:
            return await session.scalar(
                select(CoreMemoryModel.content).where(CoreMemoryModel.owner_principal == owner)
            )

    async def put(self, owner: str, content: Mapping[str, Any]) -> None:
        statement = insert(CoreMemoryModel).values(
            owner_principal=owner, version=1, content=dict(content)
        )
        async with self._sessions() as session:
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[CoreMemoryModel.owner_principal],
                    set_={
                        "content": statement.excluded.content,
                        "version": CoreMemoryModel.version + 1,
                    },
                )
            )
            await session.commit()

    async def delete(self, owner: str) -> bool:
        async with self._sessions() as session:
            result = await session.execute(
                delete(CoreMemoryModel).where(CoreMemoryModel.owner_principal == owner)
            )
            await session.commit()
            return bool(result.rowcount)


class SqlAlchemyPersonalDataPurge:
    def __init__(self, session: Any) -> None:
        self._session = session

    async def delete_core_memory(self, owner: str) -> None:
        await self._session.execute(
            delete(CoreMemoryModel).where(CoreMemoryModel.owner_principal == owner)
        )

    async def delete_threads(self, owner: str) -> None:
        """Turns and their citations go with the thread, by the cascade."""
        await self._session.execute(delete(ThreadModel).where(ThreadModel.owner_principal == owner))
