from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic

from app.domain.interfaces.llm_provider import (
    BaseLLMAdapter,
    LLMCapability,
    LLMError,
    LLMFailureClass,
    LLMGatewayError,
    LLMGatewayOutcome,
    LLMGatewayStatus,
    LLMInvalidResponseError,
    LLMPurpose,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    LLMTokenOverflowError,
    StructuredPrompt,
)
from app.domain.interfaces.observability import (
    CounterSignal,
    HistogramSignal,
    IOperationalTelemetry,
    NoopOperationalTelemetry,
    TelemetryDimensions,
    TraceOperation,
)
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class ProviderModel:
    provider: str
    model: str
    capabilities: frozenset[LLMCapability]
    purposes: frozenset[LLMPurpose]
    adapter: BaseLLMAdapter
    concurrency_limit: int
    profiles: frozenset[str] = frozenset({"default"})

    def supports(
        self,
        *,
        purpose: LLMPurpose,
        capabilities: frozenset[LLMCapability],
        model_profile: str,
    ) -> bool:
        if (
            purpose not in self.purposes
            or model_profile not in self.profiles
            or not capabilities.issubset(self.capabilities)
        ):
            return False
        return (LLMCapability.VISION in self.capabilities) == (
            LLMCapability.VISION in capabilities
        )


@dataclass(frozen=True, slots=True)
class LLMGatewayPolicy:
    primary_provider: str
    fallback_providers: tuple[str, ...] = ()
    per_attempt_timeout_seconds: float = 30.0
    first_token_timeout_seconds: float = 10.0
    request_deadline_seconds: float = 60.0
    bulkhead_wait_seconds: float = 0.25
    retry_limit: int = 1
    retry_base_seconds: float = 0.1
    retry_max_seconds: float = 1.0
    breaker_failure_threshold: int = 3
    breaker_recovery_seconds: float = 15.0


@dataclass(frozen=True, slots=True)
class _RouteKey:
    provider: str
    model: str
    purpose: LLMPurpose
    capability_profile: tuple[LLMCapability, ...]


@dataclass(slots=True)
class _Breaker:
    failure_threshold: int
    recovery_seconds: float
    state: BreakerState = BreakerState.CLOSED
    failures: int = 0
    opened_at: float = 0.0
    probe_in_flight: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def permit(self, now: float) -> bool:
        async with self.lock:
            if self.state is BreakerState.CLOSED:
                return True
            if self.state is BreakerState.OPEN:
                if now - self.opened_at < self.recovery_seconds:
                    return False
                self.state = BreakerState.HALF_OPEN
            if self.probe_in_flight:
                return False
            self.probe_in_flight = True
            return True

    async def success(self) -> None:
        async with self.lock:
            self.state = BreakerState.CLOSED
            self.failures = 0
            self.probe_in_flight = False

    async def failure(self, now: float) -> None:
        async with self.lock:
            self.failures += 1
            self.probe_in_flight = False
            if self.state is BreakerState.HALF_OPEN or self.failures >= self.failure_threshold:
                self.state = BreakerState.OPEN
                self.opened_at = now

    async def release_probe(self) -> None:
        async with self.lock:
            self.probe_in_flight = False


_BREAKER_FAILURES = {
    LLMFailureClass.TIMEOUT,
    LLMFailureClass.TRANSPORT,
    LLMFailureClass.RATE_LIMIT,
    LLMFailureClass.PROVIDER_5XX,
    LLMFailureClass.INVALID_RESPONSE,
}


class LLMGateway(BaseLLMAdapter):
    """Capability-aware provider orchestration with bounded reliability policies."""

    def __init__(
        self,
        providers: Sequence[ProviderModel],
        policy: LLMGatewayPolicy,
        *,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
        telemetry: IOperationalTelemetry | None = None,
    ) -> None:
        self._providers = tuple(providers)
        self._policy = policy
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter
        self._telemetry = telemetry or NoopOperationalTelemetry()
        self._breakers: dict[_RouteKey, _Breaker] = {}
        self._bulkheads = {
            provider.provider: asyncio.BoundedSemaphore(provider.concurrency_limit)
            for provider in self._providers
        }

    async def execute(self, prompt: StructuredPrompt) -> LLMGatewayOutcome:
        self._initialize_deadline(prompt)
        required = self._required_capabilities(prompt, streaming=False)
        candidates = self._eligible(prompt, required)
        if not candidates:
            return self._degraded(
                prompt,
                LLMFailureClass.NO_COMPATIBLE_PROVIDER,
                "No compatible LLM provider is configured",
            )

        last_failure = LLMFailureClass.UNKNOWN
        attempted_provider: str | None = None
        attempts = 0
        fallback_used = False
        candidate_index = 0
        retry_count = 0

        while candidate_index < len(candidates):
            if self._deadline_expired(prompt):
                last_failure = LLMFailureClass.DEADLINE_EXCEEDED
                break
            candidate = candidates[candidate_index]
            route_key = self._route_key(candidate, prompt, required)
            breaker = self._breaker(route_key)
            if not await breaker.permit(self._clock()):
                last_failure = LLMFailureClass.CIRCUIT_OPEN
                dimensions = self._dimensions(candidate, prompt, required)
                self._telemetry.count(CounterSignal.LLM_BREAKER_OPENS, dimensions)
                candidate_index += 1
                fallback_used = True
                self._telemetry.count(CounterSignal.LLM_FALLBACKS, dimensions)
                continue

            if prompt.call_budget.reserve() is None:
                await breaker.release_probe()
                return self._degraded(
                    prompt,
                    LLMFailureClass.BUDGET_EXHAUSTED,
                    "LLM call budget exhausted",
                    attempts=attempts,
                    fallback_used=fallback_used,
                )
            attempts += 1
            attempted_provider = candidate.provider

            try:
                response = await self._invoke(candidate, prompt)
            except asyncio.CancelledError:
                await breaker.release_probe()
                raise
            except Exception as error:
                failure = classify_llm_failure(error)
                last_failure = failure
                if failure in _BREAKER_FAILURES:
                    await breaker.failure(self._clock())
                else:
                    await breaker.release_probe()
                log.warning(
                    "LLM provider attempt failed",
                    provider=candidate.provider,
                    model=candidate.model,
                    purpose=prompt.purpose.value,
                    attempt=attempts,
                    failure_class=failure.value,
                )

                next_index = self._next_compatible_candidate(candidates, candidate_index)
                if next_index is not None:
                    candidate_index = next_index
                    fallback_used = True
                    self._telemetry.count(
                        CounterSignal.LLM_FALLBACKS,
                        self._dimensions(
                            candidate,
                            prompt,
                            required,
                            fallback_reason=failure.value,
                        ),
                    )
                    retry_count = 0
                    continue
                if self._is_retryable(failure) and retry_count < self._policy.retry_limit:
                    retry_count += 1
                    self._telemetry.count(
                        CounterSignal.LLM_RETRIES,
                        self._dimensions(candidate, prompt, required),
                    )
                    if not await self._wait_before_retry(prompt, retry_count):
                        last_failure = LLMFailureClass.DEADLINE_EXCEEDED
                        break
                    continue
                break
            else:
                await breaker.success()
                return LLMGatewayOutcome(
                    status=LLMGatewayStatus.SUCCESS,
                    response=response,
                    provider=candidate.provider,
                    model=response.model or candidate.model,
                    attempts=attempts,
                    fallback_used=fallback_used,
                )

        return self._degraded(
            prompt,
            last_failure,
            "All compatible LLM providers failed",
            provider=attempted_provider,
            attempts=attempts,
            fallback_used=fallback_used,
        )

    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        started = self._clock()
        dimensions = self._prompt_dimensions(prompt)
        with self._telemetry.span(TraceOperation.LLM_GENERATION, dimensions) as span:
            try:
                outcome = await self.execute(prompt)
                if outcome.status is LLMGatewayStatus.SUCCESS and outcome.response is not None:
                    span.set_status("ok")
                    return outcome.response
                span.set_status(
                    "degraded",
                    (outcome.failure_class or LLMFailureClass.UNKNOWN).value,
                )
                raise LLMGatewayError(
                    "LLM request unavailable",
                    failure_class=outcome.failure_class or LLMFailureClass.UNKNOWN,
                    degraded=outcome.status is LLMGatewayStatus.DEGRADED,
                )
            finally:
                self._telemetry.observe(
                    HistogramSignal.LLM_GENERATION_DURATION,
                    self._clock() - started,
                    dimensions,
                )

    async def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
        self._initialize_deadline(prompt)
        required = self._required_capabilities(prompt, streaming=True)
        candidates = self._eligible(prompt, required)
        if not candidates:
            raise LLMGatewayError(
                "No compatible streaming LLM provider is configured",
                failure_class=LLMFailureClass.NO_COMPATIBLE_PROVIDER,
                degraded=True,
            )

        last_failure = LLMFailureClass.UNKNOWN
        candidate_index = 0
        retry_count = 0
        attempts = 0
        while candidate_index < len(candidates):
            if self._deadline_expired(prompt):
                last_failure = LLMFailureClass.DEADLINE_EXCEEDED
                break
            candidate = candidates[candidate_index]
            dimensions = self._dimensions(candidate, prompt, required)
            breaker = self._breaker(
                self._route_key(candidate, prompt, required)
            )
            if not await breaker.permit(self._clock()):
                last_failure = LLMFailureClass.CIRCUIT_OPEN
                self._telemetry.count(CounterSignal.LLM_BREAKER_OPENS, dimensions)
                candidate_index += 1
                self._telemetry.count(
                    CounterSignal.LLM_FALLBACKS,
                    TelemetryDimensions(
                        provider=candidate.provider,
                        model_profile=prompt.model_profile,
                        purpose=prompt.purpose.value,
                        capability_profile=dimensions.capability_profile,
                        fallback_reason="circuit_open",
                    ),
                )
                continue
            if prompt.call_budget.reserve() is None:
                await breaker.release_probe()
                self._telemetry.count(CounterSignal.LLM_BUDGET_EXHAUSTED, dimensions)
                raise LLMGatewayError(
                    "LLM call budget exhausted",
                    failure_class=LLMFailureClass.BUDGET_EXHAUSTED,
                    degraded=True,
                )
            attempts += 1
            acquired = False
            emitted = False
            provider_started: float | None = None
            provider_span_context = None
            provider_span = None
            try:
                bulkhead_started = self._clock()
                acquired = await self._acquire_bulkhead(candidate, prompt)
                self._telemetry.observe(
                    HistogramSignal.LLM_BULKHEAD_WAIT,
                    self._clock() - bulkhead_started,
                    dimensions,
                )
                if not acquired:
                    self._telemetry.count(
                        CounterSignal.LLM_BULKHEAD_REJECTIONS, dimensions
                    )
                    raise LLMGatewayError(
                        "LLM provider concurrency budget exhausted",
                        failure_class=LLMFailureClass.BULKHEAD_REJECTED,
                    )
                provider_started = self._clock()
                provider_span_context = self._telemetry.span(
                    TraceOperation.LLM_PROVIDER, dimensions
                )
                provider_span = provider_span_context.__enter__()
                self._telemetry.count(CounterSignal.LLM_PROVIDER_CALLS, dimensions)
                iterator = candidate.adapter.stream(prompt).__aiter__()
                total_timeout = self._phase_timeout(
                    prompt, self._policy.per_attempt_timeout_seconds
                )
                async with asyncio.timeout(total_timeout):
                    first = await asyncio.wait_for(
                        iterator.__anext__(),
                        timeout=self._phase_timeout(
                            prompt, self._policy.first_token_timeout_seconds
                        ),
                    )
                    self._telemetry.observe(
                        HistogramSignal.LLM_TTFT,
                        self._clock() - provider_started,
                        dimensions,
                    )
                    emitted = True
                    yield first
                    async for chunk in iterator:
                        yield chunk
                await breaker.success()
                provider_span.set_status("ok")
                return
            except StopAsyncIteration:
                await breaker.success()
                if provider_span is not None:
                    provider_span.set_status("ok")
                return
            except asyncio.CancelledError:
                await breaker.release_probe()
                if provider_span is not None:
                    provider_span.set_status("cancelled", "client_cancelled")
                raise
            except Exception as error:
                last_failure = classify_llm_failure(error)
                failed_dimensions = self._dimensions(
                    candidate,
                    prompt,
                    required,
                    failure_class=last_failure.value,
                )
                if provider_started is not None:
                    self._telemetry.count(
                        CounterSignal.LLM_PROVIDER_ERRORS, failed_dimensions
                    )
                if provider_span is not None:
                    provider_span.set_status("error", last_failure.value)
                if last_failure in _BREAKER_FAILURES:
                    await breaker.failure(self._clock())
                else:
                    await breaker.release_probe()
                log.warning(
                    "LLM streaming provider failed",
                    provider=candidate.provider,
                    model=candidate.model,
                    purpose=prompt.purpose.value,
                    attempt=attempts,
                    failure_class=last_failure.value,
                )
                if emitted:
                    raise LLMGatewayError(
                        "LLM stream failed after output began",
                        failure_class=last_failure,
                        degraded=True,
                    ) from error
                next_index = self._next_compatible_candidate(
                    candidates, candidate_index
                )
                if next_index is not None:
                    candidate_index = next_index
                    self._telemetry.count(
                        CounterSignal.LLM_FALLBACKS,
                        TelemetryDimensions(
                            provider=candidate.provider,
                            model_profile=prompt.model_profile,
                            purpose=prompt.purpose.value,
                            capability_profile=dimensions.capability_profile,
                            fallback_reason=last_failure.value,
                        ),
                    )
                    retry_count = 0
                    continue
                if (
                    self._is_retryable(last_failure)
                    and retry_count < self._policy.retry_limit
                ):
                    retry_count += 1
                    self._telemetry.count(CounterSignal.LLM_RETRIES, dimensions)
                    if await self._wait_before_retry(prompt, retry_count):
                        continue
                    last_failure = LLMFailureClass.DEADLINE_EXCEEDED
                break
            finally:
                if provider_started is not None:
                    self._telemetry.observe(
                        HistogramSignal.LLM_PROVIDER_DURATION,
                        self._clock() - provider_started,
                        dimensions,
                    )
                if provider_span_context is not None:
                    provider_span_context.__exit__(None, None, None)
                if acquired:
                    self._bulkheads[candidate.provider].release()

        self._telemetry.count(
            CounterSignal.LLM_DEGRADED,
            TelemetryDimensions(
                model_profile=prompt.model_profile,
                purpose=prompt.purpose.value,
                failure_class=last_failure.value,
            ),
        )
        raise LLMGatewayError(
            "All compatible streaming LLM providers failed",
            failure_class=last_failure,
            degraded=True,
        )

    async def validate_response(self, raw: str, schema: dict[str, object]) -> dict[str, object]:
        candidates = self._providers_for_order()
        if not candidates:
            raise LLMGatewayError(
                "No LLM provider is configured",
                failure_class=LLMFailureClass.NO_COMPATIBLE_PROVIDER,
            )
        return await candidates[0].adapter.validate_response(raw, schema)

    async def estimate_tokens(self, text: str) -> int:
        candidates = self._providers_for_order()
        if not candidates:
            return max(1, len(text) // 4)
        return await candidates[0].adapter.estimate_tokens(text)

    def breaker_state(
        self,
        provider: str,
        model: str,
        purpose: LLMPurpose,
        capabilities: frozenset[LLMCapability] | None = None,
    ) -> BreakerState:
        """Expose safe operational state for readiness/tests and future OPS-02 metrics."""
        profile = capabilities or frozenset(
            {LLMCapability.TEXT, LLMCapability.STRUCTURED_OUTPUT}
        )
        return self._breaker(
            _RouteKey(
                provider,
                model,
                purpose,
                tuple(sorted(profile, key=lambda item: item.value)),
            )
        ).state

    def _eligible(
        self, prompt: StructuredPrompt, capabilities: frozenset[LLMCapability]
    ) -> list[ProviderModel]:
        if not prompt.remote_provider_eligible:
            return []
        return [
            provider
            for provider in self._providers_for_order()
            if provider.supports(
                purpose=prompt.purpose,
                capabilities=capabilities,
                model_profile=prompt.model_profile,
            )
        ]

    def _providers_for_order(self) -> list[ProviderModel]:
        order = (self._policy.primary_provider, *self._policy.fallback_providers)
        return [
            provider
            for name in order
            for provider in self._providers
            if provider.provider == name
        ]

    @staticmethod
    def _required_capabilities(
        prompt: StructuredPrompt, *, streaming: bool
    ) -> frozenset[LLMCapability]:
        required = set(prompt.required_capabilities)
        required.add(LLMCapability.TEXT)
        if prompt.response_schema:
            required.add(LLMCapability.STRUCTURED_OUTPUT)
        if prompt.images:
            required.add(LLMCapability.VISION)
        if prompt.output_contract_name:
            required.add(LLMCapability.TOOL_CALLING)
        if streaming:
            required.add(LLMCapability.STREAMING)
        return frozenset(required)

    def _breaker(self, key: _RouteKey) -> _Breaker:
        return self._breakers.setdefault(
            key,
            _Breaker(
                failure_threshold=self._policy.breaker_failure_threshold,
                recovery_seconds=self._policy.breaker_recovery_seconds,
            ),
        )

    @staticmethod
    def _route_key(
        candidate: ProviderModel,
        prompt: StructuredPrompt,
        capabilities: frozenset[LLMCapability],
    ) -> _RouteKey:
        return _RouteKey(
            candidate.provider,
            candidate.model,
            prompt.purpose,
            tuple(sorted(capabilities, key=lambda item: item.value)),
        )

    @staticmethod
    def _dimensions(
        candidate: ProviderModel,
        prompt: StructuredPrompt,
        capabilities: frozenset[LLMCapability],
        *,
        fallback_reason: str | None = None,
        failure_class: str | None = None,
    ) -> TelemetryDimensions:
        return TelemetryDimensions(
            provider=candidate.provider,
            model_profile=prompt.model_profile,
            purpose=prompt.purpose.value,
            capability_profile="+".join(sorted(item.value for item in capabilities)),
            fallback_reason=fallback_reason,
            failure_class=failure_class,
        )

    @staticmethod
    def _prompt_dimensions(prompt: StructuredPrompt) -> TelemetryDimensions:
        return TelemetryDimensions(
            model_profile=prompt.model_profile,
            purpose=prompt.purpose.value,
        )

    async def _invoke(
        self, candidate: ProviderModel, prompt: StructuredPrompt
    ) -> LLMResponse:
        capabilities = self._required_capabilities(prompt, streaming=False)
        dimensions = self._dimensions(candidate, prompt, capabilities)
        bulkhead_started = self._clock()
        acquired = await self._acquire_bulkhead(candidate, prompt)
        self._telemetry.observe(
            HistogramSignal.LLM_BULKHEAD_WAIT,
            self._clock() - bulkhead_started,
            dimensions,
        )
        if not acquired:
            self._telemetry.count(CounterSignal.LLM_BULKHEAD_REJECTIONS, dimensions)
            raise LLMGatewayError(
                "LLM provider concurrency budget exhausted",
                failure_class=LLMFailureClass.BULKHEAD_REJECTED,
            )
        provider_started = self._clock()
        self._telemetry.count(CounterSignal.LLM_PROVIDER_CALLS, dimensions)
        try:
            with self._telemetry.span(TraceOperation.LLM_PROVIDER, dimensions) as span:
                try:
                    response = await asyncio.wait_for(
                        candidate.adapter.generate(prompt),
                        timeout=self._phase_timeout(
                            prompt, self._policy.per_attempt_timeout_seconds
                        ),
                    )
                except asyncio.CancelledError:
                    span.set_status("cancelled", "client_cancelled")
                    raise
                except Exception as error:
                    failure = classify_llm_failure(error)
                    failed_dimensions = self._dimensions(
                        candidate,
                        prompt,
                        capabilities,
                        failure_class=failure.value,
                    )
                    self._telemetry.count(
                        CounterSignal.LLM_PROVIDER_ERRORS, failed_dimensions
                    )
                    span.set_status("error", failure.value)
                    raise
                else:
                    span.set_status("ok")
                    if response.input_tokens:
                        self._telemetry.count(
                            CounterSignal.LLM_TOKENS,
                            TelemetryDimensions(
                                provider=candidate.provider,
                                model_profile=prompt.model_profile,
                                purpose=prompt.purpose.value,
                                token_type="input",
                            ),
                            response.input_tokens,
                        )
                    if response.output_tokens:
                        self._telemetry.count(
                            CounterSignal.LLM_TOKENS,
                            TelemetryDimensions(
                                provider=candidate.provider,
                                model_profile=prompt.model_profile,
                                purpose=prompt.purpose.value,
                                token_type="output",
                            ),
                            response.output_tokens,
                        )
                    return response
        finally:
            self._telemetry.observe(
                HistogramSignal.LLM_PROVIDER_DURATION,
                self._clock() - provider_started,
                dimensions,
            )
            self._bulkheads[candidate.provider].release()

    async def _acquire_bulkhead(
        self, candidate: ProviderModel, prompt: StructuredPrompt
    ) -> bool:
        wait = self._phase_timeout(prompt, self._policy.bulkhead_wait_seconds)
        if wait <= 0:
            return False
        try:
            await asyncio.wait_for(self._bulkheads[candidate.provider].acquire(), timeout=wait)
        except TimeoutError:
            return False
        return True

    def _phase_timeout(self, prompt: StructuredPrompt, configured: float) -> float:
        remaining = prompt.call_budget.remaining_seconds(now=self._clock())
        request_limit = prompt.deadline_seconds or self._policy.request_deadline_seconds
        if remaining is None:
            return min(configured, request_limit)
        return max(0.001, min(configured, request_limit, remaining))

    def _initialize_deadline(self, prompt: StructuredPrompt) -> None:
        if prompt.call_budget.deadline_at is None:
            prompt.call_budget.deadline_at = self._clock() + (
                prompt.deadline_seconds or self._policy.request_deadline_seconds
            )

    def _deadline_expired(self, prompt: StructuredPrompt) -> bool:
        remaining = prompt.call_budget.remaining_seconds(now=self._clock())
        return remaining is not None and remaining <= 0

    async def _wait_before_retry(self, prompt: StructuredPrompt, retry_count: int) -> bool:
        base = min(
            self._policy.retry_max_seconds,
            self._policy.retry_base_seconds * (2 ** (retry_count - 1)),
        )
        wait = self._jitter(0.0, base)
        remaining = prompt.call_budget.remaining_seconds(now=self._clock())
        if prompt.call_budget.remaining_calls < 1:
            return False
        if remaining is not None and remaining <= wait:
            return False
        await self._sleep(wait)
        return True

    @staticmethod
    def _next_compatible_candidate(
        candidates: Sequence[ProviderModel], current_index: int
    ) -> int | None:
        next_index = current_index + 1
        return next_index if next_index < len(candidates) else None

    @staticmethod
    def _is_retryable(failure: LLMFailureClass) -> bool:
        return failure in _BREAKER_FAILURES

    def _degraded(
        self,
        prompt: StructuredPrompt,
        failure: LLMFailureClass,
        message: str,
        *,
        provider: str | None = None,
        attempts: int = 0,
        fallback_used: bool = False,
    ) -> LLMGatewayOutcome:
        log.warning(
            message,
            provider=provider,
            purpose=prompt.purpose.value,
            failure_class=failure.value,
            attempts=attempts,
        )
        terminal_failures = {
            LLMFailureClass.AUTH_CONFIG,
            LLMFailureClass.TOKEN_OVERFLOW,
        }
        dimensions = TelemetryDimensions(
            provider=provider,
            model_profile=prompt.model_profile,
            purpose=prompt.purpose.value,
            failure_class=failure.value,
        )
        self._telemetry.count(CounterSignal.LLM_DEGRADED, dimensions)
        if failure is LLMFailureClass.BUDGET_EXHAUSTED:
            self._telemetry.count(CounterSignal.LLM_BUDGET_EXHAUSTED, dimensions)
        return LLMGatewayOutcome(
            status=(
                LLMGatewayStatus.FAILURE
                if failure in terminal_failures
                else LLMGatewayStatus.DEGRADED
            ),
            provider=provider,
            attempts=attempts,
            failure_class=failure,
            fallback_used=fallback_used,
        )


def classify_llm_failure(error: BaseException) -> LLMFailureClass:
    """Map provider-neutral adapter errors without exposing payloads or secrets."""
    if isinstance(error, LLMTimeoutError | TimeoutError | asyncio.TimeoutError):
        return LLMFailureClass.TIMEOUT
    if isinstance(error, LLMRateLimitError):
        return LLMFailureClass.RATE_LIMIT
    if isinstance(error, LLMInvalidResponseError):
        return LLMFailureClass.INVALID_RESPONSE
    if isinstance(error, LLMTokenOverflowError):
        return LLMFailureClass.TOKEN_OVERFLOW
    if isinstance(error, LLMGatewayError):
        return error.failure_class
    if isinstance(error, LLMError):
        code = (error.code or "").upper()
        if code in {"AUTH", "AUTH_CONFIG", "CONFIG", "INVALID_API_KEY"}:
            return LLMFailureClass.AUTH_CONFIG
        if code in {"PROVIDER_5XX", "SERVER_ERROR"}:
            return LLMFailureClass.PROVIDER_5XX
        if code in {"TRANSPORT", "NETWORK"}:
            return LLMFailureClass.TRANSPORT
        return LLMFailureClass.UNKNOWN if not error.retryable else LLMFailureClass.TRANSPORT
    return LLMFailureClass.UNKNOWN
