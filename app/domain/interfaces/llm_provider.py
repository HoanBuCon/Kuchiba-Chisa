from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel


# ─── Request / Response Schemas ───────────────────────────────────────────────

class StructuredPrompt(BaseModel):
    """Input structure passed to every LLM adapter."""
    system: str
    history: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": "..."}]
    user_message: str
    response_schema: dict[str, Any]  # JSON schema for enforced output
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    retrieved_memories: list[Any] = []
    retrieved_lore: list[str] = []
    rag_decisions: dict[str, bool] = {}


class LLMResponse(BaseModel):
    """Validated structured response from LLM adapter."""
    raw_content: str                # Raw JSON string from LLM
    parsed: dict[str, Any]          # Parsed and validated JSON
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    model: str = ""
    finish_reason: str = ""
    reasoning_content: str | None = None


class LLMError(Exception):
    """Base exception for all LLM adapter errors."""
    def __init__(self, message: str, retryable: bool = True, code: Optional[str] = None):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


class LLMTimeoutError(LLMError):
    """LLM request timed out."""
    def __init__(self) -> None:
        super().__init__("LLM request timed out", retryable=True, code="TIMEOUT")


class LLMRateLimitError(LLMError):
    """LLM provider rate limit hit."""
    def __init__(self) -> None:
        super().__init__("LLM rate limit exceeded", retryable=True, code="RATE_LIMIT")


class LLMTokenOverflowError(LLMError):
    """Prompt exceeds model context window."""
    def __init__(self) -> None:
        super().__init__("Token limit exceeded", retryable=False, code="TOKEN_OVERFLOW")


class LLMInvalidResponseError(LLMError):
    """LLM returned a response that fails JSON validation."""
    def __init__(self, details: str) -> None:
        super().__init__(f"Invalid LLM response: {details}", retryable=True, code="INVALID_JSON")


# ─── Abstract LLM Port ────────────────────────────────────────────────────────

class BaseLLMAdapter(ABC):
    """
    Port interface for all LLM providers.
    Business logic ONLY interacts with this interface.
    Concrete adapters live in /infrastructure/llm/adapters/.
    """

    @abstractmethod
    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        """
        Send a structured prompt and return a validated JSON response.
        Must enforce JSON output format.
        Must handle retry logic internally.
        Must raise LLMError subclasses on failure.
        """
        ...

    @abstractmethod
    async def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
        """
        Stream LLM response chunks (for real-time UX).
        Yields raw content deltas.
        """
        ...

    @abstractmethod
    async def validate_response(self, raw: str, schema: dict[str, Any]) -> dict[str, Any]:
        """
        Validate and parse the LLM's raw JSON string against the expected schema.
        Must raise LLMInvalidResponseError if validation fails.
        """
        ...

    @abstractmethod
    async def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for a string without making an API call.
        Used for prompt budget enforcement before submission.
        """
        ...
