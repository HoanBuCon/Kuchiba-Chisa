"""
Background Task Manager — tracks asyncio tasks and handles errors gracefully.

Replaces raw asyncio.create_task() calls scattered across the codebase to prevent:
- Tasks being garbage collected before completion
- Unhandled exceptions being silently swallowed
- No graceful shutdown for running tasks
"""
from __future__ import annotations

import asyncio
from typing import Coroutine, Optional

from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class BackgroundTaskManager:
    """
    Manages fire-and-forget asyncio tasks with lifecycle tracking.
    All tasks are held in a set to prevent garbage collection and
    exceptions are automatically logged instead of being silently swallowed.
    """

    _tasks: set[asyncio.Task] = set()

    @classmethod
    def spawn(
        cls,
        coro: Coroutine,
        *,
        name: Optional[str] = None,
    ) -> asyncio.Task:
        """
        Schedule a coroutine as a tracked background task.

        Args:
            coro: The coroutine to run.
            name: Optional human-readable name for logging.

        Returns:
            The created asyncio.Task.
        """
        task = asyncio.create_task(coro, name=name)
        cls._tasks.add(task)
        task.add_done_callback(cls._on_task_done)
        log.debug("Background task spawned", task_name=name or "unnamed", total_active=len(cls._tasks))
        return task

    @classmethod
    def _on_task_done(cls, task: asyncio.Task) -> None:
        """Callback fired when a tracked task completes or fails."""
        cls._tasks.discard(task)
        task_name = task.get_name() or "unnamed"

        if task.cancelled():
            log.debug("Background task cancelled", task_name=task_name)
            return

        exc = task.exception()
        if exc is not None:
            log.error(
                "Background task failed",
                task_name=task_name,
                error=str(exc),
                error_type=type(exc).__name__,
            )

    @classmethod
    async def shutdown(cls, timeout: float = 10.0) -> None:
        """
        Cancel all running background tasks and wait for them to finish.
        Called during application shutdown.
        """
        if not cls._tasks:
            log.info("No background tasks to shut down")
            return

        count = len(cls._tasks)
        log.info("Shutting down background tasks", count=count, timeout=timeout)

        # Cancel all tasks
        for task in cls._tasks:
            task.cancel()

        # Wait for all tasks to finish (cancelled or not)
        results = await asyncio.gather(*cls._tasks, return_exceptions=True)

        # Log any non-cancellation errors
        errors = [r for r in results if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError)]
        if errors:
            log.warning("Some background tasks failed during shutdown", error_count=len(errors))

        cls._tasks.clear()
        log.info("Background task shutdown complete", original_count=count)

    @classmethod
    def active_count(cls) -> int:
        """Returns the number of currently running background tasks."""
        return len(cls._tasks)
