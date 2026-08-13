"""
Utility for detecting fallback, error, or system retry responses.
Used to prevent caching bad/error responses in Redis.
"""

FALLBACK_PATTERNS = [
    "Chisa hơi mệt một chút",
    "Chisa đang hơi bận một chút",
    "Senpai nhắn lại sau nhé",
    "Senpai chờ em thêm lát",
    "xử lý tin nhắn trước đó",
    "Service temporarily unavailable",
    "Internal server error",
    "Empty response from LLM",
    "phản hồi bị cắt ngắn do vượt quá giới hạn",
]


def is_fallback_reply(text: str | None) -> bool:
    """
    Returns True if text is empty, None, or contains a fallback/error message pattern.
    """
    if not text or not text.strip():
        return True

    text_clean = text.strip()
    for pattern in FALLBACK_PATTERNS:
        if pattern.lower() in text_clean.lower():
            return True

    return False
