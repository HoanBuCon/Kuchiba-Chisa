"""
Celery task stubs for embedding operations.
Full implementation in Phase 4.
"""
from __future__ import annotations

from app.infrastructure.queue.celery_app import celery_app
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


@celery_app.task(
    name="app.infrastructure.queue.tasks.embedding_tasks.embed_and_index_memory",
    bind=True,
    max_retries=5,
    queue="high",
)
def embed_and_index_memory(self, memory_id: str, text: str, user_id: str) -> dict:  # type: ignore
    """
    STUB: Generate embedding and index memory in Qdrant.
    Triggered after a memory turn is flagged as important.
    Full implementation in Phase 4.
    """
    log.info("embed_and_index_memory task received (stub)", memory_id=memory_id)
    return {"status": "stub", "memory_id": memory_id}
