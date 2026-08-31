from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

from groq import AsyncGroq
from groq.types.chat import ChatCompletionMessageParam

from app.config.settings import settings
from app.config.tuning.llm import LLMTuning
from app.domain.interfaces.llm_provider import (
    BaseLLMAdapter,
    LLMError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    LLMTokenOverflowError,
    StructuredPrompt,
)
from app.infrastructure.logging.logger import get_logger

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

    _MAX_RETRIES = LLMTuning.ADAPTER_MAX_RETRIES
    _BASE_BACKOFF = LLMTuning.ADAPTER_BASE_BACKOFF_STANDARD  # seconds

    @staticmethod
    def _build_messages(prompt: StructuredPrompt) -> list[ChatCompletionMessageParam]:
        """Convert the internal prompt contract to Groq's typed message union."""
        messages: list[ChatCompletionMessageParam] = [
            cast(ChatCompletionMessageParam, {"role": "system", "content": prompt.system})
        ]
        for message in prompt.history:
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"} or not isinstance(content, str):
                raise LLMInvalidResponseError("Unsupported message in Groq conversation history")
            messages.append(cast(ChatCompletionMessageParam, {"role": role, "content": content}))
        messages.append(
            cast(ChatCompletionMessageParam, {"role": "user", "content": prompt.user_message})
        )
        return messages

    def __init__(self) -> None:
        self._client = AsyncGroq(
            api_key=settings.GROQ_API_KEY,
            timeout=settings.GROQ_TIMEOUT,
            max_retries=0,  # We handle retries manually; do not block for 18s automatically
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
        messages = self._build_messages(prompt)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=prompt.max_tokens or self._max_tokens,
                temperature=prompt.temperature if prompt.temperature is not None else self._temperature,
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
            if "413" in error_str or "payload too large" in error_str:
                # Do not retry 413 errors as sending the exact same payload again will always fail
                raise LLMError(f"Groq API error: {e}", retryable=False, code="PAYLOAD_TOO_LARGE")
            raise LLMError(f"Groq API error: {e}", retryable=True)

        raw = response.choices[0].message.content or ""
        finish_reason = response.choices[0].finish_reason or ""
        reasoning_content = getattr(response.choices[0].message, "reasoning_content", None)

        if not reasoning_content and raw:
            if "<think>" in raw and "</think>" in raw:
                s_idx = raw.find("<think>") + 7
                e_idx = raw.find("</think>")
                if e_idx > s_idx:
                    reasoning_content = raw[s_idx:e_idx].strip()

        parsed = {}
        error_to_raise: Exception | None = None

        if finish_reason == "length":
            error_to_raise = LLMTokenOverflowError()
        elif finish_reason in ("content_filter", "safety"):
            error_to_raise = LLMInvalidResponseError(f"Generation interrupted by Groq content filter: {finish_reason}")
        else:
            try:
                parsed = await self.validate_response(raw, prompt.response_schema)
            except Exception as e:
                error_to_raise = e

        llm_response = LLMResponse(
            raw_content=raw,
            parsed=parsed,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            model=self._model,
            finish_reason=finish_reason,
            reasoning_content=reasoning_content,
        )

        try:
            from app.infrastructure.logging.llm_logger import log_llm_transaction
            await log_llm_transaction(prompt, llm_response)
        except Exception as e:
            log.warning("Failed to log transaction", error=str(e))

        if error_to_raise:
            raise error_to_raise

        return llm_response

    # ── Stream ─────────────────────────────────────────────────────
    async def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
        """
        Streams structured prompt response from Groq.
        """
        messages = self._build_messages(prompt)
        try:
            response_stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=prompt.max_tokens or self._max_tokens,
                temperature=prompt.temperature if prompt.temperature is not None else self._temperature,
                response_format={"type": "json_object"},
                stream=True
            )
            async for chunk in response_stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield content
        except Exception as e:
            log.error("Groq streaming failed", error=str(e))
            raise LLMError(f"Groq streaming failed: {e}", retryable=False)

    # ── Validate Response ──────────────────────────────────────────
    async def validate_response(self, raw: str, schema: dict[str, Any]) -> dict[str, Any]:
        from app.shared.utils.json_parser import robust_parse_json
        parsed = robust_parse_json(raw)
        if not parsed or not isinstance(parsed, dict):
            raise LLMInvalidResponseError("LLM response is not a valid JSON object")
        return parsed

    # ── Token Estimation ───────────────────────────────────────────
    async def estimate_tokens(self, text: str) -> int:
        """Precise token count via tiktoken cl100k_base (shared TokenEstimator)."""
        from app.shared.utils.token_estimator import TokenEstimator
        return TokenEstimator.estimate(text)
