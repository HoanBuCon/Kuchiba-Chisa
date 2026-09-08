"""Standalone BE-01 durable worker process."""

from __future__ import annotations

import argparse
import asyncio
import signal
import socket
import uuid

from app.application.background.worker import DurableBackgroundWorker
from app.application.dependencies import container
from app.config.settings import settings
from app.domain.models.background_job import BackgroundJobType
from app.domain.services.community.topic_summarizer import CommunityTopicSummarizer
from app.domain.services.visual_memory_ingestion import VisualMemoryIngestionWorker
from app.infrastructure.background.job_handlers import (
    BackgroundTurnSourceReader,
    CommunitySummaryJobHandler,
    MemoryExtractionJobHandler,
    PrivateSummaryJobHandler,
    VisualMemoryJobHandler,
)
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.database.engine import (
    AsyncSessionFactory,
    connect_database,
    disconnect_database,
)
from app.infrastructure.logging.logger import configure_logging, get_logger
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service

log = get_logger(__name__)


async def run_worker() -> None:
    """Validate dependencies, run bounded work, and drain safely on termination."""
    configure_logging()
    await connect_database()
    if not await redis_service.health_check():
        raise RuntimeError("Redis health check failed for durable worker")
    if not await qdrant_service.health_check(require_active_collections=True):
        raise RuntimeError("Qdrant health check failed for durable worker")

    source = BackgroundTurnSourceReader(AsyncSessionFactory)
    topic_summarizer = CommunityTopicSummarizer(llm=container.llm, cache=redis_service)
    visual_worker = VisualMemoryIngestionWorker(
        vector_store=qdrant_service,
        embedder=container.embedder,
    )
    worker = DurableBackgroundWorker(
        queue=container.background_job_queue,
        handlers={
            BackgroundJobType.MEMORY_EXTRACTION: MemoryExtractionJobHandler(
                source, container.memory_extractor
            ),
            BackgroundJobType.PRIVATE_SUMMARY: PrivateSummaryJobHandler(
                source, container.chat_engine._unified_auto_summarize
            ),
            BackgroundJobType.COMMUNITY_SUMMARY: CommunitySummaryJobHandler(
                source, topic_summarizer
            ),
            BackgroundJobType.VISUAL_MEMORY: VisualMemoryJobHandler(source, visual_worker),
        },
        worker_id=f"{socket.gethostname()}:{id(asyncio.current_task())}",
        concurrency=settings.WORKER_CONCURRENCY,
        lease_seconds=settings.WORKER_LEASE_SECONDS,
        poll_seconds=settings.WORKER_POLL_SECONDS,
        shutdown_grace_seconds=settings.WORKER_SHUTDOWN_GRACE_SECONDS,
    )
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, worker.request_shutdown)
        except (NotImplementedError, RuntimeError):
            signal.signal(signal_name, lambda *_: worker.request_shutdown())

    try:
        await worker.run()
    finally:
        await redis_service.disconnect()
        await qdrant_service.disconnect()
        await disconnect_database()
        if "http_client" in container.__dict__:
            await container.http_client.aclose()
        log.info("Durable background worker stopped")


async def replay_dead_letter(job_id: uuid.UUID, actor: str) -> None:
    """Explicit operator action; the durable record retains actor and timestamp."""
    configure_logging()
    await connect_database()
    try:
        await container.background_job_queue.replay_dead_letter(
            job_id=job_id,
            actor=actor,
        )
        log.info("Dead-letter job scheduled for replay", job_id=str(job_id), actor=actor)
    finally:
        await disconnect_database()


async def report_queue_status() -> None:
    """Emit content-free queue lag/state for operator monitoring."""
    configure_logging()
    await connect_database()
    try:
        snapshot = await container.background_job_queue.snapshot()
        log.info(
            "Durable background queue status",
            counts={status.value: count for status, count in snapshot.counts.items()},
            oldest_ready_age_seconds=snapshot.oldest_ready_age_seconds,
            captured_at=snapshot.captured_at.isoformat(),
        )
    finally:
        await disconnect_database()


def main() -> None:
    parser = argparse.ArgumentParser(description="Kuchiba Chisa durable worker")
    subcommands = parser.add_subparsers(dest="command")
    replay = subcommands.add_parser("replay", help="replay one dead-letter job")
    replay.add_argument("--job-id", type=uuid.UUID, required=True)
    replay.add_argument("--actor", required=True)
    subcommands.add_parser("status", help="report content-free queue lag and state")
    args = parser.parse_args()
    if args.command == "replay":
        asyncio.run(replay_dead_letter(args.job_id, args.actor))
        return
    if args.command == "status":
        asyncio.run(report_queue_status())
        return
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
