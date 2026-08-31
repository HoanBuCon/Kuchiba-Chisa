"""Regression tests for the public visualizer containment boundary."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_legacy_visualizer_routes_are_not_public(client) -> None:
    """Raw pipeline traces must not be reachable through the public ASGI app."""
    for path in (
        "/api/v1/visualizer/traces",
        "/api/v1/visualizer/ws",
        "/visualizer",
        "/static/visualizer/visualizer_dashboard.html",
    ):
        response = await client.get(path)
        assert response.status_code == 404, path
