from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

from groq import AsyncGroq
from groq.types.chat import ChatCompletionMessageParam

from app.application.security.json_schema import (
    StructuredOutputValidationError,
    validate_structured_output,
)
from app.config.settings import settings
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


def _translate_groq_error(error: Exception) -> LLMError:
    normalized = str(error).lower()
    if "timeout" in normalized:
        return LLMTimeoutError()
    if "rate_limit" in normalized or "429" in normalized:
        return LLMRateLimitError()
    if any(marker in normalized for marker in ("401", "403", "api key", "unauthorized")):
        return LLMError("Groq authentication failed", retryable=False, code="AUTH_CONFIG")
    if "context_length" in normalized or "token limit" in normalized:
        return LLMTokenOverflowError()
    if "413" in normalized or "payload too large" in normalized:
        return LLMError("Groq payload too large", retryable=False, code="PAYLOAD_TOO_LARGE")
    if any(marker in normalized for marker in ("500", "502", "503", "504")):
        return LLMError("Groq provider unavailable", retryable=True, code="PROVIDER_5XX")
    return LLMError("Groq transport request failed", retryable=True, code="TRANSPORT")

# ─── Groq Adapter ─────────────────────────────────────────────────────────────

class GroqAdapter(BaseLLMAdapter):
    """
    Groq LLM adapter — initial production implementation.
    Implements BaseLLMAdapter interface so Groq can be swapped
    for any other provider without touching domain/application layers.

    """

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
            max_retries=0,  # The gateway exclusively owns retries and failover.
        )
        self._model = settings.GROQ_MODEL
        self._max_tokens = settings.GROQ_MAX_TOKENS
        self._temperature = settings.GROQ_TEMPERATURE

    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        """Execute one provider request; retry/failover belongs to the gateway."""
        return await self._call_groq(prompt)

    async def _call_groq(self, prompt: StructuredPrompt) -> LLMResponse:
        """Build the request, execute one Groq call and validate its response."""
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
            raise _translate_groq_error(e) from e

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
            raise _translate_groq_error(e) from e

    # ── Validate Response ──────────────────────────────────────────
    async def validate_response(self, raw: str, schema: dict[str, Any]) -> dict[str, Any]:
        from app.shared.utils.json_parser import robust_parse_json
        parsed = robust_parse_json(raw)
        if not parsed or not isinstance(parsed, dict):
            raise LLMInvalidResponseError("LLM response is not a valid JSON object")
        try:
            return validate_structured_output(parsed, schema)
        except StructuredOutputValidationError as error:
            raise LLMInvalidResponseError(str(error)) from error

    # ── Token Estimation ───────────────────────────────────────────
    async def estimate_tokens(self, text: str) -> int:
        """Precise token count via tiktoken cl100k_base (shared TokenEstimator)."""
        from app.shared.utils.token_estimator import TokenEstimator
        return TokenEstimator.estimate(text)
