from __future__ import annotations

from celery import Celery

from app.config.settings import settings

# ─── Celery Application ───────────────────────────────────────────────────────

celery_app = Celery(
    "chisa",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        # Task modules auto-discovered — add new task modules here
        "app.infrastructure.queue.tasks.memory_tasks",
        "app.infrastructure.queue.tasks.embedding_tasks",
        "app.infrastructure.queue.tasks.affection_tasks",
    ],
)

# ─── Celery Configuration ─────────────────────────────────────────────────────

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task behavior
    task_acks_late=True,            # Ack after task completes (not on receive)
    task_reject_on_worker_lost=True, # Re-queue if worker crashes mid-task
    worker_prefetch_multiplier=1,   # Process one task at a time (fair dispatch)
    task_max_retries=5,
    task_default_retry_delay=60,    # seconds
    # Result TTL
    result_expires=3600,            # 1 hour
    # Routing
    task_queues={
        "high": {"exchange": "high", "routing_key": "high"},
        "medium": {"exchange": "medium", "routing_key": "medium"},
        "low": {"exchange": "low", "routing_key": "low"},
    },
    task_default_queue="medium",
    task_routes={
        "app.infrastructure.queue.tasks.embedding_tasks.*": {"queue": "high"},
        "app.infrastructure.queue.tasks.memory_tasks.summarize*": {"queue": "medium"},
        "app.infrastructure.queue.tasks.memory_tasks.prune*": {"queue": "low"},
        "app.infrastructure.queue.tasks.affection_tasks.*": {"queue": "high"},
    },
    # Beat schedule for periodic tasks
    beat_schedule={
        "memory-prune-weekly": {
            "task": "app.infrastructure.queue.tasks.memory_tasks.prune_old_memories",
            "schedule": 604800,  # Every 7 days in seconds
        },
    },
)
