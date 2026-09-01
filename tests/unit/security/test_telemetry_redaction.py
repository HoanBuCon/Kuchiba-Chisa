"""SEC-03 leakage and retention regressions for observability telemetry."""

from __future__ import annotations

import io
import json
import logging
from unittest.mock import AsyncMock

import pytest

from app.config.settings import settings
from app.domain.context import enable_clean_log
from app.domain.interfaces.llm_provider import LLMResponse, StructuredPrompt
from app.infrastructure.logging.llm_logger import (
    LLMTelemetryFormatter,
    llm_telemetry_logger,
    log_llm_transaction,
)
from app.infrastructure.logging.pipeline_tracker import PipelineTracker, pipeline_tracker


@pytest.mark.asyncio
async def test_pipeline_trace_is_metadata_only_and_drops_leakage_canaries() -> None:
    tracker = PipelineTracker()
    canaries = {
        "message": "USER_CANARY_DO_NOT_STORE",
        "system_prompt": "SYSTEM_CANARY_DO_NOT_STORE",
        "response": "RESPONSE_CANARY_DO_NOT_STORE",
        "reasoning": "REASONING_CANARY_DO_NOT_STORE",
        "history": "HISTORY_CANARY_DO_NOT_STORE",
        "secret": "SECRET_CANARY_DO_NOT_STORE",
    }

    tracker.start_trace(
        user_id="user@example.test",
        message=canaries["message"],
        pipeline="production",
        source="web",
        username="User Name",
        channel_name="private-channel",
        guild_name="tenant-a",
    )
    tracker.add_step(
        "llm_generation",
        {
            **canaries,
            "token_breakdown": {"total_tokens": 42, "reasoning_cot": 7},
            "model": "test-model",
            "input_tokens": 30,
            "output_tokens": 12,
        },
    )
    trace = tracker.end_trace(
        response_text=canaries["response"],
        emotions={"joy": 0.5},
        error=canaries["secret"],
    )

    serialized = json.dumps(trace)
    for canary in canaries.values():
        assert canary not in serialized
    assert "user_id" not in trace
    assert "message" not in trace
    assert "response" not in trace
    assert trace["input_char_count"] == len(canaries["message"])
    assert trace["response_char_count"] == len(canaries["response"])
    assert trace["steps"][0]["data"] == {
        "token_breakdown": {"total_tokens": 42, "reasoning_cot": 7},
        "model": "test-model",
        "input_tokens": 30,
        "output_tokens": 12,
    }


@pytest.mark.asyncio
async def test_llm_jsonl_telemetry_excludes_prompt_output_history_and_reasoning() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(LLMTelemetryFormatter())
    llm_telemetry_logger.addHandler(handler)
    token = enable_clean_log.set(True)
    pipeline_tracker.start_trace(
        user_id="telemetry-user",
        message="USER_CANARY_DO_NOT_STORE",
        pipeline="production",
    )
    try:
        await log_llm_transaction(
            StructuredPrompt(
                system="SYSTEM_CANARY_DO_NOT_STORE",
                user_message="USER_CANARY_DO_NOT_STORE",
                history=[{"role": "user", "content": "HISTORY_CANARY_DO_NOT_STORE"}],
                response_schema={"type": "object"},
            ),
            LLMResponse(
                raw_content="RESPONSE_CANARY_DO_NOT_STORE",
                parsed={"response": "RESPONSE_CANARY_DO_NOT_STORE"},
                reasoning_content="REASONING_CANARY_DO_NOT_STORE",
                input_tokens=10,
                output_tokens=5,
                model="test-model",
            ),
        )
    finally:
        pipeline_tracker.end_trace()
        enable_clean_log.reset(token)
        llm_telemetry_logger.removeHandler(handler)

    telemetry = stream.getvalue()
    for canary in (
        "SYSTEM_CANARY_DO_NOT_STORE",
        "USER_CANARY_DO_NOT_STORE",
        "HISTORY_CANARY_DO_NOT_STORE",
        "RESPONSE_CANARY_DO_NOT_STORE",
        "REASONING_CANARY_DO_NOT_STORE",
    ):
        assert canary not in telemetry
    payload = json.loads(telemetry)
    assert payload["event_type"] == "llm_generation"
    assert payload["prompt_tokens"] == 10
    assert payload["completion_tokens"] == 5
    assert payload["has_reasoning"] is True


@pytest.mark.asyncio
async def test_redis_trace_history_has_configured_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = PipelineTracker()
    redis = AsyncMock()
    from app.infrastructure.cache.redis import redis_service as redis_module

    monkeypatch.setattr(redis_module, "get_redis_client", lambda: redis)

    await tracker._push_history_redis({"id": "trace-1", "status": "success"})

    redis.expire.assert_awaited_once_with(
        "chisa:pipeline_history", settings.PIPELINE_TRACE_TTL_SECONDS
    )
