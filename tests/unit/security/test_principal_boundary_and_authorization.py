"""SEC-01/SEC-02/API-01 regression tests for trusted identity boundaries."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from jose import jwt
from pydantic import ValidationError

from app.config.settings import settings
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.security.jwt_authenticator import AuthenticationError, jwt_authenticator
from app.interface.api.routes import chat, community
from app.interface.api.schemas.chat import ChatRequest
from app.interface.api.schemas.community import CommunityChatRequest
from app.interface.middlewares.rate_limiter import RateLimitMiddleware


def _token(
    *,
    subject_id: str,
    scopes: list[str],
    token_use: str = "web",
    tenant_id: str | None = None,
    channel_id: str | None = None,
    source: str | None = None,
) -> str:
    now = int(time.time())
    is_workload = token_use == "workload"
    claims = {
        "sub": subject_id,
        "scopes": scopes,
        "token_use": token_use,
        "source": source or ("discord" if is_workload else "web"),
        "iss": settings.DISCORD_WORKLOAD_JWT_ISSUER if is_workload else settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": now + 120,
    }
    if tenant_id is not None:
        claims["tenant_id"] = tenant_id
    if channel_id is not None:
        claims["channel_id"] = channel_id
    secret = settings.DISCORD_WORKLOAD_JWT_SECRET if is_workload else settings.JWT_SECRET
    return jwt.encode(claims, secret, algorithm=settings.JWT_ALGORITHM)


def _principal(subject_id: str, scopes: set[str], tenant_id: str | None = None) -> PrincipalContext:
    return PrincipalContext(
        subject_id=subject_id,
        tenant_id=tenant_id,
        channel_id="channel-a" if tenant_id else None,
        source="discord" if tenant_id else "web",
        kind="workload" if tenant_id else "user",
        scopes=frozenset(scopes),
    )


def test_principal_context_is_derived_from_verified_jwt_only() -> None:
    token = _token(subject_id="verified-user", scopes=["chat:write"])

    principal = jwt_authenticator.authenticate_bearer(f"Bearer {token}")

    assert principal.subject_id == "verified-user"
    assert principal.source == "web"
    with pytest.raises(AuthenticationError):
        jwt_authenticator.authenticate_bearer("Bearer forged.token.value")


@pytest.mark.asyncio
async def test_anonymous_session_is_server_issued_and_rotates_verified_subject(
    client: AsyncClient,
) -> None:
    initial = await client.post("/api/v1/auth/anonymous-session")

    assert initial.status_code == 200
    initial_data = initial.json()
    initial_principal = jwt_authenticator.authenticate_bearer(
        f"Bearer {initial_data['access_token']}"
    )
    assert initial_principal.subject_id == initial_data["subject_id"]
    assert initial_principal.source == "web"
    assert initial_principal.scopes == frozenset({"chat:clear", "chat:read", "chat:write"})

    rotated = await client.post(
        "/api/v1/auth/anonymous-session",
        headers={"Authorization": f"Bearer {initial_data['access_token']}"},
    )
    assert rotated.status_code == 200
    assert rotated.json()["subject_id"] == initial_data["subject_id"]
    assert rotated.json()["access_token"] != initial_data["access_token"]


@pytest.mark.asyncio
async def test_anonymous_session_rejects_invalid_or_workload_credential(
    client: AsyncClient,
) -> None:
    invalid = await client.post(
        "/api/v1/auth/anonymous-session", headers={"Authorization": "Bearer forged.token"}
    )
    workload = await client.post(
        "/api/v1/auth/anonymous-session",
        headers={
            "Authorization": (
                "Bearer "
                f"{_token(subject_id='worker', scopes=['chat:write'], token_use='workload')}"
            )
        },
    )

    assert invalid.status_code == 401
    assert workload.status_code == 403


@pytest.mark.asyncio
async def test_protected_routes_reject_missing_or_invalid_credentials(client: AsyncClient) -> None:
    missing = await client.get("/api/v1/chat/history/user-a")
    invalid = await client.get(
        "/api/v1/chat/history/user-a", headers={"Authorization": "Bearer invalid.token"}
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401


@pytest.mark.asyncio
async def test_chat_route_requires_scope_before_resource_dependencies(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {_token(subject_id='user-a', scopes=['chat:read'])}"},
        json={"message": "hello"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_chat_payload_identity_fields_are_rejected_and_principal_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _principal("verified-user", {"chat:write"})
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {"user_id": "attacker-selected-user", "source": "discord", "message": "hello"}
        )

    request = ChatRequest(message="hello")
    monkeypatch.setattr(chat, "_start_chat_trace", lambda *args: "trace-1")
    monkeypatch.setattr(
        chat,
        "_run_chat_request",
        AsyncMock(return_value=("ok", {}, False, [], [], ["lore:server-owned"])),
    )

    response = await chat.chat_endpoint(
        request=request,
        http_request=SimpleNamespace(headers={}),
        principal=principal,
        session=SimpleNamespace(),
        chat_engine=SimpleNamespace(),
    )

    assert response.user_id == "verified-user"
    assert response.citations == ["lore:server-owned"]
    run_call = chat._run_chat_request.await_args.kwargs
    assert run_call["original_user_id"] == "verified-user"
    assert run_call["normalized_user_id"] != "attacker-selected-user"


@pytest.mark.asyncio
async def test_history_emotion_and_clear_deny_cross_user_access() -> None:
    principal = _principal("user-a", {"chat:read", "chat:clear"})
    engine = SimpleNamespace(
        get_history=AsyncMock(),
        get_emotion_state=AsyncMock(),
    )
    clear_use_case = SimpleNamespace(execute=AsyncMock())

    for operation in (
        chat.get_chat_history(
            user_id="user-b", principal=principal, session=SimpleNamespace(), chat_engine=engine
        ),
        chat.get_emotions(
            user_id="user-b", principal=principal, session=SimpleNamespace(), chat_engine=engine
        ),
        chat.clear_user_memory(
            user_id="user-b",
            principal=principal,
            session=SimpleNamespace(),
            clear_use_case=clear_use_case,
        ),
    ):
        with pytest.raises(HTTPException) as error:
            await operation
        assert error.value.status_code == 403

    engine.get_history.assert_not_awaited()
    engine.get_emotion_state.assert_not_awaited()
    clear_use_case.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_clear_returns_retry_job_status_without_converting_it_to_server_error() -> None:
    principal = _principal("user-a", {"chat:clear"})
    clear_use_case = SimpleNamespace(
        execute=AsyncMock(
            return_value={"job_id": "job-a", "status": "retry_required", "stores": {}}
        )
    )

    response = await chat.clear_user_memory(
        user_id="user-a",
        principal=principal,
        session=SimpleNamespace(),
        clear_use_case=clear_use_case,
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 202
    assert b'"erasure_job_id":"job-a"' in response.body


@pytest.mark.asyncio
async def test_community_tenant_clear_denies_cross_tenant_and_query_spoofing() -> None:
    principal = _principal("user-a", {"community:clear:any"}, tenant_id="tenant-a")
    clear_use_case = SimpleNamespace(execute=AsyncMock())

    with pytest.raises(HTTPException) as error:
        await community.clear_community_memory_endpoint(
            guild_id="tenant-b",
            principal=principal,
            scope="all",
            channel_id="attacker-channel",
            user_id="attacker-user",
            session=SimpleNamespace(),
            clear_use_case=clear_use_case,
        )

    assert error.value.status_code == 403
    clear_use_case.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_community_clear_returns_retry_job_status_without_server_error() -> None:
    principal = _principal("user-a", {"community:clear:any"}, tenant_id="tenant-a")
    clear_use_case = SimpleNamespace(
        execute=AsyncMock(
            return_value={"job_id": "job-a", "status": "retry_required", "stores": {}}
        )
    )

    response = await community.clear_community_memory_endpoint(
        guild_id="tenant-a",
        principal=principal,
        scope="all",
        session=SimpleNamespace(),
        clear_use_case=clear_use_case,
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 202
    assert b'"erasure_job_id":"job-a"' in response.body


@pytest.mark.asyncio
async def test_community_payload_identity_fields_are_rejected_and_principal_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = PrincipalContext(
        subject_id="verified-user",
        tenant_id="tenant-a",
        channel_id="channel-a",
        source="discord",
        kind="workload",
        scopes=frozenset({"community:write"}),
        display_name="Verified Name",
    )
    with pytest.raises(ValidationError):
        CommunityChatRequest.model_validate(
            {
                "channel_id": "attacker-channel",
                "guild_id": "tenant-b",
                "user_id": "attacker-user",
                "username": "attacker-name",
                "message": "hello",
            }
        )

    request = CommunityChatRequest(message="hello")
    engine = SimpleNamespace(
        community_chat_detailed=AsyncMock(
            return_value=SimpleNamespace(
                reply_text="ok",
                emotions={},
                images_processed=[],
                attached_images=[],
                citation_ids=["lore:server-owned"],
            )
        ),
    )
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    monkeypatch.setattr(pipeline_tracker, "start_trace", lambda **kwargs: "trace-1")
    monkeypatch.setattr(pipeline_tracker, "end_trace", lambda **kwargs: None)

    response = await community.community_chat_endpoint(
        request=request, principal=principal, session=session, chat_engine=engine
    )

    call = engine.community_chat_detailed.await_args.kwargs
    assert call["user_id"] == "verified-user"
    assert call["guild_id"] == "tenant-a"
    assert call["channel_id"] == "channel-a"
    assert call["speaker_name"] == "Verified Name"
    assert response.citations == ["lore:server-owned"]


@pytest.mark.asyncio
async def test_rate_limit_key_cannot_be_bypassed_by_client_identity_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = RateLimitMiddleware(app=SimpleNamespace())
    principal = _principal("verified-user", {"chat:write"}, tenant_id="tenant-a")
    original_limit = settings.RATE_LIMIT_PER_MINUTE
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(
        redis_service, "consume_token_bucket", AsyncMock(side_effect=RuntimeError())
    )

    key = limiter._rate_limit_key(principal, "POST", "/api/v1/chat")
    assert key == limiter._rate_limit_key(principal, "POST", "/api/v1/chat")
    assert "verified-user" not in key
    assert "X-User-ID" not in RateLimitMiddleware.__dict__

    first = await limiter._check_rate(principal, "POST", "/api/v1/chat")
    second = await limiter._check_rate(principal, "POST", "/api/v1/chat")
    third = await limiter._check_rate(principal, "POST", "/api/v1/chat")

    assert first[0] is True
    assert second[0] is True
    assert third[0] is False
    assert settings.RATE_LIMIT_PER_MINUTE == 2
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", original_limit)


@pytest.mark.asyncio
async def test_rate_limit_middleware_uses_verified_principal_not_client_identity_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the ASGI boundary rather than only the limiter helper."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post("/api/v1/chat")
    async def protected_route(request: Request) -> dict[str, str]:
        principal = request.state.principal
        return {"subject_id": principal.subject_id}

    principal = _principal("verified-user", {"chat:write"}, tenant_id="tenant-a")
    consumed_keys: list[str] = []

    def authenticate(authorization: str | None) -> PrincipalContext:
        if authorization == "Bearer verified":
            return principal
        raise AuthenticationError("invalid")

    monkeypatch.setattr(jwt_authenticator, "authenticate_bearer", authenticate)

    async def consume_token_bucket(**kwargs):
        consumed_keys.append(kwargs["key"])
        return True, 10, 60.0

    monkeypatch.setattr(redis_service, "consume_token_bucket", consume_token_bucket)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first = await client.post(
            "/api/v1/chat",
            headers={"Authorization": "Bearer verified", "X-User-ID": "attacker-a"},
        )
        second = await client.post(
            "/api/v1/chat",
            headers={"Authorization": "Bearer verified", "X-User-ID": "attacker-b"},
        )
        rejected = await client.post(
            "/api/v1/chat",
            headers={"Authorization": "Bearer invalid", "X-User-ID": "verified-user"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"subject_id": "verified-user"}
    assert second.json() == {"subject_id": "verified-user"}
    assert rejected.status_code == 401
    assert consumed_keys[0] == consumed_keys[2]
    assert "attacker-a" not in consumed_keys[0]
    assert "attacker-b" not in consumed_keys[2]


@pytest.mark.asyncio
async def test_anonymous_session_minting_has_bounded_pre_auth_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = RateLimitMiddleware(app=SimpleNamespace())
    monkeypatch.setattr(settings, "ANONYMOUS_SESSION_RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(
        redis_service, "consume_token_bucket", AsyncMock(side_effect=RuntimeError())
    )

    first = await limiter._check_anonymous_session_rate("198.51.100.20")
    second = await limiter._check_anonymous_session_rate("198.51.100.20")
    third = await limiter._check_anonymous_session_rate("198.51.100.20")

    assert first[0] is True
    assert second[0] is True
    assert third[0] is False
