"""Versioned core memory writes for the consolidation job; a person's own edit wins (MEM-006)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.domain.interfaces.core_memory_consolidation import ConsolidationState
from app.infrastructure.database.models.thread import (
    CoreMemoryConsolidationModel,
    CoreMemoryModel,
)


class PostgresCoreMemoryConsolidationStore:
    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._sessions = session_factory

    async def load(self, owner: str) -> ConsolidationState:
        async with self._sessions() as session:
            core = (
                await session.execute(
                    select(CoreMemoryModel.content, CoreMemoryModel.version).where(
                        CoreMemoryModel.owner_principal == owner
                    )
                )
            ).one_or_none()
            progress = await session.get(CoreMemoryConsolidationModel, owner)
        return ConsolidationState(
            content=dict(core.content) if core else {},
            version=core.version if core else None,
            consolidated_through=progress.consolidated_through if progress else 0,
            job_owned=dict(progress.job_owned) if progress else {},
        )

    async def commit(
        self,
        owner: str,
        *,
        expected_version: int | None,
        content: Mapping[str, Any] | None,
        job_owned: Mapping[str, list[str]],
        consolidated_through: int,
    ) -> bool:
        async with self._sessions() as session:
            # The row lock makes a hand edit wait for this transaction, or fail the version check.
            current = await session.scalar(
                select(CoreMemoryModel.version)
                .where(CoreMemoryModel.owner_principal == owner)
                .with_for_update()
            )
            if current != expected_version:
                return False
            if content is not None and not await self._write_core(
                session, owner, expected_version, content
            ):
                return False
            await self._write_progress(session, owner, job_owned, consolidated_through)
            await session.commit()
        return True

    @staticmethod
    async def _write_core(
        session: Any, owner: str, expected_version: int | None, content: Mapping[str, Any]
    ) -> bool:
        if expected_version is None:
            created = await session.execute(
                insert(CoreMemoryModel)
                .values(owner_principal=owner, version=1, content=dict(content))
                .on_conflict_do_nothing(index_elements=[CoreMemoryModel.owner_principal])
            )
            return bool(created.rowcount)
        await session.execute(
            update(CoreMemoryModel)
            .where(CoreMemoryModel.owner_principal == owner)
            .values(content=dict(content), version=CoreMemoryModel.version + 1)
        )
        return True

    @staticmethod
    async def _write_progress(
        session: Any, owner: str, job_owned: Mapping[str, list[str]], consolidated_through: int
    ) -> None:
        statement = insert(CoreMemoryConsolidationModel).values(
            owner_principal=owner,
            consolidated_through=consolidated_through,
            job_owned=dict(job_owned),
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[CoreMemoryConsolidationModel.owner_principal],
                set_={
                    "consolidated_through": statement.excluded.consolidated_through,
                    "job_owned": statement.excluded.job_owned,
                },
            )
        )
