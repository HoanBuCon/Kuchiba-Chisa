"""Content redaction for application logs (B-2 / SEC-03 / SEC-DATA-008).

Application logs are operational records, not a conversation store. Call sites
are expected to log metadata only (lengths, counts, flags, identifiers). This
processor is the defence-in-depth backstop: any structured field whose *name*
denotes user content, credentials or session material has its value replaced by
a size marker before rendering, so an accidental ``log.info(..., query=q)`` can
never write raw conversation text, passwords or OAuth material to stdout/files.

Numeric and boolean values are kept (token counts, flags). Only free-form
values (strings, mappings, sequences) are replaced.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from structlog.types import EventDict, WrappedLogger

# Field names that carry user/LLM content or authentication material.
REDACTED_FIELD_NAMES = frozenset(
    {
        "access_token",
        "answer",
        "authorization",
        "caption",
        "code",
        "code_verifier",
        "content",
        "cookie",
        "current",
        "email",
        "expanded",
        "extracted",
        "facts",
        "history",
        "id_token",
        "input",
        "memories",
        "memory",
        "message",
        "nonce",
        "output",
        "password",
        "prev_context",
        "previous_context",
        "prompt",
        "query",
        "raw",
        "raw_response",
        "raw_user_query",
        "reason",
        "refresh_token",
        "reply",
        "response",
        "rewritten_query",
        "search_query",
        "snippet",
        "snippets",
        "state",
        "summary",
        "system_prompt",
        "tags",
        "text",
        "token",
        "transcript",
        "user_input",
        "user_message",
    }
)
# Any field name containing one of these fragments is treated as secret material.
REDACTED_FIELD_FRAGMENTS = ("password", "secret", "api_key", "authorization", "cookie")


def _is_sensitive_field(name: str) -> bool:
    lowered = name.lower()
    if lowered in REDACTED_FIELD_NAMES:
        return True
    return any(fragment in lowered for fragment in REDACTED_FIELD_FRAGMENTS)


def _size_marker(value: Any) -> str:
    if isinstance(value, str | bytes):
        return f"[redacted:{len(value)} chars]"
    if isinstance(value, Mapping | Sequence):
        return f"[redacted:{len(value)} items]"
    return "[redacted]"


def redact_log_fields(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """structlog processor that replaces sensitive free-form field values."""
    for key in list(event_dict):
        if key == "event":
            continue
        value = event_dict[key]
        if value is None or isinstance(value, bool | int | float):
            continue
        if _is_sensitive_field(key):
            event_dict[key] = _size_marker(value)
    return event_dict
