"""
Celery worker entrypoint.
Run with: celery -A app.infrastructure.queue.worker worker --loglevel=info -Q high,medium,low
"""
from __future__ import annotations

from app.infrastructure.queue.celery_app import celery_app  # noqa: F401 — triggers task auto-discovery
from app.infrastructure.logging.logger import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)

log.info("[Chisa] Chisa Celery Worker starting...")


def start() -> None:
    """Programmatic entrypoint for the worker (used in Docker CMD)."""
    celery_app.worker_main(
        argv=[
            "worker",
            "--loglevel=info",
            "--queues=high,medium,low",
            f"--concurrency={__import__('app.config.settings', fromlist=['settings']).settings.WORKER_CONCURRENCY}",
            "--without-gossip",
            "--without-mingle",
        ]
    )


if __name__ == "__main__":
    start()
