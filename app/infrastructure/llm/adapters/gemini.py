from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

from app.config.settings import settings
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.llm.adapters.base import (
    BaseLLMAdapter,
    LLMError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    LLMTokenOverflowError,
    StructuredPrompt,
)

log = get_logger(__name__)


class GeminiAdapter(BaseLLMAdapter):
    """
    Google Gemini LLM adapter.
    Implements BaseLLMAdapter interface so it can be swapped seamlessly.
    """

    _MAX_RETRIES = 3
    _BASE_BACKOFF = 0.5  # seconds

    def __init__(self) -> None:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            log.warning("GEMINI_API_KEY is not set but GeminiAdapter was initialized")
        self._client = genai.Client(api_key=api_key)
        self._model = settings.GEMINI_MODEL
        self._max_tokens = settings.GEMINI_MAX_TOKENS
        self._temperature = settings.GEMINI_TEMPERATURE

    # ── Generate (with retry) ──────────────────────────────────────
    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        """
        Sends structured prompt to Gemini with JSON mode enforced.
        """
        last_error: Exception | None = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                log.debug(
                    "Gemini generate attempt",
                    attempt=attempt,
                    model=self._model,
                )
                return await self._call_gemini(prompt)

            except LLMTokenOverflowError:
                raise  # Don't retry token overflow — it won't help

            except LLMRateLimitError as e:
                last_error = e
                wait = self._BASE_BACKOFF * (2 ** (attempt - 1))
                log.warning("Gemini rate limited, waiting", wait_seconds=wait, attempt=attempt)
                await asyncio.sleep(wait)

            except LLMTimeoutError as e:
                last_error = e
                wait = self._BASE_BACKOFF * (2 ** (attempt - 1))
                log.warning("Gemini timeout, retrying", wait_seconds=wait, attempt=attempt)
                await asyncio.sleep(wait)

            except LLMError as e:
                last_error = e
                if not e.retryable:
                    raise
                await asyncio.sleep(self._BASE_BACKOFF * attempt)

        raise last_error or LLMError("Max retries exhausted")

    async def _call_gemini(self, prompt: StructuredPrompt) -> LLMResponse:
        """Internal Gemini API call."""
        contents = []
        for msg in prompt.history:
            # Map role to Gemini-compatible roles
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        
        contents.append({"role": "user", "parts": [{"text": prompt.user_message}]})

        try:
            config = types.GenerateContentConfig(
                temperature=prompt.temperature or self._temperature,
                max_output_tokens=prompt.max_tokens or self._max_tokens,
                response_mime_type="application/json",
                system_instruction=prompt.system
            )
            
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=contents,
                config=config
            )
        except Exception as e:
            error_str = str(e).lower()
            if "timeout" in error_str:
                raise LLMTimeoutError()
            if "rate_limit" in error_str or "429" in error_str or "quota" in error_str:
                raise LLMRateLimitError()
            if "context_length" in error_str or "token limit" in error_str:
                raise LLMTokenOverflowError()
            raise LLMError(f"Gemini API error: {e}", retryable=True)

        raw = response.text or ""
        finish_reason = str(response.candidates[0].finish_reason) if response.candidates else ""

        if "MAX_TOKENS" in finish_reason:
            raise LLMTokenOverflowError()

        parsed = await self.validate_response(raw, prompt.response_schema)
        
        input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

        return LLMResponse(
            raw_content=raw,
            parsed=parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
            finish_reason=finish_reason,
        )

    # ── Stream (STUB) ──────────────────────────────────────────────
    async def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
        """STUB: Streaming support — full implementation later."""
        log.warning("GeminiAdapter.stream() is a stub — not yet implemented")
        yield ""

    # ── Validate Response ──────────────────────────────────────────
    async def validate_response(self, raw: str, schema: dict[str, Any]) -> dict[str, Any]:
        """
        Parse LLM JSON response and do basic structural validation.
        """
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            log.error("LLM JSON parse failed", error=str(e), raw=raw[:200])
            raise LLMInvalidResponseError(f"JSON parse error: {e}")

        if not isinstance(parsed, dict):
            raise LLMInvalidResponseError("LLM response is not a JSON object")

        return parsed

    # ── Token Estimation ───────────────────────────────────────────
    async def estimate_tokens(self, text: str) -> int:
        """
        Rough token estimation: ~4 chars per token.
        """
        return len(text) // 4
