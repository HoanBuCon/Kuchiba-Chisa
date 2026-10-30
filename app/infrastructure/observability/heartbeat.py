"""Dead-man heartbeat: an external monitor alerts when these pings stop (MON-033)."""

from __future__ import annotations

import asyncio

import httpx

from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


async def run_heartbeat(
    client: httpx.AsyncClient,
    url: str,
    interval_seconds: float,
    stop: asyncio.Event,
) -> None:
    """Ping ``url`` every interval until ``stop`` is set; failures are logged, never raised."""
    while not stop.is_set():
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as error:
            # The URL embeds a monitor token, so only the failure type is logged.
            log.warning("Heartbeat ping failed", error_type=type(error).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
