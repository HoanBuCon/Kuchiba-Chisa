from unittest.mock import AsyncMock, MagicMock

import groq
import httpx
import pytest
from google.genai import errors as genai_errors

from app.domain.interfaces.llm_provider import (
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    StructuredPrompt,
)
from app.infrastructure.llm.adapters import gemini
from app.infrastructure.llm.adapters import groq as groq_adapter
from app.infrastructure.llm.adapters.billing import billing_exhausted_error
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter


def _prompt() -> StructuredPrompt:
    return StructuredPrompt(system="s", history=[], user_message="hi", response_schema={})


def _groq_status_error(status: int) -> groq.APIStatusError:
    request = httpx.Request("POST", "https://api.groq.com/x")
    response = httpx.Response(status, request=request)
    return groq.APIStatusError(f"Error code: {status} - boom", response=response, body=None)


def _is_billing(error: LLMError) -> bool:
    return error.code == "BILLING" and error.retryable is False


def test_billing_helper_builds_terminal_billing_error():
    error = billing_exhausted_error("Acme")
    assert _is_billing(error)
    assert "Acme" in str(error)


def test_gemini_maps_402_to_billing():
    assert _is_billing(gemini._translate_gemini_error(genai_errors.APIError(402, {})))


def test_gemini_keeps_other_mappings():
    quota = genai_errors.APIError(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
    assert isinstance(gemini._translate_gemini_error(quota), LLMRateLimitError)
    assert isinstance(gemini._translate_gemini_error(TimeoutError("timeout")), LLMTimeoutError)
    auth = gemini._translate_gemini_error(genai_errors.APIError(403, {}))
    assert auth.code == "AUTH_CONFIG"
    unknown = gemini._translate_gemini_error(RuntimeError("boom"))
    assert unknown.code == "TRANSPORT"


def test_groq_maps_402_to_billing():
    assert _is_billing(groq_adapter._translate_groq_error(_groq_status_error(402)))


def test_groq_keeps_other_mappings():
    assert isinstance(
        groq_adapter._translate_groq_error(_groq_status_error(429)), LLMRateLimitError
    )
    assert groq_adapter._translate_groq_error(_groq_status_error(401)).code == "AUTH_CONFIG"
    assert groq_adapter._translate_groq_error(_groq_status_error(503)).code == "PROVIDER_5XX"
    assert groq_adapter._translate_groq_error(RuntimeError("boom")).code == "TRANSPORT"


@pytest.mark.asyncio
async def test_gemini_generate_raises_billing_on_402(monkeypatch):
    monkeypatch.setattr(gemini.genai, "Client", MagicMock())
    adapter = gemini.GeminiAdapter()
    adapter._client = MagicMock()
    adapter._client.aio.models.generate_content = AsyncMock(
        side_effect=genai_errors.APIError(402, {})
    )
    with pytest.raises(LLMError) as raised:
        await adapter.generate(_prompt())
    assert _is_billing(raised.value)


@pytest.mark.asyncio
async def test_groq_generate_raises_billing_on_402():
    adapter = groq_adapter.GroqAdapter()
    adapter._client = MagicMock()
    adapter._client.chat.completions.create = AsyncMock(side_effect=_groq_status_error(402))
    with pytest.raises(LLMError) as raised:
        await adapter.generate(_prompt())
    assert _is_billing(raised.value)


@pytest.mark.asyncio
async def test_deepseek_generate_still_raises_billing_on_402():
    client = MagicMock()
    client.post = AsyncMock(return_value=httpx.Response(402, json={}))
    adapter = DeepSeekAdapter(http_client=client)
    with pytest.raises(LLMError) as raised:
        await adapter.generate(_prompt())
    assert _is_billing(raised.value)
