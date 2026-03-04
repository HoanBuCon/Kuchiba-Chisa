"""
Celery task stubs for memory operations.
Full implementations will be added in Phase 4: Core Domain Implementation.
"""
from __future__ import annotations

from app.infrastructure.queue.celery_app import celery_app
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


@celery_app.task(
    name="app.infrastructure.queue.tasks.memory_tasks.summarize_conversation",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    queue="medium",
)
def summarize_conversation(self, conversation_id: str, user_id: str) -> dict:  # type: ignore
    """
    STUB: Summarize a conversation and store as long-term memory.
    Triggered when: session ends OR token count > 80% of context window.
    Full implementation in Phase 4.
    """
    log.info("summarize_conversation task received (stub)", conversation_id=conversation_id, user_id=user_id)
    return {"status": "stub", "conversation_id": conversation_id}


@celery_app.task(
    name="app.infrastructure.queue.tasks.memory_tasks.prune_old_memories",
    queue="low",
)
def prune_old_memories() -> dict:  # type: ignore
    """
    STUB: Weekly job to prune low-importance memories older than 90 days.
    Full implementation in Phase 4.
    """
    log.info("prune_old_memories task received (stub)")
    return {"status": "stub"}


@celery_app.task(
    name="app.infrastructure.queue.tasks.memory_tasks.score_memory",
    bind=True,
    queue="medium",
)
def score_memory(self, memory_id: str, user_id: str) -> dict:  # type: ignore
    """STUB: Score a memory for importance after conversation turn."""
    log.info("score_memory task received (stub)", memory_id=memory_id)
    return {"status": "stub", "memory_id": memory_id}
