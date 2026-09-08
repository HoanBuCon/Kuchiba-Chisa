"""Concrete handlers for BE-01 reliability-sensitive jobs."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.models.background_job import (
    BackgroundJobType,
    BackgroundTurnSource,
    ClaimedBackgroundJob,
)
from app.domain.services.community.topic_summarizer import CommunityTopicSummarizer
from app.domain.services.memory_extractor import MemoryExtractor
from app.domain.services.visual_memory_ingestion import VisualMemoryIngestionWorker
from app.infrastructure.database.models.message import Message, MessageRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.privacy_preference import (
    SqlAlchemyPrivacyPreferenceRepository,
)

SessionFactory = async_sessionmaker[AsyncSession]
SummaryCallback = Callable[..., Awaitable[None]]


class DurableJobPayloadError(ValueError):
    """A persisted job payload does not satisfy its trusted typed contract."""


class BackgroundTurnSourceReader:
    """Rehydrate an exact committed turn while enforcing principal ownership."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def load(
        self,
        *,
        principal_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_message_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        history_limit: int = 10,
    ) -> BackgroundTurnSource:
        async with self._session_factory() as session:
            user = await session.scalar(select(User).where(User.id == principal_id))
            rows = (
                (
                    await session.execute(
                        select(Message).where(
                            Message.id.in_((user_message_id, assistant_message_id)),
                            Message.user_id == principal_id,
                            Message.conversation_id == conversation_id,
                            Message.is_success.is_(True),
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_id = {row.id: row for row in rows}
            user_message = by_id.get(user_message_id)
            assistant_message = by_id.get(assistant_message_id)
            if user is None or user_message is None or assistant_message is None:
                raise DurableJobPayloadError("background turn source is missing or unauthorized")
            if (
                user_message.role is not MessageRole.USER
                or assistant_message.role is not MessageRole.ASSISTANT
            ):
                raise DurableJobPayloadError("background turn source roles are invalid")

            history_rows = (
                (
                    await session.execute(
                        select(Message)
                        .where(
                            Message.user_id == principal_id,
                            Message.conversation_id == conversation_id,
                            Message.is_success.is_(True),
                            Message.created_at < user_message.created_at,
                        )
                        .order_by(Message.created_at.desc())
                        .limit(history_limit)
                    )
                )
                .scalars()
                .all()
            )
            media = user_message.media_metadata
            return BackgroundTurnSource(
                external_user_id=user.discord_id or str(user.id),
                user_message=user_message.content,
                assistant_message=assistant_message.content,
                history=[
                    {"role": row.role.value, "content": row.content}
                    for row in reversed(history_rows)
                ],
                media_metadata=[dict(item) for item in media] if isinstance(media, list) else [],
            )

    async def ensure_consent(self, principal_id: uuid.UUID) -> str:
        async with self._session_factory() as session:
            user = await session.scalar(select(User).where(User.id == principal_id))
            if user is None:
                raise DurableJobPayloadError("background principal does not exist")
            policy = await SqlAlchemyPrivacyPreferenceRepository(session).get_memory_policy(
                principal_id
            )
            if not policy.allows_long_term_memory:
                raise DurableJobPayloadError("long-term memory consent is not active")
            return user.discord_id or str(user.id)


class MemoryExtractionJobHandler:
    def __init__(self, source: BackgroundTurnSourceReader, extractor: MemoryExtractor) -> None:
        self._source = source
        self._extractor = extractor

    async def handle(self, job: ClaimedBackgroundJob) -> None:
        payload = _payload(job, BackgroundJobType.MEMORY_EXTRACTION)
        user_id = _uuid(payload, "user_id")
        _verify_scope(job, user_id, _optional_str(payload, "guild_id"))
        await self._source.ensure_consent(user_id)
        source = await self._source.load(
            principal_id=user_id,
            conversation_id=_uuid(payload, "conversation_id"),
            user_message_id=_uuid(payload, "user_message_id"),
            assistant_message_id=_uuid(payload, "assistant_message_id"),
        )
        await self._extractor.extract_and_store_batch(
            user_id=source.external_user_id,
            conversation_id=str(_uuid(payload, "conversation_id")),
            history=source.history,
            current_user_message=source.user_message,
            current_assistant_reply=source.assistant_message,
            guild_id=_optional_str(payload, "guild_id"),
            channel_id=_optional_str(payload, "channel_id"),
            speaker_name=_optional_str(payload, "speaker_name"),
            is_community=bool(payload.get("is_community", False)),
            trace_id=_optional_str(payload, "trace_id"),
            retention_expires_at=_optional_int(payload, "retention_expires_at"),
            idempotency_key=job.idempotency_key,
            propagate_errors=True,
        )


class PrivateSummaryJobHandler:
    def __init__(self, source: BackgroundTurnSourceReader, callback: SummaryCallback) -> None:
        self._source = source
        self._callback = callback

    async def handle(self, job: ClaimedBackgroundJob) -> None:
        payload = _payload(job, BackgroundJobType.PRIVATE_SUMMARY)
        user_id = _uuid(payload, "user_id")
        _verify_scope(job, user_id, None)
        external_user_id = await self._source.ensure_consent(user_id)
        await self._callback(
            external_user_id,
            str(_uuid(payload, "conversation_id")),
            propagate_errors=True,
        )


class CommunitySummaryJobHandler:
    def __init__(
        self, source: BackgroundTurnSourceReader, summarizer: CommunityTopicSummarizer
    ) -> None:
        self._source = source
        self._summarizer = summarizer

    async def handle(self, job: ClaimedBackgroundJob) -> None:
        payload = _payload(job, BackgroundJobType.COMMUNITY_SUMMARY)
        user_id = _uuid(payload, "user_id")
        guild_id = _required_str(payload, "guild_id")
        _verify_scope(job, user_id, guild_id)
        await self._source.ensure_consent(user_id)
        await self._summarizer.summarize_channel_topic(
            channel_id=_required_str(payload, "channel_id"),
            guild_id=guild_id,
            trace_id=_optional_str(payload, "trace_id"),
            propagate_errors=True,
        )


class VisualMemoryJobHandler:
    def __init__(
        self, source: BackgroundTurnSourceReader, worker: VisualMemoryIngestionWorker
    ) -> None:
        self._source = source
        self._worker = worker

    async def handle(self, job: ClaimedBackgroundJob) -> None:
        payload = _payload(job, BackgroundJobType.VISUAL_MEMORY)
        user_id = _uuid(payload, "user_id")
        _verify_scope(job, user_id, _optional_str(payload, "guild_id"))
        await self._source.ensure_consent(user_id)
        source = await self._source.load(
            principal_id=user_id,
            conversation_id=_uuid(payload, "conversation_id"),
            user_message_id=_uuid(payload, "user_message_id"),
            assistant_message_id=_uuid(payload, "assistant_message_id"),
        )
        tags = payload.get("image_tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise DurableJobPayloadError("image_tags must be a string list")
        await self._worker.ingest_image_memories(
            user_id=source.external_user_id,
            user_message=source.user_message,
            chisa_reply=source.assistant_message,
            processed_images=source.media_metadata,
            conversation_id=str(_uuid(payload, "conversation_id")),
            guild_id=_optional_str(payload, "guild_id"),
            channel_id=_optional_str(payload, "channel_id"),
            llm_image_tags=tags,
            llm_visual_caption=_optional_str(payload, "visual_caption"),
            retention_expires_at=_optional_int(payload, "retention_expires_at"),
            propagate_errors=True,
        )


def _payload(job: ClaimedBackgroundJob, expected: BackgroundJobType) -> dict[str, Any]:
    if job.job_type is not expected or job.payload_version != 1:
        raise DurableJobPayloadError("job type or payload version mismatch")
    return job.payload


def _verify_scope(job: ClaimedBackgroundJob, user_id: uuid.UUID, tenant_id: str | None) -> None:
    if user_id != job.principal_id or tenant_id != job.tenant_id:
        raise DurableJobPayloadError("job payload scope does not match trusted envelope")


def _uuid(payload: dict[str, Any], key: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload[key]))
    except (KeyError, TypeError, ValueError) as exc:
        raise DurableJobPayloadError(f"invalid {key}") from exc


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise DurableJobPayloadError(f"invalid {key}")
    return value


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise DurableJobPayloadError(f"invalid {key}")
    return value


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise DurableJobPayloadError(f"invalid {key}")
    return value
