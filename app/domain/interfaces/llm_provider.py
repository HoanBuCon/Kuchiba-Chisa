from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from time import monotonic
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.evidence import Evidence

# ─── Request / Response Schemas ───────────────────────────────────────────────

class LLMCapability(str, Enum):
    """Provider-neutral capabilities used for deterministic route eligibility."""

    TEXT = "text"
    STRUCTURED_OUTPUT = "structured_output"
    STREAMING = "streaming"
    VISION = "vision"
    TOOL_CALLING = "tool_calling"


class LLMPurpose(str, Enum):
    """Stable use-case identifiers for policy, isolation and safe telemetry."""

    UNKNOWN = "unknown"
    CHAT_RESPONSE = "chat_response"
    QUERY_REWRITE = "query_rewrite"
    CONTEXT_ASSESSMENT = "context_assessment"
    THINKING_LOOP = "thinking_loop"
    MEMORY_EXTRACTION = "memory_extraction"
    MEMORY_RECONCILIATION = "memory_reconciliation"
    PRIVATE_SUMMARY = "private_summary"
    COMMUNITY_SUMMARY = "community_summary"
    CONVERSATION_SUMMARY = "conversation_summary"


class LLMFailureClass(str, Enum):
    """Failure classes understood by retry, breaker and fallback policies."""

    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    RATE_LIMIT = "rate_limit"
    PROVIDER_5XX = "provider_5xx"
    INVALID_RESPONSE = "invalid_response"
    AUTH_CONFIG = "auth_config"
    TOKEN_OVERFLOW = "token_overflow"
    BULKHEAD_REJECTED = "bulkhead_rejected"
    CIRCUIT_OPEN = "circuit_open"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    NO_COMPATIBLE_PROVIDER = "no_compatible_provider"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class LLMCallBudget:
    """Mutable request-scoped provider-call budget shared by nested orchestration."""

    max_calls: int = 2
    used_calls: int = 0
    deadline_at: float | None = None

    @classmethod
    def with_deadline(cls, *, max_calls: int, timeout_seconds: float) -> LLMCallBudget:
        return cls(max_calls=max_calls, deadline_at=monotonic() + timeout_seconds)

    @property
    def remaining_calls(self) -> int:
        return max(0, self.max_calls - self.used_calls)

    def reserve(self) -> int | None:
        """Reserve exactly one provider execution without yielding to the event loop."""
        if self.used_calls >= self.max_calls:
            return None
        self.used_calls += 1
        return self.used_calls

    def remaining_seconds(self, *, now: float | None = None) -> float | None:
        if self.deadline_at is None:
            return None
        return max(0.0, self.deadline_at - (monotonic() if now is None else now))

    def __deepcopy__(self, memo: dict[int, object]) -> LLMCallBudget:
        """Prompt redaction copies must retain the same logical-request budget."""
        return self


class StructuredPrompt(BaseModel):
    """Input structure passed to every LLM adapter."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    system: str
    history: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": "..."}]
    user_message: str
    response_schema: dict[str, Any]  # JSON schema for enforced output
    images: list[str] = Field(default_factory=list)
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    retrieved_memories: list[Any] = Field(default_factory=list)
    retrieved_lore: list[str] = Field(default_factory=list)
    retrieved_evidence: list[Evidence] = Field(default_factory=list)
    rag_decisions: dict[str, bool] = Field(default_factory=dict)
    output_contract_name: str | None = None
    purpose: LLMPurpose = LLMPurpose.UNKNOWN
    required_capabilities: set[LLMCapability] = Field(
        default_factory=lambda: {
            LLMCapability.TEXT,
            LLMCapability.STRUCTURED_OUTPUT,
        }
    )
    model_profile: str = "default"
    remote_provider_eligible: bool = True
    call_budget: LLMCallBudget = Field(default_factory=LLMCallBudget, exclude=True)
    deadline_seconds: float | None = Field(default=None, gt=0)


class LLMResponse(BaseModel):
    """Validated structured response from LLM adapter."""
    raw_content: str                # Raw JSON string from LLM
    parsed: dict[str, Any]          # Parsed and validated JSON
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    vision_tokens: int = 0
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


class LLMGatewayError(LLMError):
    """Sanitized gateway failure carrying only typed operational metadata."""

    def __init__(
        self,
        message: str,
        *,
        failure_class: LLMFailureClass,
        retryable: bool = False,
        degraded: bool = False,
    ) -> None:
        super().__init__(message, retryable=retryable, code=failure_class.value.upper())
        self.failure_class = failure_class
        self.degraded = degraded


class LLMGatewayStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class LLMGatewayOutcome:
    """Typed terminal gateway result; provider SDK objects never cross this boundary."""

    status: LLMGatewayStatus
    response: LLMResponse | None = None
    provider: str | None = None
    model: str | None = None
    attempts: int = 0
    failure_class: LLMFailureClass | None = None
    fallback_used: bool = False


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
        Must execute at most one provider call; gateway owns retry and failover.
        Must raise LLMError subclasses on failure.
        """
        ...

    @abstractmethod
    def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
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
