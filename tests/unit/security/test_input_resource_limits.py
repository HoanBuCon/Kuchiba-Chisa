"""SEC-05 regression tests for admission limits before costly processing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.config.settings import settings
from app.domain.services.image_ingestion import ImageIngestionService
from app.interface.api.schemas.chat import ChatRequest
from app.interface.api.schemas.community import CommunityChatRequest
from app.interface.middlewares.request_body_limit import RequestBodyLimitMiddleware
from app.shared.security.vision_security import ImageValidationError


def _community_message(index: int) -> dict[str, str | bool]:
    return {
        "message_id": f"message-{index}",
        "speaker_id": f"speaker-{index}",
        "speaker_name": "Speaker",
        "content": "short message",
        "is_bot": False,
    }


def test_chat_schema_rejects_excessive_image_count_before_ingestion() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {"message": "hello", "images": ["https://cdn.discordapp.com/a.png"] * 5}
        )


def test_schema_preflights_encoded_and_aggregate_image_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "VISION_MAX_IMAGE_BYTES", 4)
    monkeypatch.setattr(settings, "VISION_MAX_TOTAL_DECODED_BYTES", 5)

    with pytest.raises(ValidationError, match="decoded image payload is too large"):
        ChatRequest.model_validate({"message": "hello", "images": ["AAAAAAA"]})
    with pytest.raises(ValidationError, match="aggregate decoded image payload is too large"):
        ChatRequest.model_validate({"message": "hello", "images": ["AAAA", "AAAA"]})


def test_community_schema_rejects_excessive_history_and_oversized_fields() -> None:
    with pytest.raises(ValidationError):
        CommunityChatRequest.model_validate(
            {
                "message": "hello",
                "recent_messages": [
                    _community_message(index)
                    for index in range(settings.COMMUNITY_MAX_HISTORY_MESSAGES + 1)
                ],
            }
        )
    with pytest.raises(ValidationError):
        CommunityChatRequest.model_validate(
            {
                "message": "hello",
                "recent_messages": [
                    {
                        **_community_message(1),
                        "content": "x" * (settings.COMMUNITY_MAX_MESSAGE_CHARS + 1),
                    }
                ],
            }
        )


@pytest.mark.asyncio
async def test_body_limit_rejects_declared_and_actual_oversized_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "API_MAX_REQUEST_BODY_BYTES", 4)
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware)

    @app.post("/api/v1/chat")
    async def echo_size(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        declared = await client.post("/api/v1/chat", content=b"12345")
        actual = await client.post(
            "/api/v1/chat",
            content=b"12345",
            headers={"Content-Length": "1"},
        )

    assert declared.status_code == 413
    assert actual.status_code == 413


@pytest.mark.asyncio
async def test_image_ingestion_rejects_invalid_base64_without_permissive_decode() -> None:
    service = ImageIngestionService(storage=SimpleNamespace())

    with pytest.raises(ImageValidationError):
        await service._resolve_raw_bytes("data:image/png;base64,%%%not-base64%%%")
