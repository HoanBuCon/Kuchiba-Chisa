"""FR-RAG-011 regressions for server-owned SSE output events."""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from fastapi import Request

from app.domain.value_objects.principal import PrincipalContext
from app.interface.api.routes import chat
from app.interface.api.schemas.chat import ChatRequest


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        return None


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
        }
    )


def _principal() -> PrincipalContext:
    return PrincipalContext(
        subject_id="verified-user",
        tenant_id=None,
        channel_id=None,
        source="web",
        kind="user",
        scopes=frozenset({"chat:write"}),
    )


async def _stream_body(response: Any) -> str:
    chunks = [chunk async for chunk in response.body_iterator]
    return "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_stream_emits_only_the_server_owned_grounding_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.infrastructure.database import engine

    async def fake_run(
        **kwargs: Any,
    ) -> tuple[str, dict[str, float], bool, list[object], list[object], list[str]]:
        on_token = kwargs["on_token"]
        token_result = on_token("approved token")
        if inspect.isawaitable(token_result):
            await token_result
        return "approved token", {}, False, [], [], ["lore:server-owned"]

    monkeypatch.setattr(engine, "AsyncSessionFactory", lambda: _Session())
    monkeypatch.setattr(chat, "_run_chat_request", fake_run)

    response = await chat.chat_stream_endpoint(
        request=ChatRequest(message="Tell me the lore"),
        http_request=_request(),
        principal=_principal(),
        chat_engine=object(),
    )

    body = await _stream_body(response)

    assert "event: meta" in body
    assert "event: token" in body
    assert "event: citation" in body
    assert '"citation_ids": ["lore:server-owned"]' in body
    assert "event: done" in body
    assert "event: complete" not in body


@pytest.mark.asyncio
async def test_stream_sanitizes_unexpected_error_before_sse_sink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.infrastructure.database import engine

    async def fake_run(**_: Any) -> None:
        raise RuntimeError("internal-provider-secret")

    monkeypatch.setattr(engine, "AsyncSessionFactory", lambda: _Session())
    monkeypatch.setattr(chat, "_run_chat_request", fake_run)

    response = await chat.chat_stream_endpoint(
        request=ChatRequest(message="Tell me the lore"),
        http_request=_request(),
        principal=_principal(),
        chat_engine=object(),
    )

    body = await _stream_body(response)

    assert "event: error" in body
    assert "InternalServerError" in body
    assert "internal-provider-secret" not in body
