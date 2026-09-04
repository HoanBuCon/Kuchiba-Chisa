from __future__ import annotations

import socket
from collections.abc import Sequence

import pytest

import app.shared.security.network_destinations as destinations


class _ResolverLoop:
    def __init__(self, addresses: Sequence[str]) -> None:
        self._addresses = addresses

    async def getaddrinfo(self, *_: object, **__: object) -> list[tuple[object, ...]]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
            for address in self._addresses
        ]


@pytest.mark.asyncio
async def test_public_destination_validator_accepts_public_dns_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        destinations.asyncio,
        "get_running_loop",
        lambda: _ResolverLoop(("93.184.216.34",)),
    )

    assert await destinations.validate_public_destination("wiki.example.test", 443) == (
        "93.184.216.34",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("addresses", (("169.254.169.254",), ("93.184.216.34", "10.0.0.7")))
async def test_public_destination_validator_rejects_private_or_rebound_dns(
    addresses: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        destinations.asyncio,
        "get_running_loop",
        lambda: _ResolverLoop(addresses),
    )

    with pytest.raises(destinations.NetworkDestinationError, match="not public"):
        await destinations.validate_public_destination("wiki.example.test", 443)
