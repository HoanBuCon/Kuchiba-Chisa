"""Lifecycle supervision for best-effort node-local maintenance work."""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class MaintenanceTaskSnapshot:
    """Content-free counters suitable for operational telemetry."""

    submitted: int
    coalesced: int
    succeeded: int
    retries: int
    failed: int
    cancelled: int
    active: int


@dataclass
class _MutableTaskCounters:
    submitted: int = 0
    coalesced: int = 0
    succeeded: int = 0
    retries: int = 0
    failed: int = 0
    cancelled: int = 0


class MaintenanceTaskSupervisor:
    """Run keyed maintenance jobs with bounded retry and graceful draining.

    This supervisor is intentionally reserved for node-local, reconstructable
    maintenance such as local-storage quota scans. Durable business work remains
    owned by the PostgreSQL outbox worker.
    """

    _tasks: weakref.WeakKeyDictionary[
        asyncio.AbstractEventLoop, dict[str, asyncio.Task[None]]
    ] = weakref.WeakKeyDictionary()
    _counters: weakref.WeakKeyDictionary[
        asyncio.AbstractEventLoop, _MutableTaskCounters
    ] = weakref.WeakKeyDictionary()
    _closing: weakref.WeakSet[asyncio.AbstractEventLoop] = weakref.WeakSet()

    @classmethod
    def schedule(
        cls,
        *,
        key: str,
        operation: Callable[[], Awaitable[None]],
        max_attempts: int = 3,
        retry_base_seconds: float = 0.1,
    ) -> asyncio.Task[None]:
        """Schedule one operation, coalescing concurrent work with the same key."""
        if not key or len(key) > 255:
            raise ValueError("maintenance task key must contain 1..255 characters")
        if not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if not 0 <= retry_base_seconds <= 60:
            raise ValueError("retry_base_seconds must be between 0 and 60")

        loop = asyncio.get_running_loop()
        if loop in cls._closing:
            raise RuntimeError("maintenance task supervisor is shutting down")
        tasks = cls._tasks.setdefault(loop, {})
        counters = cls._counters.setdefault(loop, _MutableTaskCounters())
        existing = tasks.get(key)
        if existing is not None and not existing.done():
            counters.coalesced += 1
            return existing

        task = loop.create_task(
            cls._run(
                key=key,
                operation=operation,
                max_attempts=max_attempts,
                retry_base_seconds=retry_base_seconds,
                counters=counters,
            ),
            name=f"maintenance:{key}",
        )
        tasks[key] = task
        counters.submitted += 1
        task.add_done_callback(lambda completed: cls._discard(loop, key, completed))
        return task

    @classmethod
    async def _run(
        cls,
        *,
        key: str,
        operation: Callable[[], Awaitable[None]],
        max_attempts: int,
        retry_base_seconds: float,
        counters: _MutableTaskCounters,
    ) -> None:
        for attempt in range(1, max_attempts + 1):
            try:
                await operation()
            except asyncio.CancelledError:
                counters.cancelled += 1
                raise
            except Exception as exc:
                if attempt >= max_attempts:
                    counters.failed += 1
                    log.error(
                        "Maintenance task exhausted retries",
                        task_key=key,
                        attempts=attempt,
                        error_type=type(exc).__name__,
                    )
                    raise
                counters.retries += 1
                log.warning(
                    "Maintenance task retry scheduled",
                    task_key=key,
                    attempt=attempt,
                    error_type=type(exc).__name__,
                )
                await asyncio.sleep(retry_base_seconds * (2 ** (attempt - 1)))
            else:
                counters.succeeded += 1
                return

    @classmethod
    def _discard(
        cls,
        loop: asyncio.AbstractEventLoop,
        key: str,
        completed: asyncio.Task[None],
    ) -> None:
        tasks = cls._tasks.get(loop)
        if tasks is not None and tasks.get(key) is completed:
            tasks.pop(key, None)
        if completed.cancelled():
            return
        # Retrieve the exception so an exhausted maintenance failure never becomes
        # an unhandled asyncio task exception. The retry loop already logged it.
        completed.exception()

    @classmethod
    async def shutdown(cls, *, grace_seconds: float = 10.0) -> None:
        """Stop admission, drain current-loop tasks, then cancel after the deadline."""
        if grace_seconds < 0:
            raise ValueError("shutdown grace period must be non-negative")
        loop = asyncio.get_running_loop()
        cls._closing.add(loop)
        tasks = set(cls._tasks.get(loop, {}).values())
        try:
            if not tasks:
                return
            _, pending = await asyncio.wait(tasks, timeout=grace_seconds)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            cls._tasks.pop(loop, None)
            cls._closing.discard(loop)

    @classmethod
    def snapshot(cls) -> MaintenanceTaskSnapshot:
        """Return content-free counters for the current event loop."""
        loop = asyncio.get_running_loop()
        counters = cls._counters.setdefault(loop, _MutableTaskCounters())
        active = sum(not task.done() for task in cls._tasks.get(loop, {}).values())
        return MaintenanceTaskSnapshot(
            submitted=counters.submitted,
            coalesced=counters.coalesced,
            succeeded=counters.succeeded,
            retries=counters.retries,
            failed=counters.failed,
            cancelled=counters.cancelled,
            active=active,
        )
