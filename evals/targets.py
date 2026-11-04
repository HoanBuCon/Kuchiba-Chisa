"""Systems under evaluation; each turns a golden case into one observed final answer."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

import httpx

from evals.dataset import GoldenCase

# v1 evidence ids embed the wiki page id: raw_wiki:<pageid>:<revid>:<hash>:chunk:<n>.
_RAW_WIKI_PAGE = re.compile(r"^raw_wiki:(\d+):")
# v2 ids: wiki:<pageid>:<hash> for chunks, kb:<version>:<table>:<pageid> for lookups.
_V2_PAGE = re.compile(r"^wiki:(\d+):|^kb:[^:]+:[^:]+:(\d+)$")
_ABSTAINED_STATUSES = frozenset(
    {"no_evidence", "invalid_output", "output_leakage", "input_blocked"}
)


class TargetError(Exception):
    """The target failed to produce an answer for a case."""


class UnsupportedCaseError(Exception):
    """The target cannot run this case shape (for example multi-session memory)."""


@dataclass(frozen=True)
class Observation:
    answer: str
    # Page ids in rank order; empty when the target does not expose evidence.
    evidence_pages: tuple[int, ...] = ()
    abstained: bool | None = None
    latency_ms: float | None = None
    llm_calls: int | None = None
    cost_usd: float | None = None
    raw: dict[str, object] = field(default_factory=dict)


class EvalTarget(Protocol):
    name: str

    async def answer(self, case: GoldenCase) -> Observation: ...


def pages_from_evidence_ids(evidence_ids: list[str]) -> tuple[int, ...]:
    """Map evidence ids to wiki page ids, keeping first-seen order and dropping duplicates."""
    pages: list[int] = []
    for evidence_id in evidence_ids:
        match = _RAW_WIKI_PAGE.match(evidence_id)
        if match and int(match.group(1)) not in pages:
            pages.append(int(match.group(1)))
    return tuple(pages)


class HttpChatTarget:
    """Chisa v1 public chat API, one fresh anonymous principal per case so memory never leaks."""

    name = "chisa-v1-http"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def answer(self, case: GoldenCase) -> Observation:
        if case.sessions > 1:
            raise UnsupportedCaseError("anonymous sessions cannot span multiple conversations")
        headers = {"Authorization": f"Bearer {await self._anonymous_token()}"}
        payload: dict[str, object] = {}
        latency_ms = 0.0
        for turn in case.turns:
            started = time.perf_counter()
            payload = await self._post("/api/v1/chat", {"message": turn.message}, headers)
            latency_ms = (time.perf_counter() - started) * 1000
        raw_citations = payload.get("citations")
        citations = [str(item) for item in raw_citations] if isinstance(raw_citations, list) else []
        return Observation(
            answer=str(payload.get("response", "")),
            evidence_pages=pages_from_evidence_ids(citations),
            latency_ms=latency_ms,
            raw={"citations": citations},
        )

    async def _anonymous_token(self) -> str:
        payload = await self._post("/api/v1/auth/anonymous-session", None, {})
        return str(payload["access_token"])

    async def _post(
        self, path: str, body: dict[str, str] | None, headers: dict[str, str]
    ) -> dict[str, object]:
        try:
            response = await self._client.post(path, json=body, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise TargetError(f"{path}: {type(error).__name__}") from error
        payload: dict[str, object] = response.json()
        return payload


def pages_from_v2_events(evidence_ids: list[str]) -> tuple[int, ...]:
    pages: list[int] = []
    for evidence_id in evidence_ids:
        match = _V2_PAGE.match(evidence_id)
        page = int(match.group(1) or match.group(2)) if match else None
        if page is not None and page not in pages:
            pages.append(page)
    return tuple(pages)


def parse_sse(text: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    event = ""
    for line in text.splitlines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            events.append((event, json.loads(line.removeprefix("data: "))))
    return events


class HttpChatV2Target:
    """`/api/v2/chat/turns`, one thread per case, reading the server's own abstention status."""

    name = "chisa-v2-http"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def answer(self, case: GoldenCase) -> Observation:
        if case.sessions > 1:
            raise UnsupportedCaseError("anonymous sessions cannot span multiple conversations")
        headers = {"Authorization": f"Bearer {await self._anonymous_token()}"}
        thread_id: object = None
        events: list[tuple[str, dict[str, object]]] = []
        latency_ms = 0.0
        for turn in case.turns:
            body = {"message": turn.message, "turn_id": str(uuid4())}
            if thread_id:
                body["thread_id"] = str(thread_id)
            started = time.perf_counter()
            events = await self._turn(body, headers)
            latency_ms = (time.perf_counter() - started) * 1000
            thread_id = next((d["thread_id"] for e, d in events if e == "turn.started"), thread_id)
        return self._observation(events, latency_ms)

    @staticmethod
    def _observation(events: list[tuple[str, dict[str, object]]], latency_ms: float) -> Observation:
        final = next((d for e, d in events if e == "turn.completed"), None)
        if final is None:
            raise TargetError("turn did not complete")
        evidence = [str(d["evidence_id"]) for e, d in events if e == "evidence.added"]
        citations = final.get("citations")
        return Observation(
            answer=str(final.get("response", "")),
            evidence_pages=pages_from_v2_events(evidence),
            abstained=final.get("status") in _ABSTAINED_STATUSES,
            latency_ms=latency_ms,
            raw={"citations": citations, "status": final.get("status")},
        )

    async def _turn(
        self, body: dict[str, str], headers: dict[str, str]
    ) -> list[tuple[str, dict[str, object]]]:
        try:
            response = await self._client.post("/api/v2/chat/turns", json=body, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise TargetError(f"turn: {type(error).__name__}") from error
        return parse_sse(response.text)

    async def _anonymous_token(self) -> str:
        try:
            response = await self._client.post("/api/v1/auth/anonymous-session")
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise TargetError(f"session: {type(error).__name__}") from error
        return str(response.json()["access_token"])
