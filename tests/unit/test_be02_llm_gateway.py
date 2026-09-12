from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.application.llm_gateway import (
    BreakerState,
    LLMGateway,
    LLMGatewayPolicy,
    ProviderModel,
)
from app.config.settings import settings
from app.domain.interfaces.llm_provider import (
    BaseLLMAdapter,
    LLMCallBudget,
    LLMCapability,
    LLMError,
    LLMFailureClass,
    LLMGatewayError,
    LLMGatewayStatus,
    LLMPurpose,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    StructuredPrompt,
)
from app.domain.services.rag.thinking_loop import ThinkingLoopAgent
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from app.infrastructure.llm.adapters.gemini import GeminiAdapter
from app.infrastructure.llm.adapters.groq import GroqAdapter
from app.infrastructure.llm.gateway_factory import validate_llm_configuration


class FakeAdapter(BaseLLMAdapter):
    def __init__(
        self,
        outcomes: list[LLMResponse | BaseException] | None = None,
        *,
        chunks: list[str] | None = None,
        stream_runs: list[list[str | BaseException]] | None = None,
        entered: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
    ) -> None:
        self.outcomes = list(outcomes or [_response("fake")])
        self.chunks = chunks or ["{}"]
        self.stream_runs = list(stream_runs or [])
        self.entered = entered
        self.release = release
        self.calls = 0

    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        self.calls += 1
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            await self.release.wait()
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
        self.calls += 1
        chunks = self.stream_runs.pop(0) if self.stream_runs else self.chunks
        for chunk in chunks:
            if isinstance(chunk, BaseException):
                raise chunk
            yield chunk

    async def validate_response(
        self, raw: str, schema: dict[str, object]
    ) -> dict[str, object]:
        return {}

    async def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


class HalfOpenProbeAdapter(FakeAdapter):
    def __init__(self, entered: asyncio.Event, release: asyncio.Event) -> None:
        super().__init__()
        self.entered = entered
        self.release = release

    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            raise LLMTimeoutError()
        self.entered.set()
        await self.release.wait()
        return _response("recovered")


def _response(model: str) -> LLMResponse:
    return LLMResponse(raw_content="{}", parsed={}, model=model, finish_reason="stop")


def _provider(
    name: str,
    adapter: BaseLLMAdapter,
    *,
    capabilities: set[LLMCapability] | None = None,
    model: str | None = None,
    concurrency: int = 1,
    profiles: set[str] | None = None,
) -> ProviderModel:
    return ProviderModel(
        provider=name,
        model=model or f"{name}-model",
        capabilities=frozenset(
            capabilities
            or {
                LLMCapability.TEXT,
                LLMCapability.STRUCTURED_OUTPUT,
            }
        ),
        purposes=frozenset({LLMPurpose.CHAT_RESPONSE, LLMPurpose.QUERY_REWRITE}),
        adapter=adapter,
        concurrency_limit=concurrency,
        profiles=frozenset(profiles or {"default"}),
    )


def _prompt(
    *,
    budget: LLMCallBudget | None = None,
    images: list[str] | None = None,
    output_contract_name: str | None = None,
    purpose: LLMPurpose = LLMPurpose.CHAT_RESPONSE,
    model_profile: str = "default",
) -> StructuredPrompt:
    return StructuredPrompt(
        system="protected-value",
        history=[],
        user_message="private-value",
        response_schema={"type": "object"},
        images=images or [],
        output_contract_name=output_contract_name,
        purpose=purpose,
        model_profile=model_profile,
        call_budget=budget or LLMCallBudget(max_calls=2),
    )


def _gateway(
    providers: list[ProviderModel],
    *,
    primary: str = "primary",
    fallback: tuple[str, ...] = (),
    threshold: int = 3,
    recovery: float = 15.0,
    timeout: float = 0.2,
    bulkhead_wait: float = 0.01,
    retry_limit: int = 1,
    clock=None,
) -> LLMGateway:
    policy = LLMGatewayPolicy(
        primary_provider=primary,
        fallback_providers=fallback,
        per_attempt_timeout_seconds=timeout,
        first_token_timeout_seconds=timeout,
        request_deadline_seconds=1.0,
        bulkhead_wait_seconds=bulkhead_wait,
        retry_limit=retry_limit,
        retry_base_seconds=0.0,
        retry_max_seconds=0.0,
        breaker_failure_threshold=threshold,
        breaker_recovery_seconds=recovery,
    )
    kwargs = {"clock": clock} if clock is not None else {}
    return LLMGateway(providers, policy, jitter=lambda _start, _end: 0.0, **kwargs)


@pytest.mark.asyncio
async def test_healthy_primary_succeeds_with_one_call() -> None:
    primary = FakeAdapter([_response("primary-model")])
    gateway = _gateway([_provider("primary", primary)])

    outcome = await gateway.execute(_prompt())

    assert outcome.status is LLMGatewayStatus.SUCCESS
    assert outcome.attempts == 1
    assert not outcome.fallback_used
    assert primary.calls == 1


@pytest.mark.asyncio
async def test_retryable_primary_recovers_within_two_call_budget() -> None:
    primary = FakeAdapter([LLMTimeoutError(), _response("primary-model")])
    budget = LLMCallBudget(max_calls=2)
    gateway = _gateway([_provider("primary", primary)])

    outcome = await gateway.execute(_prompt(budget=budget))

    assert outcome.status is LLMGatewayStatus.SUCCESS
    assert outcome.attempts == 2
    assert primary.calls == 2
    assert budget.used_calls == 2


@pytest.mark.asyncio
async def test_compatible_cross_provider_fallback_uses_same_candidate_contract() -> None:
    primary = FakeAdapter([LLMRateLimitError()])
    secondary = FakeAdapter([_response("secondary-model")])
    gateway = _gateway(
        [_provider("primary", primary), _provider("secondary", secondary)],
        fallback=("secondary",),
    )

    outcome = await gateway.execute(_prompt())

    assert outcome.status is LLMGatewayStatus.SUCCESS
    assert outcome.provider == "secondary"
    assert outcome.fallback_used
    assert (primary.calls, secondary.calls) == (1, 1)


@pytest.mark.asyncio
async def test_shared_budget_cannot_be_bypassed_by_nested_prompts() -> None:
    primary = FakeAdapter([_response("one"), _response("two"), _response("three")])
    gateway = _gateway([_provider("primary", primary)], retry_limit=0)
    budget = LLMCallBudget(max_calls=2)

    first = await gateway.execute(_prompt(budget=budget))
    second = await gateway.execute(_prompt(budget=budget))
    third = await gateway.execute(_prompt(budget=budget))

    assert first.status is second.status is LLMGatewayStatus.SUCCESS
    assert third.status is LLMGatewayStatus.DEGRADED
    assert third.failure_class is LLMFailureClass.BUDGET_EXHAUSTED
    assert primary.calls == 2


@pytest.mark.asyncio
async def test_thinking_loop_preserves_last_call_for_final_generation() -> None:
    tracker = MagicMock()
    embedder = AsyncMock()
    embedder.embed_text.return_value = [0.1, 0.2, 0.3]
    lore_retriever = AsyncMock()
    lore_retriever.retrieve_lore_parent_child.return_value = []
    llm = AsyncMock()
    budget = LLMCallBudget(max_calls=2, used_calls=1)
    agent = ThinkingLoopAgent(
        pipeline_tracker=tracker,
        lore_retriever=lore_retriever,
    )

    context, steps = await agent.run(
        session=None,
        user_id="user-1",
        user_message="Tell me the supported fact",
        history=[],
        initial_context="(No context retrieved)",
        llm=llm,
        embedder=embedder,
        web_search_tool=AsyncMock(),
        initial_search_query="supported fact",
        initial_search_target="vector",
        call_budget=budget,
    )

    assert "No search results returned" in context
    assert len(steps) == 2
    assert steps[-1]["has_enough_info"] is True
    llm.generate.assert_not_awaited()
    assert budget.remaining_calls == 1


@pytest.mark.asyncio
async def test_vision_never_falls_back_to_text_only_provider() -> None:
    vision = FakeAdapter([LLMTimeoutError(), LLMTimeoutError()])
    text = FakeAdapter([_response("text-model")])
    gateway = _gateway(
        [
            _provider(
                "primary",
                vision,
                capabilities={
                    LLMCapability.TEXT,
                    LLMCapability.STRUCTURED_OUTPUT,
                    LLMCapability.VISION,
                },
            ),
            _provider("secondary", text),
        ],
        fallback=("secondary",),
    )

    outcome = await gateway.execute(_prompt(images=["data:image/png;base64,AA=="]))

    assert outcome.status is LLMGatewayStatus.DEGRADED
    assert outcome.failure_class is LLMFailureClass.TIMEOUT
    assert vision.calls == 2
    assert text.calls == 0


@pytest.mark.asyncio
async def test_tool_request_rejects_provider_without_tool_capability() -> None:
    text = FakeAdapter()
    gateway = _gateway([_provider("primary", text)])

    outcome = await gateway.execute(_prompt(output_contract_name="submit_answer"))

    assert outcome.status is LLMGatewayStatus.DEGRADED
    assert outcome.failure_class is LLMFailureClass.NO_COMPATIBLE_PROVIDER
    assert text.calls == 0


@pytest.mark.asyncio
async def test_remote_ineligible_request_fails_closed_before_provider_call() -> None:
    provider = FakeAdapter()
    gateway = _gateway([_provider("primary", provider)])
    prompt = _prompt()
    prompt.remote_provider_eligible = False

    outcome = await gateway.execute(prompt)

    assert outcome.status is LLMGatewayStatus.DEGRADED
    assert outcome.failure_class is LLMFailureClass.NO_COMPATIBLE_PROVIDER
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_structured_request_skips_text_only_provider() -> None:
    text_only = FakeAdapter()
    structured = FakeAdapter([_response("structured-model")])
    gateway = _gateway(
        [
            _provider(
                "primary",
                text_only,
                capabilities={LLMCapability.TEXT},
            ),
            _provider("secondary", structured),
        ],
        fallback=("secondary",),
    )

    outcome = await gateway.execute(_prompt())

    assert outcome.provider == "secondary"
    assert text_only.calls == 0
    assert structured.calls == 1


@pytest.mark.asyncio
async def test_remote_ineligible_request_fails_closed_without_provider_call() -> None:
    provider = FakeAdapter()
    gateway = _gateway([_provider("primary", provider)])
    prompt = _prompt()
    prompt.remote_provider_eligible = False

    outcome = await gateway.execute(prompt)

    assert outcome.status is LLMGatewayStatus.DEGRADED
    assert outcome.failure_class is LLMFailureClass.NO_COMPATIBLE_PROVIDER
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_model_profile_is_part_of_deterministic_eligibility() -> None:
    primary = FakeAdapter()
    secondary = FakeAdapter([_response("quality-model")])
    gateway = _gateway(
        [
            _provider("primary", primary, profiles={"fast"}),
            _provider("secondary", secondary, profiles={"quality"}),
        ],
        fallback=("secondary",),
    )

    outcome = await gateway.execute(_prompt(model_profile="quality"))

    assert outcome.status is LLMGatewayStatus.SUCCESS
    assert outcome.provider == "secondary"
    assert primary.calls == 0


@pytest.mark.asyncio
async def test_breaker_state_accessor_isolated_between_models_of_same_provider() -> None:
    fast = FakeAdapter([LLMTimeoutError()])
    quality = FakeAdapter([_response("quality-model")])
    gateway = _gateway(
        [
            _provider(
                "primary",
                fast,
                model="fast-model",
                profiles={"fast"},
            ),
            _provider(
                "primary",
                quality,
                model="quality-model",
                profiles={"quality"},
            ),
        ],
        threshold=1,
    )

    failed = await gateway.execute(_prompt(model_profile="fast"))
    succeeded = await gateway.execute(_prompt(model_profile="quality"))

    assert failed.status is LLMGatewayStatus.DEGRADED
    assert succeeded.provider == "primary"
    assert succeeded.model == "quality-model"
    assert gateway.breaker_state(
        "primary", "fast-model", LLMPurpose.CHAT_RESPONSE
    ) is BreakerState.OPEN
    assert gateway.breaker_state(
        "primary", "quality-model", LLMPurpose.CHAT_RESPONSE
    ) is BreakerState.CLOSED


@pytest.mark.asyncio
async def test_breaker_state_isolated_between_capability_profiles() -> None:
    vision = FakeAdapter([LLMTimeoutError()])
    text = FakeAdapter([_response("shared-model")])
    text_capabilities = {
        LLMCapability.TEXT,
        LLMCapability.STRUCTURED_OUTPUT,
    }
    vision_capabilities = {
        *text_capabilities,
        LLMCapability.VISION,
    }
    gateway = _gateway(
        [
            _provider(
                "primary",
                text,
                model="shared-model",
                capabilities=text_capabilities,
            ),
            _provider(
                "primary",
                vision,
                model="shared-model",
                capabilities=vision_capabilities,
            ),
        ],
        threshold=1,
    )

    failed_vision = await gateway.execute(
        _prompt(images=["data:image/png;base64,AA=="])
    )
    healthy_text = await gateway.execute(_prompt())

    assert failed_vision.status is LLMGatewayStatus.DEGRADED
    assert healthy_text.status is LLMGatewayStatus.SUCCESS
    assert gateway.breaker_state(
        "primary",
        "shared-model",
        LLMPurpose.CHAT_RESPONSE,
        frozenset(vision_capabilities),
    ) is BreakerState.OPEN
    assert gateway.breaker_state(
        "primary",
        "shared-model",
        LLMPurpose.CHAT_RESPONSE,
        frozenset(text_capabilities),
    ) is BreakerState.CLOSED


@pytest.mark.asyncio
async def test_structured_output_skips_text_only_provider() -> None:
    text_only = FakeAdapter()
    structured = FakeAdapter([_response("structured-model")])
    gateway = _gateway(
        [
            _provider(
                "primary",
                text_only,
                capabilities={LLMCapability.TEXT},
            ),
            _provider("secondary", structured),
        ],
        fallback=("secondary",),
    )

    outcome = await gateway.execute(_prompt())

    assert outcome.provider == "secondary"
    assert text_only.calls == 0
    assert structured.calls == 1


@pytest.mark.asyncio
async def test_streaming_only_uses_stream_capable_provider() -> None:
    non_stream = FakeAdapter()
    stream = FakeAdapter(chunks=["{", "}"])
    gateway = _gateway(
        [
            _provider("primary", non_stream),
            _provider(
                "secondary",
                stream,
                capabilities={
                    LLMCapability.TEXT,
                    LLMCapability.STRUCTURED_OUTPUT,
                    LLMCapability.STREAMING,
                },
            ),
        ],
        fallback=("secondary",),
    )

    chunks = [chunk async for chunk in gateway.stream(_prompt())]

    assert chunks == ["{", "}"]
    assert non_stream.calls == 0
    assert stream.calls == 1


@pytest.mark.asyncio
async def test_streaming_tool_combination_uses_declared_capability() -> None:
    provider = FakeAdapter()
    gateway = _gateway(
        [
            _provider(
                "primary",
                provider,
                capabilities={
                    LLMCapability.TEXT,
                    LLMCapability.STRUCTURED_OUTPUT,
                    LLMCapability.STREAMING,
                    LLMCapability.TOOL_CALLING,
                },
            )
        ]
    )

    chunks = [
        chunk
        async for chunk in gateway.stream(
            _prompt(output_contract_name="submit_answer")
        )
    ]

    assert chunks == ["{}"]
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_streaming_retryable_failure_recovers_within_shared_budget() -> None:
    provider = FakeAdapter(
        stream_runs=[[LLMTimeoutError()], ["recovered"]],
    )
    gateway = _gateway(
        [
            _provider(
                "primary",
                provider,
                capabilities={
                    LLMCapability.TEXT,
                    LLMCapability.STRUCTURED_OUTPUT,
                    LLMCapability.STREAMING,
                },
            )
        ]
    )
    budget = LLMCallBudget(max_calls=2)

    chunks = [chunk async for chunk in gateway.stream(_prompt(budget=budget))]

    assert chunks == ["recovered"]
    assert provider.calls == 2
    assert budget.used_calls == 2


@pytest.mark.asyncio
async def test_stream_failure_after_output_never_appends_fallback() -> None:
    primary = FakeAdapter(stream_runs=[["partial", LLMTimeoutError()]])
    secondary = FakeAdapter(chunks=["fallback"])
    streaming = {
        LLMCapability.TEXT,
        LLMCapability.STRUCTURED_OUTPUT,
        LLMCapability.STREAMING,
    }
    gateway = _gateway(
        [
            _provider("primary", primary, capabilities=streaming),
            _provider("secondary", secondary, capabilities=streaming),
        ],
        fallback=("secondary",),
    )

    received: list[str] = []
    with pytest.raises(LLMGatewayError) as caught:
        async for chunk in gateway.stream(_prompt()):
            received.append(chunk)

    assert received == ["partial"]
    assert caught.value.failure_class is LLMFailureClass.TIMEOUT
    assert primary.calls == 1
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_streaming_vision_never_uses_text_only_fallback() -> None:
    vision_non_stream = FakeAdapter()
    text_stream = FakeAdapter(chunks=["text-only"])
    gateway = _gateway(
        [
            _provider(
                "primary",
                vision_non_stream,
                capabilities={
                    LLMCapability.TEXT,
                    LLMCapability.STRUCTURED_OUTPUT,
                    LLMCapability.VISION,
                },
            ),
            _provider(
                "secondary",
                text_stream,
                capabilities={
                    LLMCapability.TEXT,
                    LLMCapability.STRUCTURED_OUTPUT,
                    LLMCapability.STREAMING,
                },
            ),
        ],
        fallback=("secondary",),
    )

    with pytest.raises(LLMGatewayError) as caught:
        _ = [
            chunk
            async for chunk in gateway.stream(
                _prompt(images=["data:image/png;base64,AA=="])
            )
        ]

    assert caught.value.failure_class is LLMFailureClass.NO_COMPATIBLE_PROVIDER
    assert vision_non_stream.calls == 0
    assert text_stream.calls == 0


@pytest.mark.asyncio
async def test_breaker_isolated_by_provider_and_purpose_and_half_open_recovers() -> None:
    now = [0.0]
    primary = FakeAdapter(
        [LLMTimeoutError(), _response("other-purpose"), _response("recovered")]
    )
    secondary = FakeAdapter(
        [_response("fallback-1"), _response("fallback-2"), _response("fallback-3")]
    )
    gateway = _gateway(
        [_provider("primary", primary), _provider("secondary", secondary)],
        fallback=("secondary",),
        threshold=1,
        recovery=5.0,
        clock=lambda: now[0],
    )

    first = await gateway.execute(_prompt())
    second = await gateway.execute(_prompt())
    other_purpose = await gateway.execute(_prompt(purpose=LLMPurpose.QUERY_REWRITE))

    assert first.provider == second.provider == "secondary"
    assert other_purpose.provider == "primary"
    assert gateway.breaker_state(
        "primary", "primary-model", LLMPurpose.CHAT_RESPONSE
    ) is BreakerState.OPEN

    now[0] = 6.0
    recovered = await gateway.execute(_prompt())

    assert recovered.provider == "primary"
    assert gateway.breaker_state(
        "primary", "primary-model", LLMPurpose.CHAT_RESPONSE
    ) is BreakerState.CLOSED


@pytest.mark.asyncio
async def test_half_open_allows_one_bounded_probe() -> None:
    now = [0.0]
    entered = asyncio.Event()
    release = asyncio.Event()
    primary = HalfOpenProbeAdapter(entered, release)
    secondary = FakeAdapter(
        [_response("fallback-1"), _response("fallback-while-probing")]
    )
    gateway = _gateway(
        [_provider("primary", primary), _provider("secondary", secondary)],
        fallback=("secondary",),
        threshold=1,
        recovery=5.0,
        clock=lambda: now[0],
    )

    initial = await gateway.execute(_prompt())
    assert initial.provider == "secondary"
    now[0] = 6.0
    probe = asyncio.create_task(gateway.execute(_prompt()))
    await entered.wait()

    concurrent = await gateway.execute(_prompt())
    release.set()
    recovered = await probe

    assert recovered.provider == "primary"
    assert concurrent.provider == "secondary"
    assert primary.calls == 2
    assert secondary.calls == 2


@pytest.mark.asyncio
async def test_breaker_isolated_between_models_of_same_provider() -> None:
    fast = FakeAdapter([LLMTimeoutError()])
    quality = FakeAdapter([_response("quality-model")])
    gateway = _gateway(
        [
            _provider("primary", fast, model="fast-model", profiles={"fast"}),
            _provider(
                "primary", quality, model="quality-model", profiles={"quality"}
            ),
        ],
        threshold=1,
        retry_limit=0,
    )

    fast_outcome = await gateway.execute(_prompt(model_profile="fast"))
    quality_outcome = await gateway.execute(_prompt(model_profile="quality"))

    assert fast_outcome.failure_class is LLMFailureClass.TIMEOUT
    assert quality_outcome.status is LLMGatewayStatus.SUCCESS
    assert gateway.breaker_state(
        "primary", "fast-model", LLMPurpose.CHAT_RESPONSE
    ) is BreakerState.OPEN
    assert gateway.breaker_state(
        "primary", "quality-model", LLMPurpose.CHAT_RESPONSE
    ) is BreakerState.CLOSED


@pytest.mark.asyncio
async def test_provider_bulkhead_saturation_falls_back_without_starving_secondary() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    primary = FakeAdapter(entered=entered, release=release)
    secondary = FakeAdapter([_response("secondary")])
    gateway = _gateway(
        [_provider("primary", primary), _provider("secondary", secondary)],
        fallback=("secondary",),
        bulkhead_wait=0.001,
    )

    first_task = asyncio.create_task(gateway.execute(_prompt()))
    await entered.wait()
    second = await gateway.execute(_prompt())
    release.set()
    first = await first_task

    assert first.provider == "primary"
    assert second.provider == "secondary"
    assert second.fallback_used
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_total_call_timeout_is_classified_and_bounded() -> None:
    entered = asyncio.Event()
    never_release = asyncio.Event()
    provider = FakeAdapter(entered=entered, release=never_release)
    gateway = _gateway(
        [_provider("primary", provider)], timeout=0.005, retry_limit=0
    )

    outcome = await gateway.execute(_prompt(budget=LLMCallBudget(max_calls=1)))

    assert outcome.status is LLMGatewayStatus.DEGRADED
    assert outcome.failure_class is LLMFailureClass.TIMEOUT
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_expired_request_deadline_makes_no_provider_call() -> None:
    provider = FakeAdapter()
    gateway = _gateway([_provider("primary", provider)], clock=lambda: 10.0)
    budget = LLMCallBudget(max_calls=2, deadline_at=9.0)

    outcome = await gateway.execute(_prompt(budget=budget))

    assert outcome.status is LLMGatewayStatus.DEGRADED
    assert outcome.failure_class is LLMFailureClass.DEADLINE_EXCEEDED
    assert provider.calls == 0
    assert budget.used_calls == 0


@pytest.mark.asyncio
async def test_caller_cancellation_stops_retry_and_fallback() -> None:
    entered = asyncio.Event()
    never_release = asyncio.Event()
    primary = FakeAdapter(entered=entered, release=never_release)
    secondary = FakeAdapter()
    gateway = _gateway(
        [_provider("primary", primary), _provider("secondary", secondary)],
        fallback=("secondary",),
        timeout=1.0,
    )

    task = asyncio.create_task(gateway.execute(_prompt()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert primary.calls == 1
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_auth_configuration_failure_is_not_retried() -> None:
    provider = FakeAdapter(
        [LLMError("secret payload", retryable=False, code="AUTH_CONFIG")]
    )
    gateway = _gateway([_provider("primary", provider)])

    outcome = await gateway.execute(_prompt())

    assert outcome.status is LLMGatewayStatus.FAILURE
    assert outcome.failure_class is LLMFailureClass.AUTH_CONFIG
    assert provider.calls == 1


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LLMRateLimitError(), LLMFailureClass.RATE_LIMIT),
        (
            LLMError("provider unavailable", retryable=True, code="PROVIDER_5XX"),
            LLMFailureClass.PROVIDER_5XX,
        ),
    ],
)
@pytest.mark.asyncio
async def test_retryable_failure_classification(
    error: BaseException, expected: LLMFailureClass
) -> None:
    provider = FakeAdapter([error])
    gateway = _gateway(
        [_provider("primary", provider)], retry_limit=0, threshold=1
    )

    outcome = await gateway.execute(_prompt())

    assert outcome.failure_class is expected
    assert gateway.breaker_state(
        "primary", "primary-model", LLMPurpose.CHAT_RESPONSE
    ) is BreakerState.OPEN


@pytest.mark.parametrize(
    ("status_code", "expected_type", "expected_code"),
    [
        (401, LLMError, "AUTH_CONFIG"),
        (429, LLMRateLimitError, "RATE_LIMIT"),
        (503, LLMError, "PROVIDER_5XX"),
    ],
)
@pytest.mark.asyncio
async def test_deepseek_http_failure_mapping_is_typed_and_sanitized(
    status_code: int,
    expected_type: type[LLMError],
    expected_code: str,
) -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, text="provider-secret-response-body")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = DeepSeekAdapter(http_client=client)

    with pytest.raises(expected_type) as caught:
        await adapter.generate(_prompt())
    await client.aclose()

    assert caught.value.code == expected_code
    assert "provider-secret-response-body" not in str(caught.value)
    assert calls == 1


@pytest.mark.asyncio
async def test_deepseek_transport_failure_is_typed_and_single_attempt() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("provider-secret-transport", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = DeepSeekAdapter(http_client=client)

    with pytest.raises(LLMError) as caught:
        await adapter.generate(_prompt())
    await client.aclose()

    assert caught.value.code == "TRANSPORT"
    assert "provider-secret-transport" not in str(caught.value)
    assert calls == 1


@pytest.mark.asyncio
async def test_gemini_adapter_does_not_retry_below_gateway() -> None:
    adapter = GeminiAdapter.__new__(GeminiAdapter)
    provider_call = AsyncMock(side_effect=LLMTimeoutError())
    adapter._call_gemini = provider_call

    with pytest.raises(LLMTimeoutError):
        await adapter.generate(_prompt())

    provider_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_groq_adapter_does_not_retry_below_gateway() -> None:
    adapter = GroqAdapter.__new__(GroqAdapter)
    provider_call = AsyncMock(side_effect=LLMTimeoutError())
    adapter._call_groq = provider_call

    with pytest.raises(LLMTimeoutError):
        await adapter.generate(_prompt())

    provider_call.assert_awaited_once()


def test_configuration_validation_requires_enabled_primary_credentials_and_models() -> None:
    valid = settings.model_copy(
        update={
            "LLM_PROVIDER": "deepseek",
            "LLM_ENABLED_PROVIDERS": "deepseek",
            "LLM_FALLBACK_PROVIDERS": "",
            "DEEPSEEK_API_KEY": "configured",
            "DEEPSEEK_MODEL": "deepseek-model",
            "DEEPSEEK_VISION_MODEL": "deepseek-vision",
        }
    )
    assert validate_llm_configuration(valid) == []

    missing_key = valid.model_copy(update={"DEEPSEEK_API_KEY": None})
    missing_findings = validate_llm_configuration(missing_key)
    assert "enabled LLM provider is missing credentials: deepseek" in missing_findings
    assert "no configured model supports text and structured output" in missing_findings
    assert "no configured model supports grounded tool output and vision" in missing_findings

    invalid_fallback = valid.model_copy(update={"LLM_FALLBACK_PROVIDERS": "gemini"})
    assert validate_llm_configuration(invalid_fallback) == [
        "fallback LLM provider is not enabled: gemini"
    ]

    missing_models = valid.model_copy(
        update={"DEEPSEEK_MODEL": "", "DEEPSEEK_VISION_MODEL": ""}
    )
    assert validate_llm_configuration(missing_models) == [
        "enabled LLM provider is missing a model: deepseek",
        "DeepSeek vision model is not configured",
    ]

    invalid_purpose = valid.model_copy(
        update={"LLM_DEEPSEEK_PURPOSES": "chat_response,not_a_purpose"}
    )
    assert validate_llm_configuration(invalid_purpose) == [
        "enabled LLM provider has invalid purpose eligibility: deepseek",
        "DeepSeek primary does not allow chat_response purpose",
    ]


@pytest.mark.asyncio
async def test_gateway_logs_and_errors_do_not_disclose_prompt_or_provider_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = FakeAdapter(
        [LLMError("provider-secret-value", retryable=False, code="AUTH_CONFIG")]
    )
    gateway = _gateway([_provider("primary", provider)])
    prompt = _prompt()

    with pytest.raises(LLMGatewayError) as caught:
        await gateway.generate(prompt)

    rendered = caplog.text
    assert "provider-secret-value" not in rendered
    assert prompt.system not in rendered
    assert prompt.user_message not in rendered
    assert "provider-secret-value" not in str(caught.value)
    assert caught.value.failure_class is LLMFailureClass.AUTH_CONFIG
