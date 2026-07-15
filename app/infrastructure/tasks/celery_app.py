from celery import Celery
from app.config.settings import settings

celery_app = Celery(
    "chisa_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.infrastructure.tasks.ingestion_tasks", "app.infrastructure.tasks.cleanup_tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600, # 1 hour max per task
)
