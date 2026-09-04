"""Shared, fail-closed validation for externally resolved network destinations."""

from __future__ import annotations

import asyncio
import ipaddress
import socket

FORBIDDEN_IP_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),
)


class NetworkDestinationError(ValueError):
    """A destination cannot be used for an outbound request."""


def is_forbidden_ip(ip_address: str) -> bool:
    """Return whether an IP literal belongs to a non-public destination range."""
    try:
        parsed = ipaddress.ip_address(ip_address)
    except ValueError:
        return True
    return any(parsed in network for network in FORBIDDEN_IP_NETWORKS)


async def validate_public_destination(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve a hostname and reject it if any address is non-public.

    Callers must repeat validation for each outbound request and disable
    automatic redirects. Connection-level DNS pinning belongs to the deployed
    egress proxy or transport, not this resolver alone.
    """
    if not hostname or not 1 <= port <= 65_535:
        raise NetworkDestinationError("network destination is invalid")
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError as error:
        raise NetworkDestinationError("network destination could not be resolved") from error

    resolved = tuple(dict.fromkeys(address[4][0] for address in addresses if address[4]))
    if not resolved or any(is_forbidden_ip(address) for address in resolved):
        raise NetworkDestinationError("network destination is not public")
    return resolved
