import asyncio
from datetime import timedelta
from sqlalchemy import delete, select, text
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.database.models.ingestion import PipelineEventModel, PipelineJobModel
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

# Assuming this file will be imported and registered by the Celery app
# @celery_app.task(name="cleanup_pipeline_events")
def cleanup_pipeline_events(days_to_keep: int = 7):
    """
    Celery task to delete pipeline events older than `days_to_keep` days,
    provided their parent job has COMPLETED.
    """
    log.info("Starting pipeline event cleanup task", days_to_keep=days_to_keep)
    asyncio.run(_async_cleanup_pipeline_events(days_to_keep))

async def _async_cleanup_pipeline_events(days_to_keep: int):
    async for session in get_db_session():
        try:
            # We use a raw SQL or a subquery text block since we need to join or subquery safely.
            # Delete from pipeline_events where created_at < NOW() - INTERVAL 'X days' 
            # AND job_id IN (select id from pipeline_jobs where status = 'COMPLETED')
            
            stmt = text(f"""
                DELETE FROM pipeline_events 
                WHERE created_at < NOW() - INTERVAL '{days_to_keep} days'
                AND job_id IN (
                    SELECT id FROM pipeline_jobs WHERE status = 'COMPLETED'
                )
            """)
            
            result = await session.execute(stmt)
            await session.commit()
            
            deleted_count = result.rowcount
            log.info("Pipeline event cleanup complete", deleted_events=deleted_count)
            
        except Exception as e:
            await session.rollback()
            log.error("Failed to clean up pipeline events", error=str(e))
        finally:
            # Only need one session from the generator
            break
