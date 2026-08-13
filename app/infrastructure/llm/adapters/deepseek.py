from __future__ import annotations
import asyncio
import json
from typing import Any, AsyncIterator
import httpx
from app.config.settings import settings
from app.config.tuning.llm import LLMTuning
from app.infrastructure.logging.logger import get_logger
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

log = get_logger(__name__)


class DeepSeekAdapter(BaseLLMAdapter):
    """
    DeepSeek API adapter using direct httpx calls to avoid OpenAI-HTTPX proxies conflicts.
    """

    _MAX_RETRIES = LLMTuning.ADAPTER_MAX_RETRIES
    _BASE_BACKOFF = LLMTuning.ADAPTER_BASE_BACKOFF_STANDARD  # seconds

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client
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
            "temperature": prompt.temperature if prompt.temperature is not None else self._temperature,
        }
        
        is_deep_thinking = prompt.rag_decisions.get("use_deep_thinking", False) if hasattr(prompt, "rag_decisions") else False
        if not is_deep_thinking:
            payload["response_format"] = {"type": "json_object"}
            payload["thinking"] = {"type": "disabled"}
        else:
            payload["thinking"] = {"type": "enabled"}

        try:
            response = await self._http_client.post(url, headers=headers, json=payload, timeout=float(self._timeout))
            
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
            raw = choice["message"].get("content", "") or ""
            reasoning_content = choice["message"].get("reasoning_content")

            if not reasoning_content and raw:
                if "<think>" in raw and "</think>" in raw:
                    s_idx = raw.find("<think>") + 7
                    e_idx = raw.find("</think>")
                    if e_idx > s_idx:
                        reasoning_content = raw[s_idx:e_idx].strip()

            finish_reason = choice.get("finish_reason", "")
            
            usage = res_json.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
            if not reasoning_tokens and reasoning_content:
                from app.shared.utils.token_estimator import TokenEstimator
                reasoning_tokens = TokenEstimator.estimate_tokens(reasoning_content)
        except (KeyError, IndexError) as e:
            raise LLMInvalidResponseError(f"Invalid response structure: {e}")

        parsed = {}
        error_to_raise = None

        if finish_reason == "length":
            error_to_raise = LLMTokenOverflowError()
        else:
            try:
                parsed = await self.validate_response(raw, prompt.response_schema)
            except Exception as e:
                error_to_raise = e

        llm_response = LLMResponse(
            raw_content=raw,
            parsed=parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
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
            "temperature": prompt.temperature if prompt.temperature is not None else self._temperature,
            "stream": True
        }
        
        is_deep_thinking = prompt.rag_decisions.get("use_deep_thinking", False) if hasattr(prompt, "rag_decisions") else False
        if not is_deep_thinking:
            payload["response_format"] = {"type": "json_object"}
            payload["thinking"] = {"type": "disabled"}
        else:
            payload["thinking"] = {"type": "enabled"}
        in_thinking = False
        try:
            async with self._http_client.stream("POST", url, headers=headers, json=payload, timeout=float(self._timeout)) as response:
                if response.status_code != 200:
                    log.error("DeepSeek stream failed", status_code=response.status_code)
                    yield ""
                    return
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if not data_str:
                            continue
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_json = json.loads(data_str)
                            delta = chunk_json["choices"][0]["delta"]
                            
                            reasoning = delta.get("reasoning_content", "")
                            content = delta.get("content", "")
                            
                            if reasoning:
                                if not in_thinking:
                                    in_thinking = True
                                    yield "<think>\n"
                                yield reasoning
                            
                            if content:
                                if in_thinking:
                                    in_thinking = False
                                    yield "\n</think>\n"
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as parse_ex:
                            log.warning(
                                "Failed to parse DeepSeek stream chunk",
                                chunk_preview=data_str[:200],
                                chunk_size=len(data_str),
                                error=str(parse_ex),
                                error_type=type(parse_ex).__name__,
                            )
                            continue
                if in_thinking:
                    yield "\n</think>\n"
        except httpx.TimeoutException:
            log.error("DeepSeek streaming timed out")
            raise LLMTimeoutError()
        except Exception as e:
            log.error("DeepSeek streaming failed", error=str(e))
            raise LLMError(f"DeepSeek streaming failed: {e}", retryable=False)

    async def validate_response(self, raw: str, schema: dict[str, Any]) -> dict[str, Any]:
        from app.shared.utils.json_parser import robust_parse_json
        parsed = robust_parse_json(raw)
        if not parsed or not isinstance(parsed, dict):
            raise LLMInvalidResponseError("LLM response is not a valid JSON object")
        return parsed

    async def estimate_tokens(self, text: str) -> int:
        """Precise token count via tiktoken cl100k_base (shared TokenEstimator)."""
        from app.shared.utils.token_estimator import TokenEstimator
        return TokenEstimator.estimate(text)
