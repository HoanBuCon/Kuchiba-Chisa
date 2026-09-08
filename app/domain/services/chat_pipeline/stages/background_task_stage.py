"""Transactional scheduling of reliability-sensitive background work."""

from __future__ import annotations

from app.domain.interfaces.background_jobs import IDurableBackgroundJobQueue
from app.domain.interfaces.tracker import IPipelineTracker
from app.domain.models.background_job import (
    BackgroundJobSubmission,
    BackgroundJobType,
    CommunityStatePayload,
    MemoryExtractionPayload,
    PrivateSummaryPayload,
    UserStateCachePayload,
    VisualMemoryPayload,
)
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.community.topic_summarizer import CommunityTopicSummarizer
from app.domain.services.guardrails.injection_guard import GuardAction
from app.domain.services.guardrails.pii_redaction import PiiRedactor
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class BackgroundTaskStage(PipelineStage):
    """Stage 10: atomically enqueue durable jobs with the persisted chat turn."""

    def __init__(
        self,
        job_queue: IDurableBackgroundJobQueue,
        topic_summarizer: CommunityTopicSummarizer | None = None,
        pipeline_tracker: IPipelineTracker | None = None,
        pii_redactor: PiiRedactor | None = None,
    ) -> None:
        self.job_queue = job_queue
        self.topic_summarizer = topic_summarizer
        self.pipeline_tracker = pipeline_tracker
        self.pii_redactor = pii_redactor or PiiRedactor()

    async def process(self, context: ChatContext) -> ChatContext:
        if (
            context.guardrail_assessment
            and context.guardrail_assessment.action is GuardAction.BLOCK
        ):
            return context
        if context.user_uuid is None or context.conv_id is None:
            raise RuntimeError("BackgroundTaskStage requires persisted principal and conversation")

        allowed = context.memory_privacy_policy.allows_long_term_memory
        count = context.stats.interaction_count if context.stats else 0
        trigger_extract = bool(allowed and count > 0 and count % 3 == 0)
        trigger_summary = bool(
            allowed and not context.is_community and count > 0 and count % 10 == 0
        )
        trigger_visual = bool(
            allowed and context.processed_images and not context.is_ephemeral_reference
        )
        trigger_topic = False

        if (trigger_extract or trigger_summary or trigger_visual) and (
            context.persisted_user_message_id is None
            or context.persisted_assistant_message_id is None
        ):
            raise RuntimeError("Durable background work requires exact persisted message IDs")
        user_message_id = context.persisted_user_message_id
        assistant_message_id = context.persisted_assistant_message_id

        if context.state_revision is None:
            raise RuntimeError("Durable cache projection requires a committed state revision")
        user_cache_payload = UserStateCachePayload(
            user_id=context.user_uuid,
            conversation_id=context.conv_id,
            state_revision=context.state_revision,
        )
        await self._enqueue(
            context,
            BackgroundJobType.USER_STATE_CACHE,
            f"user-state-cache:{context.user_uuid}:{context.state_revision}",
            user_cache_payload.as_json(),
            tenant_id=None,
        )

        expiry = context.memory_privacy_policy.retention_expiry_epoch()
        if trigger_extract:
            if user_message_id is None or assistant_message_id is None:
                raise RuntimeError("Memory extraction requires persisted message IDs")
            memory_payload = MemoryExtractionPayload(
                user_id=context.user_uuid,
                conversation_id=context.conv_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                guild_id=context.guild_id,
                channel_id=context.channel_id,
                speaker_name=_redact_optional(self.pii_redactor, context.speaker_name),
                is_community=context.is_community,
                trace_id=context.trace_id,
                retention_expires_at=expiry,
            )
            await self._enqueue(
                context,
                BackgroundJobType.MEMORY_EXTRACTION,
            f"memory-extraction:{assistant_message_id}",
            memory_payload.as_json(),
            tenant_id=context.guild_id if context.is_community else None,
            )

        if trigger_summary:
            if assistant_message_id is None:
                raise RuntimeError("Private summary requires persisted assistant message ID")
            summary_payload = PrivateSummaryPayload(
                user_id=context.user_uuid,
                conversation_id=context.conv_id,
                source_revision=context.state_revision,
            )
            await self._enqueue(
                context,
                BackgroundJobType.PRIVATE_SUMMARY,
                f"private-summary:{assistant_message_id}",
                summary_payload.as_json(),
                tenant_id=None,
            )

        if (
            allowed
            and context.is_community
            and context.guild_id
            and context.channel_id
        ):
            if user_message_id is None or assistant_message_id is None:
                raise RuntimeError("Community state requires persisted message IDs")
            if context.emotion_mutation is None:
                raise RuntimeError("Community state requires an atomic emotion mutation")
            community_payload = CommunityStatePayload(
                user_id=context.user_uuid,
                conversation_id=context.conv_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                guild_id=context.guild_id,
                channel_id=context.channel_id,
                speaker_name=_redact_optional(self.pii_redactor, context.speaker_name),
                ambient_delta={
                    "joy": context.emotion_mutation.joy,
                    "sadness": context.emotion_mutation.sadness,
                    "irritation": context.emotion_mutation.irritation,
                    "shyness": context.emotion_mutation.shyness,
                    "curiosity": context.emotion_mutation.curiosity,
                    "comfort": context.emotion_mutation.comfort,
                },
                trace_id=context.trace_id,
            )
            await self._enqueue(
                context,
                BackgroundJobType.COMMUNITY_STATE,
                f"community-state:{assistant_message_id}",
                community_payload.as_json(),
                tenant_id=context.guild_id,
            )
            trigger_topic = count % 30 == 0

        if trigger_visual:
            if user_message_id is None or assistant_message_id is None:
                raise RuntimeError("Visual memory requires persisted message IDs")
            visual_payload = VisualMemoryPayload(
                user_id=context.user_uuid,
                conversation_id=context.conv_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                guild_id=context.guild_id,
                channel_id=context.channel_id,
                image_tags=tuple(
                    self.pii_redactor.redact(str(tag)).value for tag in context.image_tags
                ),
                visual_caption=_redact_optional(self.pii_redactor, context.visual_caption),
                retention_expires_at=expiry,
            )
            await self._enqueue(
                context,
                BackgroundJobType.VISUAL_MEMORY,
                f"visual-memory:{assistant_message_id}",
                visual_payload.as_json(),
                tenant_id=context.guild_id if context.is_community else None,
            )

        if self.pipeline_tracker:
            self.pipeline_tracker.add_step(
                name="background_tasks",
                stage_id="stage_10_bg",
                depth=0,
                category="stage_root",
                status="success",
                title="Stage 10: Durable Background Jobs",
                subtitle="Transactional outbox scheduling",
                data={
                    "interaction_count": count,
                    "batch_memory_extraction_triggered": trigger_extract,
                    "auto_summarization_triggered": trigger_summary,
                    "topic_summarization_triggered": trigger_topic,
                    "visual_memory_ingestion_triggered": trigger_visual,
                    "long_term_memory_allowed": allowed,
                },
            )
        log.info("ChatPipeline cycle complete", user_id=context.user_id)
        return context

    async def _enqueue(
        self,
        context: ChatContext,
        job_type: BackgroundJobType,
        idempotency_key: str,
        payload: dict[str, object],
        *,
        tenant_id: str | None,
    ) -> None:
        if context.user_uuid is None:
            raise RuntimeError("Trusted principal is required for durable enqueue")
        await self.job_queue.enqueue(
            context.session,
            BackgroundJobSubmission(
                job_type=job_type,
                idempotency_key=idempotency_key,
                payload=payload,
                principal_id=context.user_uuid,
                tenant_id=tenant_id,
            ),
        )


def _redact_optional(redactor: PiiRedactor, value: str | None) -> str | None:
    return redactor.redact(value).value if value else None
