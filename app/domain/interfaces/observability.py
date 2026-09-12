"""Typed, backend-neutral operational observability contract (OPS-02)."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class TraceOperation(StrEnum):
    HTTP_REQUEST = "http.request"
    CHAT_PIPELINE = "chat.pipeline"
    PIPELINE_STAGE = "chat.pipeline.stage"
    RAG_RETRIEVAL = "rag.retrieval"
    RAG_RERANK = "rag.rerank"
    RAG_GROUNDING = "rag.grounding"
    LLM_GENERATION = "llm.generation"
    LLM_PROVIDER = "llm.provider"
    WORKER_JOB = "worker.job"
    DEPENDENCY_CHECK = "dependency.check"


class CounterSignal(StrEnum):
    HTTP_REQUESTS = "chisa.http.requests"
    HTTP_ERRORS = "chisa.http.errors"
    SSE_DISCONNECTS = "chisa.http.sse.disconnects"
    RAG_ABSTENTIONS = "chisa.rag.abstentions"
    GROUNDING_FAILURES = "chisa.rag.grounding.failures"
    RERANKER_CALLS = "chisa.rag.reranker.calls"
    RERANKER_ERRORS = "chisa.rag.reranker.errors"
    RERANKER_FALLBACKS = "chisa.rag.reranker.fallbacks"
    RERANKER_PRIVACY_REJECTIONS = "chisa.rag.reranker.privacy_rejections"
    LLM_PROVIDER_CALLS = "chisa.llm.provider.calls"
    LLM_PROVIDER_ERRORS = "chisa.llm.provider.errors"
    LLM_RETRIES = "chisa.llm.retries"
    LLM_FALLBACKS = "chisa.llm.fallbacks"
    LLM_BREAKER_OPENS = "chisa.llm.breaker.opens"
    LLM_BULKHEAD_REJECTIONS = "chisa.llm.bulkhead.rejections"
    LLM_DEGRADED = "chisa.llm.degraded"
    LLM_BUDGET_EXHAUSTED = "chisa.llm.budget.exhausted"
    LLM_TOKENS = "chisa.llm.tokens"
    CACHE_OPERATIONS = "chisa.cache.operations"
    WORKER_JOBS = "chisa.worker.jobs"
    WORKER_RETRIES = "chisa.worker.retries"
    WORKER_FAILURES = "chisa.worker.failures"
    WORKER_DLQ = "chisa.worker.dlq"
    WORKER_REPLAYS = "chisa.worker.replays"
    DEPENDENCY_CHECKS = "chisa.dependency.checks"
    SECURITY_EVENTS = "chisa.security.events"
    GUARDRAIL_DECISIONS = "chisa.guardrail.decisions"
    GROUNDING_DECISIONS = "chisa.rag.grounding.decisions"


class HistogramSignal(StrEnum):
    HTTP_DURATION = "chisa.http.server.duration"
    HTTP_TTFT = "chisa.http.ttft"
    CHAT_PIPELINE_DURATION = "chisa.chat.pipeline.duration"
    PIPELINE_STAGE_DURATION = "chisa.chat.pipeline.stage.duration"
    RAG_RETRIEVAL_DURATION = "chisa.rag.retrieval.duration"
    RAG_RERANKER_DURATION = "chisa.rag.reranker.duration"
    RAG_RERANKER_TOTAL_DURATION = "chisa.rag.reranker.total_duration"
    RAG_RETRIEVAL_SCORE = "chisa.rag.retrieval.score"
    RAG_GROUNDING_DURATION = "chisa.rag.grounding.duration"
    LLM_PROVIDER_DURATION = "chisa.llm.provider.duration"
    LLM_TTFT = "chisa.llm.ttft"
    LLM_GENERATION_DURATION = "chisa.llm.generation.duration"
    LLM_BULKHEAD_WAIT = "chisa.llm.bulkhead.wait"
    WORKER_JOB_DURATION = "chisa.worker.job.duration"
    DEPENDENCY_DURATION = "chisa.dependency.duration"


class GaugeSignal(StrEnum):
    HTTP_ACTIVE_REQUESTS = "chisa.http.active_requests"
    HTTP_ACTIVE_STREAMS = "chisa.http.active_streams"
    WORKER_ACTIVE = "chisa.worker.active"
    WORKER_QUEUE_DEPTH = "chisa.worker.queue.depth"
    WORKER_QUEUE_OLDEST_READY_AGE = "chisa.worker.queue.oldest_ready_age"
    DEPENDENCY_AVAILABLE = "chisa.dependency.available"


@dataclass(frozen=True, slots=True)
class TelemetryDimensions:
    route: str | None = None
    method: str | None = None
    status_class: str | None = None
    stage: str | None = None
    provider: str | None = None
    model_profile: str | None = None
    purpose: str | None = None
    capability_profile: str | None = None
    cache_outcome: str | None = None
    fallback_reason: str | None = None
    failure_class: str | None = None
    job_type: str | None = None
    dependency: str | None = None
    status: str | None = None
    token_type: str | None = None


class SpanHandle(Protocol):
    def set_dimensions(self, dimensions: TelemetryDimensions) -> None: ...

    def set_status(self, status: str, failure_class: str | None = None) -> None: ...


class IOperationalTelemetry(Protocol):
    def span(
        self, operation: TraceOperation, dimensions: TelemetryDimensions
    ) -> AbstractContextManager[SpanHandle]: ...

    def count(
        self,
        signal: CounterSignal,
        dimensions: TelemetryDimensions,
        amount: int = 1,
    ) -> None: ...

    def observe(
        self,
        signal: HistogramSignal,
        value_seconds: float,
        dimensions: TelemetryDimensions,
    ) -> None: ...

    def set_gauge(
        self,
        signal: GaugeSignal,
        value: int | float,
        dimensions: TelemetryDimensions,
    ) -> None: ...


class _NoopSpan:
    def set_dimensions(self, dimensions: TelemetryDimensions) -> None:
        return None

    def set_status(self, status: str, failure_class: str | None = None) -> None:
        return None


class NoopOperationalTelemetry:
    """Zero-cost-enough default used when OTLP export is disabled."""

    def span(
        self, operation: TraceOperation, dimensions: TelemetryDimensions
    ) -> AbstractContextManager[SpanHandle]:
        from contextlib import nullcontext

        return nullcontext(_NoopSpan())

    def count(
        self,
        signal: CounterSignal,
        dimensions: TelemetryDimensions,
        amount: int = 1,
    ) -> None:
        return None

    def observe(
        self,
        signal: HistogramSignal,
        value_seconds: float,
        dimensions: TelemetryDimensions,
    ) -> None:
        return None

    def set_gauge(
        self,
        signal: GaugeSignal,
        value: int | float,
        dimensions: TelemetryDimensions,
    ) -> None:
        return None
