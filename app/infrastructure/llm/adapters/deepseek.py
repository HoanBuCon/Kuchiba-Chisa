from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

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


class DeepSeekAdapter(BaseLLMAdapter):
    """
    DeepSeek API adapter using direct httpx calls to avoid OpenAI-HTTPX proxies conflicts.
    """

    _MAX_RETRIES = 5
    _BASE_BACKOFF = 1.0  # seconds

    def __init__(self) -> None:
        self._api_key = settings.DEEPSEEK_API_KEY
        self._base_url = settings.DEEPSEEK_BASE_URL.rstrip('/')
        self._model = settings.DEEPSEEK_MODEL
        self._max_tokens = settings.DEEPSEEK_MAX_TOKENS
        self._temperature = settings.DEEPSEEK_TEMPERATURE
        self._timeout = settings.DEEPSEEK_TIMEOUT

    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        last_error: Exception | None = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                log.debug(
                    "DeepSeek generate attempt",
                    attempt=attempt,
                    model=self._model,
                )
                return await self._call_deepseek(prompt)

            except LLMTokenOverflowError:
                raise

            except LLMRateLimitError as e:
                last_error = e
                wait = self._BASE_BACKOFF * (2 ** (attempt - 1))
                log.warning("DeepSeek rate limited, waiting", wait_seconds=wait, attempt=attempt)
                await asyncio.sleep(wait)

            except LLMTimeoutError as e:
                last_error = e
                wait = self._BASE_BACKOFF * (2 ** (attempt - 1))
                log.warning("DeepSeek timeout, retrying", wait_seconds=wait, attempt=attempt)
                await asyncio.sleep(wait)

            except LLMError as e:
                last_error = e
                if not e.retryable:
                    raise
                await asyncio.sleep(self._BASE_BACKOFF * attempt)

        raise last_error or LLMError("Max retries exhausted")

    async def _call_deepseek(self, prompt: StructuredPrompt) -> LLMResponse:
        messages = [
            {"role": "system", "content": prompt.system},
            *prompt.history,
            {"role": "user", "content": prompt.user_message},
        ]

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }
        
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": prompt.max_tokens or self._max_tokens,
            "temperature": prompt.temperature or self._temperature,
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient(timeout=float(self._timeout)) as client:
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code == 429:
                    raise LLMRateLimitError()
                elif response.status_code == 413:
                    raise LLMError("Payload too large", retryable=False, code="PAYLOAD_TOO_LARGE")
                elif response.status_code >= 500:
                    raise LLMError(f"Server error: {response.status_code}", retryable=True)
                elif response.status_code != 200:
                    raise LLMError(f"API error: {response.status_code} - {response.text}", retryable=False)
                    
                res_json = response.json()
        except httpx.TimeoutException:
            raise LLMTimeoutError()
        except httpx.RequestError as e:
            raise LLMError(f"HTTP request failed: {e}", retryable=True)
        except json.JSONDecodeError:
            raise LLMInvalidResponseError("Failed to decode JSON from DeepSeek response")

        try:
            choice = res_json["choices"][0]
            raw = choice["message"]["content"] or ""
            finish_reason = choice.get("finish_reason", "")
            
            usage = res_json.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
        except (KeyError, IndexError) as e:
            raise LLMInvalidResponseError(f"Invalid response structure: {e}")

        if finish_reason == "length":
            raise LLMTokenOverflowError()

        parsed = await self.validate_response(raw, prompt.response_schema)

        llm_response = LLMResponse(
            raw_content=raw,
            parsed=parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
            finish_reason=finish_reason,
        )

        try:
            from app.infrastructure.logging.llm_logger import log_llm_transaction
            await log_llm_transaction(prompt, llm_response)
        except Exception as e:
            log.warning("Failed to log transaction", error=str(e))

        return llm_response

    async def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
        """
        Streams response chunks from DeepSeek API.
        """
        messages = [
            {"role": "system", "content": prompt.system},
            *prompt.history,
            {"role": "user", "content": prompt.user_message},
        ]
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": prompt.max_tokens or self._max_tokens,
            "temperature": prompt.temperature or self._temperature,
            "response_format": {"type": "json_object"},
            "stream": True
        }
        try:
            async with httpx.AsyncClient(timeout=float(self._timeout)) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        log.error("DeepSeek stream failed", status_code=response.status_code)
                        yield ""
                        return
                    
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_str)
                                content = chunk_json["choices"][0]["delta"].get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                continue
        except Exception as e:
            log.error("DeepSeek streaming failed", error=str(e))
            yield ""

    async def validate_response(self, raw: str, schema: dict[str, Any]) -> dict[str, Any]:
        raw_cleaned = raw.strip()
        try:
            parsed = json.loads(raw_cleaned)
        except json.JSONDecodeError:
            try:
                start = raw_cleaned.find('{')
                end = raw_cleaned.rfind('}')
                if start != -1 and end != -1 and end > start:
                    candidate = raw_cleaned[start:end+1]
                    parsed = json.loads(candidate)
                else:
                    raise LLMInvalidResponseError("No JSON object found in response")
            except json.JSONDecodeError as e:
                log.error("LLM JSON parse failed", error=str(e), raw=raw[:200])
                raise LLMInvalidResponseError(f"JSON parse error: {e}")

        if not isinstance(parsed, dict):
            raise LLMInvalidResponseError("LLM response is not a JSON object")

        return parsed

    async def estimate_tokens(self, text: str) -> int:
        return len(text) // 4
