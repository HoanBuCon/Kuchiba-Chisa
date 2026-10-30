"""SSRF-safe public web page fetcher for the web-search deep-read step (B-1).

Search results are third-party, attacker-influenceable URLs. Every hop of a
fetch is therefore treated as untrusted:

* only ``http``/``https`` URLs without embedded credentials are accepted;
* the hostname is resolved and *every* resolved address must be public
  (``validate_public_destination``); IP literals are checked directly;
* the connection is pinned to the validated address (TLS SNI and certificate
  verification still use the original hostname), so a DNS answer cannot change
  between validation and connection (DNS rebinding);
* redirects are never followed automatically. Each ``Location`` is resolved
  and re-validated as a new hop, with a small hop budget;
* only textual content types are read, and the body is read incrementally up to
  a fixed byte budget so a hostile page cannot exhaust memory.

The fetcher returns ``""`` for every refused or failed fetch, which preserves the
existing web-search contract (an empty page is simply skipped).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.infrastructure.logging.logger import get_logger
from app.shared.security.network_destinations import (
    NetworkDestinationError,
    is_forbidden_ip,
    validate_public_destination,
)

log = get_logger(__name__)

_ALLOWED_SCHEMES = {"http": 80, "https": 443}
_TEXTUAL_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}

Resolver = Callable[[str, int], Awaitable[tuple[str, ...]]]


class UnsafeDestinationError(ValueError):
    """The requested URL or one of its redirect hops is not a public destination."""


@dataclass(frozen=True, slots=True)
class _PinnedTarget:
    request_url: str
    host_header: str
    sni_hostname: str | None


def _format_ip_for_url(address: str) -> str:
    parsed = ipaddress.ip_address(address)
    return f"[{parsed.compressed}]" if parsed.version == 6 else parsed.compressed


async def resolve_pinned_target(url: str, resolver: Resolver) -> _PinnedTarget:
    """Validate one hop and return a request target pinned to a public IP."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeDestinationError("unsupported URL scheme")
    if parts.username or parts.password:
        raise UnsafeDestinationError("credentials in URL are not allowed")
    hostname = parts.hostname
    if not hostname:
        raise UnsafeDestinationError("URL has no host")
    try:
        port = parts.port or _ALLOWED_SCHEMES[scheme]
    except ValueError as error:
        raise UnsafeDestinationError("invalid URL port") from error

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        if is_forbidden_ip(literal.compressed):
            raise UnsafeDestinationError("destination is not public")
        address = literal.compressed
        sni_hostname = None
    else:
        try:
            addresses = await resolver(hostname, port)
        except NetworkDestinationError as error:
            raise UnsafeDestinationError("destination is not public") from error
        address = addresses[0]
        sni_hostname = hostname

    default_port = _ALLOWED_SCHEMES[scheme]
    netloc = _format_ip_for_url(address)
    if port != default_port:
        netloc = f"{netloc}:{port}"
    host_header = hostname if port == default_port else f"{hostname}:{port}"
    request_url = urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))
    return _PinnedTarget(
        request_url=request_url,
        host_header=host_header,
        sni_hostname=sni_hostname if scheme == "https" else None,
    )


class SafePageFetcher:
    """Fetch public textual pages with per-hop SSRF validation and a size budget."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        max_bytes: int,
        max_redirects: int,
        timeout_seconds: float,
        resolver: Resolver = validate_public_destination,
    ) -> None:
        self._client = http_client
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._timeout = timeout_seconds
        self._resolver = resolver

    async def fetch(self, url: str, headers: Mapping[str, str] | None = None) -> str:
        try:
            return await self._fetch(url, dict(headers or {}))
        except UnsafeDestinationError as error:
            log.warning("Web page fetch refused by destination policy", policy=str(error))
        except (httpx.HTTPError, UnicodeDecodeError) as error:
            log.debug("Web page fetch failed", error_type=type(error).__name__)
        return ""

    async def _fetch(self, url: str, headers: dict[str, str]) -> str:
        current_url = url
        for _hop in range(self._max_redirects + 1):
            target = await resolve_pinned_target(current_url, self._resolver)
            request_headers = {**headers, "Host": target.host_header}
            extensions = {"sni_hostname": target.sni_hostname} if target.sni_hostname else {}
            request = self._client.build_request(
                "GET",
                target.request_url,
                headers=request_headers,
                timeout=self._timeout,
                extensions=extensions,
            )
            response = await self._client.send(request, stream=True, follow_redirects=False)
            try:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        return ""
                    current_url = urljoin(current_url, location)
                    continue
                if response.status_code != 200:
                    return ""
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                if content_type.lower() not in _TEXTUAL_CONTENT_TYPES:
                    return ""
                # Read incrementally and stop at the budget: large pages are
                # truncated (the search tool only keeps a short excerpt anyway).
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    remaining = self._max_bytes - len(body)
                    if remaining <= 0:
                        break
                    body.extend(chunk[:remaining])
                encoding = response.encoding or "utf-8"
                return bytes(body).decode(encoding, errors="replace")
            finally:
                await response.aclose()
        raise UnsafeDestinationError("too many redirects")
