import asyncio

from app.infrastructure.logging.pipeline_tracker import PipelineTracker


def test_flush_does_not_await_a_task_owned_by_another_event_loop() -> None:
    """A process singleton must not gather a task created by a closed request loop."""
    tracker = PipelineTracker()
    foreign_loop = asyncio.new_event_loop()
    foreign_task = foreign_loop.create_task(asyncio.sleep(60))
    tracker._pending_tasks.add(foreign_task)

    try:
        asyncio.run(tracker.flush())
        assert foreign_task in tracker._pending_tasks
    finally:
        foreign_task.cancel()
        foreign_loop.run_until_complete(asyncio.gather(foreign_task, return_exceptions=True))
        foreign_loop.close()


def test_redis_publish_requires_a_ready_subscriber() -> None:
    """Short-lived request loops cannot leak observability tasks before Redis is ready."""
    tracker = PipelineTracker()

    async def notify() -> None:
        tracker._notify_listeners({"type": "step"})
        await tracker.flush()

    asyncio.run(notify())

    assert not tracker._pending_tasks


def test_redis_publish_runs_after_subscriber_is_ready(monkeypatch) -> None:
    """Readiness gating must not suppress cross-worker telemetry after startup."""
    tracker = PipelineTracker()
    published_events: list[dict[str, object]] = []

    async def publish(event: dict[str, object]) -> None:
        published_events.append(event)

    monkeypatch.setattr(tracker, "_publish_redis_event", publish)
    tracker._redis_broadcast_ready = True

    async def notify() -> None:
        tracker._notify_listeners({"type": "step"})
        await tracker.flush()

    asyncio.run(notify())

    assert published_events == [{"type": "step", "_publisher_id": tracker.instance_id}]
