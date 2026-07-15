from dataclasses import dataclass

@dataclass(frozen=True)
class LLMTuning:
    """System tuning parameters for LLM adapters."""
    ADAPTER_MAX_RETRIES: int = 5
    ADAPTER_BASE_BACKOFF_STANDARD: float = 1.0  # DeepSeek, Groq
    ADAPTER_BASE_BACKOFF_SLOW: float = 1.5      # Gemini
