"""BPE Tokenizer-based precise token estimation for Vietnamese + JSON prompt budgeting."""

from typing import Optional, List, Dict

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False


class TokenEstimator:
    """
    Sync token estimator for prompt budget enforcement.
    Uses tiktoken cl100k_base BPE encoding with fallback to character heuristic.
    """

    CHARS_PER_TOKEN = 2
    _encoder: Optional[object] = None

    @classmethod
    def _get_encoder(cls):
        if not _TIKTOKEN_AVAILABLE:
            return None
        if cls._encoder is None:
            try:
                cls._encoder = tiktoken.get_encoding("cl100k_base")
            except Exception:
                cls._encoder = None
        return cls._encoder

    @classmethod
    def estimate(cls, text: str) -> int:
        if not text:
            return 0
        encoder = cls._get_encoder()
        if encoder:
            try:
                return len(encoder.encode(text))
            except Exception:
                pass
        return len(text) // cls.CHARS_PER_TOKEN

    @classmethod
    def trim_to_budget(cls, text: str, max_tokens: int, suffix: str = "...") -> str:
        if max_tokens <= 0:
            return ""
        if cls.estimate(text) <= max_tokens:
            return text

        encoder = cls._get_encoder()
        if encoder:
            try:
                tokens = encoder.encode(text)
                suffix_tokens = encoder.encode(suffix)
                budget_for_text = max_tokens - len(suffix_tokens)
                if budget_for_text <= 0:
                    return suffix
                trimmed_tokens = tokens[:budget_for_text]
                return encoder.decode(trimmed_tokens) + suffix
            except Exception:
                pass

        max_chars = max_tokens * cls.CHARS_PER_TOKEN
        suffix_chars = len(suffix)
        if max_chars <= suffix_chars:
            return suffix[:max_chars]
        return text[: max_chars - suffix_chars] + suffix

    @classmethod
    def estimate_messages(cls, messages: List[Dict[str, str]], overhead_per_msg: int = 4) -> int:
        total = 0
        for msg in messages:
            total += cls.estimate(msg.get("content", "")) + overhead_per_msg
        return total
