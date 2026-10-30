"""Dead-man heartbeat pings until stopped and survives monitor failures (MON-033)."""

import asyncio

import httpx
import pytest

from app.infrastructure.observability.heartbeat import run_heartbeat


@pytest.mark.asyncio
async def test_heartbeat_pings_repeatedly_until_stopped() -> None:
    pings: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pings.append(str(request.url))
        return httpx.Response(200)

    stop = asyncio.Event()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(run_heartbeat(client, "https://hc.example/ping/x", 0.01, stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=1)

    assert len(pings) >= 2
    assert set(pings) == {"https://hc.example/ping/x"}


@pytest.mark.asyncio
async def test_heartbeat_keeps_running_when_the_monitor_fails() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("monitor down")
        return httpx.Response(503)

    stop = asyncio.Event()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(run_heartbeat(client, "https://hc.example/ping/x", 0.01, stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=1)

    assert calls >= 2
