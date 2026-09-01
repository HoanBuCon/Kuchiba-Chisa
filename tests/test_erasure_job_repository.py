"""Integration coverage for SEC-04's pseudonymous durable erasure audit."""

from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.erasure_job import ErasureJobModel
from app.infrastructure.database.repositories.erasure_job_repository import ErasureJobRepository


@pytest.mark.asyncio
async def test_erasure_job_records_pseudonymous_completion(
    isolated_postgres: None,
) -> None:
    del isolated_postgres
    subject_hash = hashlib.sha256(f"test-subject:{uuid4()}".encode()).hexdigest()
    job_id = None
    try:
        async with AsyncSessionFactory() as session:
            repository = ErasureJobRepository(session)
            job = await repository.create(subject_hash)
            job_id = job.id
            await repository.finish(
                job.id,
                status="COMPLETED",
                store_results={"postgres": "acknowledged"},
            )

            stored = (
                await session.execute(
                    select(ErasureJobModel).where(ErasureJobModel.id == job.id)
                )
            ).scalar_one()
            assert stored.subject_hash == subject_hash
            assert stored.status == "COMPLETED"
            assert stored.store_results == {"postgres": "acknowledged"}
            assert stored.completed_at is not None
    finally:
        if job_id is not None:
            async with AsyncSessionFactory() as session:
                await session.execute(delete(ErasureJobModel).where(ErasureJobModel.id == job_id))
                await session.commit()
