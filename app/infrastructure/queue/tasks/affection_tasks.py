"""
Celery task stubs for affection/relationship operations.
Full implementation in Phase 4.
"""
from __future__ import annotations

from app.infrastructure.queue.celery_app import celery_app
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


@celery_app.task(
    name="app.infrastructure.queue.tasks.affection_tasks.apply_affection_delta",
    bind=True,
    queue="high",
)
def apply_affection_delta(self, user_id: str, delta: int, reason: str) -> dict:  # type: ignore
    """
    STUB: Apply affection point delta and check level-up threshold.
    Full implementation in Phase 4.
    """
    log.info("apply_affection_delta task received (stub)", user_id=user_id, delta=delta)
    return {"status": "stub", "user_id": user_id, "delta": delta}
