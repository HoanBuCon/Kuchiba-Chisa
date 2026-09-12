"""Read a versioned, authorization-bound final lore answer cache entry."""

from __future__ import annotations

from collections.abc import Callable
from time import time

from pydantic import ValidationError

from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.lore_corpus_identity import ILoreCorpusIdentityProvider
from app.domain.interfaces.observability import (
    CounterSignal,
    IOperationalTelemetry,
    NoopOperationalTelemetry,
    TelemetryDimensions,
)
from app.domain.interfaces.tracker import IPipelineTracker
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.guardrails.injection_guard import GuardAction
from app.domain.services.lore_answer_cache import (
    LoreAnswerCacheContract,
    LoreAnswerCacheEntry,
)
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class CacheStage(PipelineStage):
    """Use only current-format answers whose version and ACL receipt still match."""

    def __init__(
        self,
        cache: ICacheProvider,
        corpus_identity_provider: ILoreCorpusIdentityProvider,
        contract: LoreAnswerCacheContract,
        pipeline_tracker: IPipelineTracker | None = None,
        clock: Callable[[], float] = time,
        telemetry: IOperationalTelemetry | None = None,
    ) -> None:
        self.cache = cache
        self.corpus_identity_provider = corpus_identity_provider
        self.contract = contract
        self.pipeline_tracker = pipeline_tracker
        self.clock = clock
        self.telemetry = telemetry or NoopOperationalTelemetry()

    async def process(self, context: ChatContext) -> ChatContext:
        if (
            context.guardrail_assessment
            and context.guardrail_assessment.action is GuardAction.BLOCK
        ):
            return context
        if not self.contract.request_is_eligible(context):
            return self._track(context, "bypass")

        try:
            corpus = await self.corpus_identity_provider.active_lore_corpus_identity()
        except Exception as error:
            log.warning("Lore cache corpus identity unavailable", error_type=type(error).__name__)
            return self._track(context, "unavailable")
        if corpus is None:
            return self._track(context, "corpus_unavailable")

        identity = self.contract.identity(context, corpus)
        context.lore_cache_identity = identity
        try:
            raw = await self.cache.get(identity.key)
        except Exception as error:
            log.warning("Lore answer cache read unavailable", error_type=type(error).__name__)
            return self._track(context, "unavailable")
        if raw is None:
            return self._track(context, "miss")
        try:
            entry = LoreAnswerCacheEntry.model_validate_json(raw)
        except (ValidationError, ValueError, TypeError):
            return self._track(context, "malformed")

        outcome = self.contract.validate_entry(entry, identity, context, now=self.clock())
        if outcome != "hit":
            return self._track(context, outcome)

        context.is_cached_answer = True
        context.chisa_reply = entry.answer
        context.citation_ids = [citation.evidence_id for citation in entry.citations]
        context.tool_res = {
            "grounding": {"status": "verified", "source": "validated_cache_receipt"},
            "cache": {"schema_version": entry.schema_version, "outcome": "hit"},
        }
        log.info("Lore answer cache hit", cache_identity=identity.digest[:12])
        return self._track(context, "hit")

    def _track(self, context: ChatContext, outcome: str) -> ChatContext:
        context.lore_cache_outcome = outcome
        self.telemetry.count(
            CounterSignal.CACHE_OPERATIONS,
            TelemetryDimensions(cache_outcome=outcome, status="read"),
        )
        if self.pipeline_tracker:
            self.pipeline_tracker.add_step(
                name="cache_check",
                stage_id="stage_3_cache",
                depth=0,
                category="stage_root",
                status="cached" if outcome == "hit" else "skipped",
                title="Stage 3: [CACHE] Versioned lore answer cache",
                subtitle=f"Cache outcome: {outcome}",
                data={
                    "hit": outcome == "hit",
                    "is_hit": outcome == "hit",
                    "outcome": outcome,
                    "cache_schema": "lore-answer-v2",
                },
            )
        return context
