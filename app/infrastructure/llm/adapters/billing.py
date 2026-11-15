from __future__ import annotations

from app.domain.interfaces.llm_provider import LLMError

HTTP_PAYMENT_REQUIRED = 402


def billing_exhausted_error(provider: str) -> LLMError:
    """Build the terminal error the gateway classifies as LLMFailureClass.BILLING."""
    return LLMError(f"{provider} balance exhausted", retryable=False, code="BILLING")
