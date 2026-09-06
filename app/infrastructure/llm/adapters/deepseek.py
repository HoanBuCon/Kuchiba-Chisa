from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.application.security.json_schema import (
    StructuredOutputValidationError,
    validate_structured_output,
)
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


def _output_contract_tool(prompt: StructuredPrompt) -> dict[str, Any] | None:
    if not prompt.output_contract_name:
        return None
    return {
        "type": "function",
        "function": {
            "name": prompt.output_contract_name,
            "description": "Submit the final response using the required typed contract.",
            "parameters": prompt.response_schema,
        },
    }


def _extract_contract_arguments(
    message: dict[str, Any], contract_name: str
) -> str:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        raise LLMInvalidResponseError("Expected exactly one structured response tool call")
    function = tool_calls[0].get("function")
    if not isinstance(function, dict) or function.get("name") != contract_name:
        raise LLMInvalidResponseError("Unexpected structured response tool call")
    arguments = function.get("arguments")
    if not isinstance(arguments, str) or not arguments.strip():
        raise LLMInvalidResponseError("Structured response tool call has no arguments")
    return arguments


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
        if prompt.images:
            user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt.user_message}]
            for img_item in prompt.images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": img_item,
                        "detail": "high"
                    }
                })
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": prompt.system},
                *prompt.history,
                {"role": "user", "content": user_content},
            ]
            target_model = getattr(
                settings,
                "DEEPSEEK_VISION_MODEL",
                "deepseek-v4-flash-vision-exp",
            )
        else:
            messages = [
                {"role": "system", "content": prompt.system},
                *prompt.history,
                {"role": "user", "content": prompt.user_message},
            ]
            target_model = self._model

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }
        
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "max_tokens": prompt.max_tokens or self._max_tokens,
            "temperature": (
                prompt.temperature if prompt.temperature is not None else self._temperature
            ),
        }

        contract_tool = _output_contract_tool(prompt)
        if contract_tool is not None:
            payload["tools"] = [contract_tool]
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": prompt.output_contract_name},
            }
        
        requested_deep_thinking = prompt.rag_decisions.get(
            "use_deep_thinking", False
        )
        # DeepSeek rejects a forced tool_choice while thinking mode is enabled.
        # Evidence-bound output must preserve the typed contract, so thinking is
        # disabled for this call only; unrelated runtime defaults are unchanged.
        is_deep_thinking = requested_deep_thinking and contract_tool is None
        if not is_deep_thinking and contract_tool is None:
            payload["response_format"] = {"type": "json_object"}
            payload["thinking"] = {"type": "disabled"}
        else:
            payload["thinking"] = {
                "type": "enabled" if is_deep_thinking else "disabled"
            }

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
        except httpx.TimeoutException as error:
            raise LLMTimeoutError() from error
        except httpx.RequestError as e:
            raise LLMError(f"HTTP request failed: {e}", retryable=True) from e
        except json.JSONDecodeError as error:
            raise LLMInvalidResponseError("Failed to decode JSON from DeepSeek response") from error

        try:
            choice = res_json["choices"][0]
            message = choice["message"]
            if prompt.output_contract_name:
                raw = _extract_contract_arguments(
                    message, prompt.output_contract_name
                )
            else:
                raw = message.get("content", "") or ""
            reasoning_content = message.get("reasoning_content")

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
                reasoning_tokens = TokenEstimator.estimate(reasoning_content)
        except (KeyError, IndexError) as e:
            raise LLMInvalidResponseError(f"Invalid response structure: {e}") from e

        parsed = {}
        error_to_raise: Exception | None = None

        if finish_reason == "length":
            error_to_raise = LLMTokenOverflowError()
        elif finish_reason in ("content_filter", "safety"):
            error_to_raise = LLMInvalidResponseError(f"Generation interrupted by DeepSeek content filter: {finish_reason}")
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
            vision_tokens=len(prompt.images) * 384 if prompt.images else 0,
            model=target_model,
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

        contract_tool = _output_contract_tool(prompt)
        if contract_tool is not None:
            payload["tools"] = [contract_tool]
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": prompt.output_contract_name},
            }
        
        requested_deep_thinking = prompt.rag_decisions.get(
            "use_deep_thinking", False
        )
        is_deep_thinking = requested_deep_thinking and contract_tool is None
        if not is_deep_thinking and contract_tool is None:
            payload["response_format"] = {"type": "json_object"}
            payload["thinking"] = {"type": "disabled"}
        else:
            payload["thinking"] = {
                "type": "enabled" if is_deep_thinking else "disabled"
            }
        in_thinking = False
        contract_name = ""
        contract_arguments_seen = False
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

                            if prompt.output_contract_name:
                                tool_calls = delta.get("tool_calls") or []
                                for tool_call in tool_calls:
                                    function = tool_call.get("function") or {}
                                    name_fragment = function.get("name") or ""
                                    if name_fragment:
                                        contract_name += name_fragment
                                    arguments = function.get("arguments") or ""
                                    if arguments:
                                        contract_arguments_seen = True
                                        yield arguments
                                continue
                            
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
                if prompt.output_contract_name and (
                    contract_name != prompt.output_contract_name
                    or not contract_arguments_seen
                ):
                    raise LLMInvalidResponseError(
                        "Streaming structured response tool call is incomplete"
                    )
        except httpx.TimeoutException as error:
            log.error("DeepSeek streaming timed out")
            raise LLMTimeoutError() from error
        except Exception as e:
            log.error("DeepSeek streaming failed", error=str(e))
            raise LLMError(f"DeepSeek streaming failed: {e}", retryable=False) from e

    async def validate_response(self, raw: str, schema: dict[str, Any]) -> dict[str, Any]:
        from app.shared.utils.json_parser import robust_parse_json
        parsed = robust_parse_json(raw)
        if not parsed or not isinstance(parsed, dict):
            raise LLMInvalidResponseError("LLM response is not a valid JSON object")
        try:
            return validate_structured_output(parsed, schema)
        except StructuredOutputValidationError as error:
            raise LLMInvalidResponseError(str(error)) from error

    async def estimate_tokens(self, text: str) -> int:
        """Precise token count via tiktoken cl100k_base (shared TokenEstimator)."""
        from app.shared.utils.token_estimator import TokenEstimator
        return TokenEstimator.estimate(text)
