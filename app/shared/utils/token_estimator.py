"""Conservative token estimation for Vietnamese + JSON prompt budgeting."""


class TokenEstimator:
    """
    Sync token estimator for prompt budget enforcement.
    Uses 2 chars/token — conservative for Vietnamese BPE on Llama/DeepSeek-class models.
    """

    CHARS_PER_TOKEN = 2

    @classmethod
    def estimate(cls, text: str) -> int:
        if not text:
            return 0
        return len(text) // cls.CHARS_PER_TOKEN

    @classmethod
    def trim_to_budget(cls, text: str, max_tokens: int, suffix: str = "...") -> str:
        if max_tokens <= 0:
            return ""
        if cls.estimate(text) <= max_tokens:
            return text
        max_chars = max_tokens * cls.CHARS_PER_TOKEN
        suffix_chars = len(suffix)
        if max_chars <= suffix_chars:
            return suffix[:max_chars]
        return text[: max_chars - suffix_chars] + suffix

    @classmethod
    def estimate_messages(cls, messages: list[dict[str, str]], overhead_per_msg: int = 10) -> int:
        total = 0
        for msg in messages:
            total += cls.estimate(msg.get("content", "")) + overhead_per_msg
        return total
