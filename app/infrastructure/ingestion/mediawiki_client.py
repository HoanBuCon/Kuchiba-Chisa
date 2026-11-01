"""Polite MediaWiki API client for the wiki sync (ING-002, ING-013, ING-018).

Pacing, Retry-After handling, the maxlag retry and the continuation-loop guard follow the
crawler that IndexBeast ran on 4,164 pages (docs/ingestion/indexbeast-lessons.md, L1/L2).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.domain.ingestion.pages import WikiPageInfo
from app.domain.interfaces.wiki_ingestion import ParsedPage, WikiSourceError
from app.infrastructure.ingestion.wiki_sync_config import SourceSettings

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
BATCH = 50  # anonymous API limit for multi-page queries
MAXLAG_RETRIES = 3


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def retry_after_seconds(header: str | None, attempt: int, now: datetime) -> float:
    """Honour Retry-After as seconds or an HTTP date; otherwise back off exponentially."""
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            try:
                return max(0.0, (parsedate_to_datetime(header) - now).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return float(2 ** (attempt + 1))


class MediaWikiClient:
    """Every request starts at least `min_interval_seconds` after the previous one."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: SourceSettings,
        *,
        sleep: Callable[[float], Any] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._settings = settings
        self._host = urlsplit(settings.api_url).hostname
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None
        self.requests = 0

    async def _pace(self) -> None:
        if self._last_request is not None:
            wait = self._settings.min_interval_seconds - (self._clock() - self._last_request)
            if wait > 0:
                await self._sleep(wait)
        self._last_request = self._clock()

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        query = {"format": "json", "formatversion": "2", "maxlag": "5", **params}
        for attempt in range(self._settings.max_retries + 1):
            await self._pace()
            self.requests += 1
            try:
                response = await self._client.get(self._settings.api_url, params=query)
            except httpx.TransportError as error:
                pause, reason = float(2 ** (attempt + 1)), type(error).__name__
            else:
                if urlsplit(str(response.url)).hostname != self._host:
                    raise WikiSourceError("redirected outside the configured wiki host")
                if response.status_code not in RETRYABLE_STATUS:
                    return self._decode(response)
                pause = retry_after_seconds(
                    response.headers.get("Retry-After"), attempt, datetime.now(UTC)
                )
                reason = f"HTTP {response.status_code}"
            if attempt == self._settings.max_retries or pause > self._settings.max_wait_seconds:
                raise WikiSourceError(f"{reason}; retry budget or wait limit reached")
            await self._sleep(pause)
        raise WikiSourceError("retry budget exhausted")

    def _decode(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code != 200:
            raise WikiSourceError(f"HTTP {response.status_code}")
        if len(response.content) > self._settings.max_response_bytes:
            raise WikiSourceError("response exceeds the byte limit")
        try:
            payload = response.json()
        except json.JSONDecodeError as error:
            raise WikiSourceError("expected JSON; possible challenge page") from error
        if not isinstance(payload, dict):
            raise WikiSourceError("expected a JSON object")
        return payload

    async def api(self, **params: Any) -> dict[str, Any]:
        for attempt in range(MAXLAG_RETRIES):
            payload = await self._get(params)
            error = payload.get("error")
            if not error:
                return payload
            if error.get("code") != "maxlag" or attempt == MAXLAG_RETRIES - 1:
                raise WikiSourceError(f"MediaWiki error: {error.get('code', 'unknown')}")
            await self._sleep(5.0 * (attempt + 1))
        raise WikiSourceError("maxlag retries exhausted")

    async def _continued(self, **params: Any) -> list[dict[str, Any]]:
        """Follow `continue` tokens, refusing a token the server already returned."""
        pages: list[dict[str, Any]] = []
        continuation: dict[str, Any] = {}
        seen: set[str] = set()
        while True:
            payload = await self.api(**params, **continuation)
            pages.append(payload)
            continuation = payload.get("continue", {})
            if not continuation:
                return pages
            token = repr(sorted(continuation.items()))
            if token in seen:
                raise WikiSourceError("repeated continuation token")
            seen.add(token)

    async def list_page_ids(self) -> dict[int, str]:
        batches = await self._continued(
            action="query",
            list="allpages",
            apnamespace=0,
            apfilterredir="nonredirects",
            aplimit="max",
        )
        return {row["pageid"]: row["title"] for b in batches for row in b["query"]["allpages"]}

    async def page_infos(self, page_ids: Sequence[int]) -> list[WikiPageInfo]:
        infos = []
        for start in range(0, len(page_ids), BATCH):
            batch = page_ids[start : start + BATCH]
            payload = await self.api(
                action="query",
                prop="info|revisions",
                rvprop="ids|timestamp",
                pageids="|".join(map(str, batch)),
            )
            for page in payload.get("query", {}).get("pages", []):
                if "missing" in page or "lastrevid" not in page:
                    continue
                revised = (page.get("revisions") or [{}])[0].get("timestamp")
                infos.append(
                    WikiPageInfo(
                        page_id=page["pageid"],
                        title=page["title"],
                        last_revid=page["lastrevid"],
                        touched=_timestamp(page["touched"]),
                        revision_timestamp=_timestamp(revised) if revised else None,
                    )
                )
        return infos

    async def page_details(
        self, page_ids: Sequence[int]
    ) -> dict[int, tuple[tuple[str, ...], tuple[str, ...]]]:
        details: dict[int, tuple[set[str], set[str]]] = {}
        for start in range(0, len(page_ids), BATCH):
            batches = await self._continued(
                action="query",
                prop="categories|templates",
                cllimit="max",
                tllimit="max",
                tlnamespace=10,
                pageids="|".join(map(str, page_ids[start : start + BATCH])),
            )
            for payload in batches:
                for page in payload.get("query", {}).get("pages", []):
                    categories, templates = details.setdefault(page["pageid"], (set(), set()))
                    categories.update(c["title"] for c in page.get("categories", []))
                    templates.update(t["title"] for t in page.get("templates", []))
        return {pid: (tuple(sorted(c)), tuple(sorted(t))) for pid, (c, t) in details.items()}

    async def subcategories(self, parent: str) -> list[str]:
        batches = await self._continued(
            action="query",
            list="categorymembers",
            cmtitle=f"Category:{parent}",
            cmtype="subcat",
            cmlimit="max",
        )
        return [
            m["title"].removeprefix("Category:")
            for b in batches
            for m in b["query"]["categorymembers"]
        ]

    async def changed_templates(self, since: datetime) -> frozenset[str]:
        batches = await self._continued(
            action="query",
            list="recentchanges",
            rcnamespace="10|828",
            rctype="edit|new",
            rcprop="title",
            rcend=since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            rclimit="max",
        )
        return frozenset(c["title"] for b in batches for c in b["query"]["recentchanges"])

    async def deleted_titles(self, since: datetime) -> frozenset[str]:
        batches = await self._continued(
            action="query",
            list="logevents",
            letype="delete",
            leprop="title|type",
            leend=since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            lelimit="max",
        )
        return frozenset(
            e["title"]
            for b in batches
            for e in b["query"]["logevents"]
            if e.get("action") != "restore"
        )

    async def parse(self, page_id: int) -> ParsedPage:
        payload = await self.api(
            action="parse",
            pageid=page_id,
            prop="text|revid|categories|sections|templates|displaytitle|properties",
        )
        parsed = payload.get("parse") or {}
        if not parsed.get("revid") or not isinstance(parsed.get("text"), str):
            raise WikiSourceError(f"page {page_id}: missing parsed HTML or revision")
        title = parsed["title"]
        return ParsedPage(
            page_id=parsed["pageid"],
            title=title,
            revid=parsed["revid"],
            html=parsed["text"],
            # parse spells categories with underscores; prop=categories uses spaces.
            categories=tuple(
                c.get("category", "").replace("_", " ") for c in parsed.get("categories", [])
            ),
            templates=tuple(t["title"] for t in parsed.get("templates", []) if t.get("ns") == 10),
            sections=tuple(parsed.get("sections", [])),
            # formatversion=2 returns page properties (e.g. PortableInfobox JSON) as an object.
            properties={str(k): str(v) for k, v in (parsed.get("properties") or {}).items()},
            url=self._settings.page_url.format(title=quote(title.replace(" ", "_"), safe="")),
            license=self._settings.license,
            fetched_at=datetime.now(UTC),
        )
