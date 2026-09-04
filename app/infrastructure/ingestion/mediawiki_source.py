"""Typed MediaWiki adapter for the application ingestion source port."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.domain.entities.wiki import WikiPage, WikiRevision
from app.shared.security.network_destinations import (
    NetworkDestinationError,
    validate_public_destination,
)


class MediaWikiSourceError(RuntimeError):
    """A malformed or unavailable MediaWiki response prevented a safe sync."""


DestinationValidator = Callable[[str, int], Awaitable[tuple[str, ...]]]


class MediaWikiSource:
    """Enumerate configured categories and retrieve a concrete source revision.

    Only idempotent GETs are retried.  Every response is structurally validated
    before its external data crosses into the application layer.
    """

    _USER_AGENT = "KuchibaChisaIngestion/1.0 (+https://github.com/kuchiba-chisa)"

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        api_url: str,
        categories: Sequence[str],
        allowed_hosts: Sequence[str],
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
        destination_validator: DestinationValidator = validate_public_destination,
    ) -> None:
        if not categories:
            raise ValueError("at least one source category is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self._http_client = http_client
        self._api_url, self._hostname, self._port = self._validated_api_endpoint(
            api_url, allowed_hosts
        )
        self._categories = tuple(category.strip() for category in categories if category.strip())
        if not self._categories:
            raise ValueError("at least one non-empty source category is required")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._destination_validator = destination_validator

    async def get_all_pages(self) -> AsyncIterator[WikiPage]:
        """Yield a de-duplicated versioned page inventory for configured categories."""
        seen_page_ids: set[int] = set()
        for category in self._categories:
            continuation: str | None = None
            while True:
                params: dict[str, str] = {
                    "action": "query",
                    "format": "json",
                    "formatversion": "2",
                    "list": "categorymembers",
                    "cmtitle": f"Category:{category}",
                    "cmtype": "page",
                    "cmlimit": "500",
                }
                if continuation is not None:
                    params["cmcontinue"] = continuation
                payload = await self._get_json(params)
                members = self._category_members(payload)
                page_ids = [
                    member["pageid"]
                    for member in members
                    if member["pageid"] not in seen_page_ids
                ]
                if page_ids:
                    for page in await self._page_metadata(page_ids):
                        seen_page_ids.add(page.page_id)
                        yield page
                continuation = self._continuation(payload, "cmcontinue")
                if continuation is None:
                    break

    async def download_page(self, page_id: int) -> WikiRevision:
        """Download the newest revision for one previously selected source page."""
        if page_id < 1:
            raise ValueError("page_id must be positive")
        payload = await self._get_json(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "revisions",
                "pageids": str(page_id),
                "rvprop": "ids|timestamp|content",
                "rvslots": "main",
                "rvlimit": "1",
            }
        )
        pages = self._pages(payload)
        if len(pages) != 1 or pages[0].get("missing") is not None:
            raise MediaWikiSourceError("selected page is absent from source")
        page = pages[0]
        if page.get("pageid") != page_id:
            raise MediaWikiSourceError("source response page identifier mismatch")
        title = self._required_str(page, "title")
        revisions = page.get("revisions")
        if (
            not isinstance(revisions, list)
            or len(revisions) != 1
            or not isinstance(revisions[0], dict)
        ):
            raise MediaWikiSourceError("source response has no concrete revision")
        revision = revisions[0]
        revision_id = self._positive_int(revision.get("revid"), "revision id")
        timestamp = self._parse_timestamp(self._required_str(revision, "timestamp"))
        content = self._revision_content(revision)
        return WikiRevision(
            page_id=page_id,
            title=title,
            revision_id=revision_id,
            content=content,
            timestamp=timestamp,
        )

    async def _page_metadata(self, page_ids: Sequence[int]) -> list[WikiPage]:
        payload = await self._get_json(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "prop": "revisions",
                "pageids": "|".join(str(page_id) for page_id in page_ids),
                "rvprop": "ids|timestamp",
                "rvlimit": "1",
            }
        )
        pages: list[WikiPage] = []
        for page in self._pages(payload):
            if page.get("missing") is not None:
                continue
            page_id = self._positive_int(page.get("pageid"), "page id")
            title = self._required_str(page, "title")
            revisions = page.get("revisions")
            if (
                not isinstance(revisions, list)
                or len(revisions) != 1
                or not isinstance(revisions[0], dict)
            ):
                raise MediaWikiSourceError("page inventory is missing a latest revision")
            latest = revisions[0]
            pages.append(
                WikiPage(
                    page_id=page_id,
                    title=title,
                    latest_revision_id=self._positive_int(latest.get("revid"), "revision id"),
                    last_updated=self._parse_timestamp(self._required_str(latest, "timestamp")),
                )
            )
        return pages

    async def _get_json(self, params: dict[str, str]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                await self._validate_destination()
                response = await self._http_client.get(
                    self._api_url,
                    params=params,
                    headers={"User-Agent": self._USER_AGENT},
                    timeout=self._timeout_seconds,
                    follow_redirects=False,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or "error" in payload:
                    raise MediaWikiSourceError("MediaWiki returned an invalid API payload")
                return payload
            except (httpx.HTTPError, ValueError, MediaWikiSourceError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(0.1 * (2**attempt))
        raise MediaWikiSourceError("MediaWiki request failed after bounded retries") from last_error

    async def _validate_destination(self) -> None:
        try:
            await self._destination_validator(self._hostname, self._port)
        except NetworkDestinationError as error:
            raise MediaWikiSourceError("MediaWiki source destination is not permitted") from error

    @staticmethod
    def _validated_api_endpoint(
        api_url: str, allowed_hosts: Sequence[str]
    ) -> tuple[str, str, int]:
        hosts = {host.strip().casefold().rstrip(".") for host in allowed_hosts if host.strip()}
        if not hosts:
            raise ValueError("at least one ingestion source host must be allowlisted")
        try:
            parsed = urlsplit(api_url)
            port = parsed.port or 443
        except ValueError as error:
            raise ValueError("MediaWiki API endpoint is invalid") from error
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or port != 443
            or hostname not in hosts
        ):
            raise ValueError("MediaWiki API endpoint is not allowlisted HTTPS")
        return api_url, hostname, port

    @staticmethod
    def _category_members(payload: dict[str, Any]) -> list[dict[str, Any]]:
        query = payload.get("query")
        members = query.get("categorymembers") if isinstance(query, dict) else None
        if not isinstance(members, list):
            raise MediaWikiSourceError("MediaWiki category inventory is malformed")
        valid: list[dict[str, Any]] = []
        for member in members:
            if not isinstance(member, dict):
                raise MediaWikiSourceError("MediaWiki category member is malformed")
            valid.append({"pageid": MediaWikiSource._positive_int(member.get("pageid"), "page id")})
        return valid

    @staticmethod
    def _pages(payload: dict[str, Any]) -> list[dict[str, Any]]:
        query = payload.get("query")
        pages = query.get("pages") if isinstance(query, dict) else None
        if not isinstance(pages, list) or any(not isinstance(page, dict) for page in pages):
            raise MediaWikiSourceError("MediaWiki pages response is malformed")
        return pages

    @staticmethod
    def _continuation(payload: dict[str, Any], key: str) -> str | None:
        continuation = payload.get("continue")
        if continuation is None:
            return None
        if not isinstance(continuation, dict):
            raise MediaWikiSourceError("MediaWiki continuation response is malformed")
        value = continuation.get(key)
        if not isinstance(value, str) or not value:
            raise MediaWikiSourceError("MediaWiki continuation token is malformed")
        return value

    @staticmethod
    def _required_str(payload: dict[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise MediaWikiSourceError(f"MediaWiki {field} is invalid")
        return value

    @staticmethod
    def _positive_int(value: object, label: str) -> int:
        if not isinstance(value, int) or value < 1:
            raise MediaWikiSourceError(f"MediaWiki {label} is invalid")
        return value

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MediaWikiSourceError("MediaWiki timestamp is invalid") from exc
        if parsed.tzinfo is None:
            raise MediaWikiSourceError("MediaWiki timestamp must include a timezone")
        return parsed.astimezone(UTC)

    @staticmethod
    def _revision_content(revision: dict[str, Any]) -> str:
        slots = revision.get("slots")
        if isinstance(slots, dict):
            main = slots.get("main")
            if isinstance(main, dict) and isinstance(main.get("*"), str):
                return main["*"]
        legacy_content = revision.get("*")
        if isinstance(legacy_content, str):
            return legacy_content
        raise MediaWikiSourceError("MediaWiki revision content is invalid")
