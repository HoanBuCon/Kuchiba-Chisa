"""Systems under evaluation; each turns a golden case into one observed final answer."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from evals.dataset import GoldenCase

# v1 evidence ids embed the wiki page id: raw_wiki:<pageid>:<revid>:<hash>:chunk:<n>.
_RAW_WIKI_PAGE = re.compile(r"^raw_wiki:(\d+):")


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
