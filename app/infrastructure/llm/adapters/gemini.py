from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types
from PIL import Image

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

GeminiPart = str | Image.Image | types.File | types.FileDict | types.Part | types.PartDict
GeminiContent = types.Content | types.ContentDict | GeminiPart | list[GeminiPart]


class GeminiAdapter(BaseLLMAdapter):
    """
    Google Gemini LLM adapter.
    Implements BaseLLMAdapter interface so it can be swapped seamlessly.
    """

    _MAX_RETRIES = LLMTuning.ADAPTER_MAX_RETRIES
    _BASE_BACKOFF = LLMTuning.ADAPTER_BASE_BACKOFF_SLOW  # seconds

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
        contents: list[GeminiContent] = []
        for msg in prompt.history:
            # Map role to Gemini-compatible roles
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
        
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt.user_message)]))

        safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
        ]

        try:
            config = types.GenerateContentConfig(
                temperature=prompt.temperature if prompt.temperature is not None else self._temperature,
                max_output_tokens=prompt.max_tokens or self._max_tokens,
                response_mime_type="application/json",
                system_instruction=prompt.system,
                safety_settings=safety_settings,
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

        reasoning_content = None
        if "<think>" in raw and "</think>" in raw:
            s_idx = raw.find("<think>") + 7
            e_idx = raw.find("</think>")
            if e_idx > s_idx:
                reasoning_content = raw[s_idx:e_idx].strip()

        parsed = {}
        error_to_raise: Exception | None = None

        if "MAX_TOKENS" in finish_reason:
            error_to_raise = LLMTokenOverflowError()
        elif "SAFETY" in finish_reason or "BLOCKLIST" in finish_reason:
            error_to_raise = LLMInvalidResponseError(f"Generation interrupted by safety filter: {finish_reason}")
        else:
            try:
                parsed = await self.validate_response(raw, prompt.response_schema)
            except Exception as e:
                error_to_raise = e

        input_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        output_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

        llm_response = LLMResponse(
            raw_content=raw,
            parsed=parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
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
        Streams structured prompt response from Gemini.
        """
        contents: list[GeminiContent] = []
        for msg in prompt.history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
        
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt.user_message)]))

        safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            ),
        ]

        try:
            config = types.GenerateContentConfig(
                temperature=prompt.temperature if prompt.temperature is not None else self._temperature,
                max_output_tokens=prompt.max_tokens or self._max_tokens,
                response_mime_type="application/json",
                system_instruction=prompt.system,
                safety_settings=safety_settings,
            )
            
            response_stream = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=contents,
                config=config
            )
            async for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            log.error("Gemini streaming failed", error=str(e))
            raise LLMError(f"Gemini streaming failed: {e}", retryable=False)

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
