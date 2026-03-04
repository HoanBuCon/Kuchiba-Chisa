from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from groq import AsyncGroq

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

# ─── Groq Adapter ─────────────────────────────────────────────────────────────

class GroqAdapter(BaseLLMAdapter):
    """
    Groq LLM adapter — initial production implementation.
    Implements BaseLLMAdapter interface so Groq can be swapped
    for any other provider without touching domain/application layers.

    Current status: STUB — full generation logic will be implemented
    in Phase 4 (Core Domain Implementation).
    """

    _MAX_RETRIES = 3
    _BASE_BACKOFF = 0.5  # seconds

    def __init__(self) -> None:
        self._client = AsyncGroq(
            api_key=settings.GROQ_API_KEY,
            timeout=settings.GROQ_TIMEOUT,
        )
        self._model = settings.GROQ_MODEL
        self._max_tokens = settings.GROQ_MAX_TOKENS
        self._temperature = settings.GROQ_TEMPERATURE

    # ── Generate (with retry) ──────────────────────────────────────
    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        """
        STUB: Sends structured prompt to Groq with JSON mode enforced.
        Full implementation in Phase 4.
        """
        last_error: Exception | None = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                log.debug(
                    "Groq generate attempt",
                    attempt=attempt,
                    model=self._model,
                )
                return await self._call_groq(prompt)

            except LLMTokenOverflowError:
                raise  # Don't retry token overflow — it won't help

            except LLMRateLimitError as e:
                last_error = e
                wait = self._BASE_BACKOFF * (2 ** (attempt - 1))
                log.warning("Groq rate limited, waiting", wait_seconds=wait, attempt=attempt)
                await asyncio.sleep(wait)

            except LLMTimeoutError as e:
                last_error = e
                wait = self._BASE_BACKOFF * (2 ** (attempt - 1))
                log.warning("Groq timeout, retrying", wait_seconds=wait, attempt=attempt)
                await asyncio.sleep(wait)

            except LLMError as e:
                last_error = e
                if not e.retryable:
                    raise
                await asyncio.sleep(self._BASE_BACKOFF * attempt)

        raise last_error or LLMError("Max retries exhausted")

    async def _call_groq(self, prompt: StructuredPrompt) -> LLMResponse:
        """Internal Groq API call — STUB implementation."""
        # TODO (Phase 4): Build full message list, call Groq, validate JSON
        messages = [
            {"role": "system", "content": prompt.system},
            *prompt.history,
            {"role": "user", "content": prompt.user_message},
        ]

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=prompt.max_tokens or self._max_tokens,
                temperature=prompt.temperature or self._temperature,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            error_str = str(e).lower()
            if "timeout" in error_str:
                raise LLMTimeoutError()
            if "rate_limit" in error_str or "429" in error_str:
                raise LLMRateLimitError()
            if "context_length" in error_str or "token" in error_str:
                raise LLMTokenOverflowError()
            raise LLMError(f"Groq API error: {e}", retryable=True)

        raw = response.choices[0].message.content or ""
        finish_reason = response.choices[0].finish_reason or ""

        if finish_reason == "length":
            raise LLMTokenOverflowError()

        parsed = await self.validate_response(raw, prompt.response_schema)

        return LLMResponse(
            raw_content=raw,
            parsed=parsed,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            model=self._model,
            finish_reason=finish_reason,
        )

    # ── Stream (STUB) ──────────────────────────────────────────────
    async def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
        """STUB: Streaming support — full implementation in Phase 4."""
        log.warning("GroqAdapter.stream() is a stub — not yet implemented")
        yield ""

    # ── Validate Response ──────────────────────────────────────────
    async def validate_response(self, raw: str, schema: dict[str, Any]) -> dict[str, Any]:
        """
        Parse LLM JSON response and do basic structural validation.
        TODO (Phase 4): Add full Pydantic schema validation against schema arg.
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
        TODO (Phase 4): Use tiktoken for accurate counting.
        """
        return len(text) // 4
