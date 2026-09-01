"""Persistence adapter for retryable, pseudonymous erasure jobs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.erasure_job import ErasureJobModel


class ErasureJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, subject_hash: str) -> ErasureJobModel:
        job = ErasureJobModel(subject_hash=subject_hash, status="IN_PROGRESS", store_results={})
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def finish(
        self,
        job_id: uuid.UUID,
        *,
        status: str,
        store_results: dict[str, str],
        error_code: str | None = None,
    ) -> None:
        job = (
            await self.session.execute(select(ErasureJobModel).where(ErasureJobModel.id == job_id))
        ).scalar_one()
        job.status = status
        job.store_results = store_results
        job.error_code = error_code
        job.completed_at = datetime.now(UTC) if status == "COMPLETED" else None
        await self.session.commit()
