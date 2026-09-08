"""Provider-neutral contracts for BE-01 durable background work."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class BackgroundJobType(StrEnum):
    MEMORY_EXTRACTION = "memory_extraction.v1"
    PRIVATE_SUMMARY = "private_summary.v1"
    COMMUNITY_SUMMARY = "community_summary.v1"
    VISUAL_MEMORY = "visual_memory.v1"
    USER_STATE_CACHE = "user_state_cache.v1"
    PRIVATE_SUMMARY_CACHE = "private_summary_cache.v1"
    COMMUNITY_STATE = "community_state.v1"


class BackgroundJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"


@dataclass(frozen=True)
class BackgroundTurnSource:
    """Exact persisted turn rehydrated by a durable worker."""

    external_user_id: str
    user_message: str
    assistant_message: str
    history: list[dict[str, str]]
    media_metadata: list[dict[str, Any]]


@dataclass(frozen=True)
class MemoryExtractionPayload:
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    guild_id: str | None
    channel_id: str | None
    speaker_name: str | None
    is_community: bool
    trace_id: str | None
    retention_expires_at: int | None

    def as_json(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class PrivateSummaryPayload:
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    source_revision: int | None = None

    def as_json(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class CommunitySummaryPayload:
    user_id: uuid.UUID
    guild_id: str
    channel_id: str
    trace_id: str | None

    def as_json(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class UserStateCachePayload:
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    state_revision: int

    def as_json(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class PrivateSummaryCachePayload:
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    summary_revision: int
    source_revision: int

    def as_json(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class CommunityStatePayload:
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    guild_id: str
    channel_id: str
    speaker_name: str | None
    ambient_delta: dict[str, float]
    trace_id: str | None

    def as_json(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class VisualMemoryPayload:
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    guild_id: str | None
    channel_id: str | None
    image_tags: tuple[str, ...]
    visual_caption: str | None
    retention_expires_at: int | None

    def as_json(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class BackgroundJobSubmission:
    job_type: BackgroundJobType
    idempotency_key: str
    payload: dict[str, Any]
    principal_id: uuid.UUID
    tenant_id: str | None = None
    payload_version: int = 1
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not 8 <= len(self.idempotency_key) <= 255:
            raise ValueError("idempotency_key must contain 8..255 characters")
        if self.payload_version != 1:
            raise ValueError("unsupported background job payload version")
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        validate_persisted_payload(self.payload)


@dataclass(frozen=True)
class ClaimedBackgroundJob:
    job_id: uuid.UUID
    job_type: BackgroundJobType
    idempotency_key: str
    payload: dict[str, Any]
    payload_version: int
    principal_id: uuid.UUID
    tenant_id: str | None
    attempt_count: int
    max_attempts: int
    lease_owner: str
    lease_token: uuid.UUID
    lease_expires_at: datetime


@dataclass(frozen=True)
class BackgroundQueueSnapshot:
    """Content-free operational state suitable for metrics and alerts."""

    counts: dict[BackgroundJobStatus, int]
    oldest_ready_age_seconds: float | None
    captured_at: datetime


def validate_persisted_payload(payload: dict[str, Any]) -> None:
    """Reject secrets/protected prompt material and unbounded job payloads."""
    forbidden_key_fragments = ("secret", "password", "api_key", "system_prompt", "persona")

    def inspect(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).lower()
                if any(fragment in normalized for fragment in forbidden_key_fragments):
                    raise ValueError(f"forbidden persisted payload field: {path}{key}")
                inspect(nested, f"{path}{key}.")
        elif isinstance(value, list | tuple):
            for index, nested in enumerate(value):
                inspect(nested, f"{path}{index}.")
        elif isinstance(value, str) and len(value) > 8_192:
            raise ValueError(f"persisted payload string is too large: {path.rstrip('.')}")

    inspect(payload, "")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 32_768:
        raise ValueError("persisted background job payload exceeds 32 KiB")


def _json_ready(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_ready(item) for item in value]
    return value
