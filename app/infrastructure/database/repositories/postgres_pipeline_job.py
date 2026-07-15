import uuid
import json
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.infrastructure.database.models.ingestion import PipelineJobModel, PipelineEventModel
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class PostgresPipelineJobRepository(IPipelineJobRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_job(self, stage: str, worker: str) -> uuid.UUID:
        job = PipelineJobModel(stage=stage, worker=worker, status="STARTED")
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job.id

    async def update_job_status(self, job_id: uuid.UUID, status: str, error: Optional[str] = None) -> None:
        stmt = select(PipelineJobModel).where(PipelineJobModel.id == job_id)
        result = await self.session.execute(stmt)
        job = result.scalar_one_or_none()
        
        if job:
            job.status = status
            if error:
                job.error_message = error
            await self.session.commit()

    async def log_event(self, job_id: uuid.UUID, event_type: str, details: dict) -> None:
        event = PipelineEventModel(job_id=job_id, event_type=event_type, details=json.dumps(details))
        self.session.add(event)
        await self.session.commit()
