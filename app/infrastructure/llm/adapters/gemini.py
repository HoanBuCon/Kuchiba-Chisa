from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types
from PIL import Image

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

GeminiPart = str | Image.Image | types.File | types.FileDict | types.Part | types.PartDict
GeminiContent = types.Content | types.ContentDict | GeminiPart | list[GeminiPart]


def _translate_gemini_error(error: Exception) -> LLMError:
    normalized = str(error).lower()
    if "timeout" in normalized:
        return LLMTimeoutError()
    if "rate_limit" in normalized or "429" in normalized or "quota" in normalized:
        return LLMRateLimitError()
    if "context_length" in normalized or "token limit" in normalized:
        return LLMTokenOverflowError()
    if any(marker in normalized for marker in ("401", "403", "api key", "unauthenticated")):
        return LLMError("Gemini authentication failed", retryable=False, code="AUTH_CONFIG")
    if any(marker in normalized for marker in ("500", "502", "503", "504")):
        return LLMError("Gemini provider unavailable", retryable=True, code="PROVIDER_5XX")
    return LLMError("Gemini transport request failed", retryable=True, code="TRANSPORT")


class GeminiAdapter(BaseLLMAdapter):
    """
    Google Gemini LLM adapter.
    Implements BaseLLMAdapter interface so it can be swapped seamlessly.
    """

    def __init__(self) -> None:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            log.warning("GEMINI_API_KEY is not set but GeminiAdapter was initialized")
        self._client = genai.Client(api_key=api_key)
        self._model = settings.GEMINI_MODEL
        self._max_tokens = settings.GEMINI_MAX_TOKENS
        self._temperature = settings.GEMINI_TEMPERATURE

    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        """Execute one provider request; retry/failover belongs to the gateway."""
        return await self._call_gemini(prompt)

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
            raise _translate_gemini_error(e) from e

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
            raise _translate_gemini_error(e) from e

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
