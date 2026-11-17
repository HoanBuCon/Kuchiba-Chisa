"""Periodic sweep that turns expired role assignments into revocations (ROLE-006)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.application.security.authz_service import AuthzService

log = logging.getLogger(__name__)

# Expired roles already grant nothing at query time; the sweep only keeps the records honest.
ROLE_EXPIRY_INTERVAL_SECONDS = 60.0


class RoleExpirySweeper:
    def __init__(
        self,
        service: AuthzService,
        session_factory: Callable[[], Any],
        interval_seconds: float = ROLE_EXPIRY_INTERVAL_SECONDS,
    ) -> None:
        self._service = service
        self._sessions = session_factory
        self._interval = interval_seconds

    async def sweep_once(self) -> int:
        async with self._sessions() as session:
            expired = await self._service.expire_assignments(session)
            await session.commit()
        return expired

    async def run(self, stop: asyncio.Event) -> None:
        """Sweep until `stop` is set; a failed sweep is retried on the next tick."""
        while not stop.is_set():
            try:
                await self.sweep_once()
            except Exception:
                log.exception("Role expiry sweep failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue
