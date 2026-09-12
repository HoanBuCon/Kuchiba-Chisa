from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.settings import settings
from app.domain.interfaces.llm_provider import LLMCallBudget, StructuredPrompt
from app.domain.interfaces.lore_corpus_identity import LoreCorpusIdentity
from app.domain.interfaces.observability import (
    CounterSignal,
    TelemetryDimensions,
)
from app.domain.models.evidence import (
    Evidence,
    EvidenceAccess,
    EvidenceProvenance,
    EvidenceScore,
)
from app.domain.models.intent_result import ChatIntent
from app.domain.services.chat_engine import ChatPipeline
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.cache_stage import CacheStage
from app.domain.services.chat_pipeline.stages.cache_update_stage import CacheUpdateStage
from app.domain.services.chat_pipeline.stages.llm_generation_stage import LLMGenerationStage
from app.domain.services.lore_answer_cache import (
    LoreAnswerCacheContract,
    LoreAnswerCacheEntry,
    LoreAnswerCachePolicy,
)
from app.infrastructure.llm.gateway_factory import generation_policy_fingerprint
from app.infrastructure.vector.qdrant.qdrant_service import QdrantService

NOW = 1_800_000_000.0
PROTECTED_SENTINEL = "protected-persona-content-must-not-be-cached"


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        await asyncio.sleep(0)
        self.values[key] = value
        self.ttls[key] = ttl


class CorpusProvider:
    def __init__(self, version: str = "v1") -> None:
        self.version = version

    async def active_lore_corpus_identity(self) -> LoreCorpusIdentity:
        return _corpus(self.version)


def _corpus(version: str = "v1") -> LoreCorpusIdentity:
    return LoreCorpusIdentity(
        alias_targets=(
            ("character_lore", f"character_lore__{version}"),
            ("story_lore", f"story_lore__{version}"),
            ("world_lore", f"world_lore__{version}"),
        )
    )


def _contract(
    *, generation: str = "a" * 64, prompt: str = "prompt-v1", grounding: str = "rag06-v2"
) -> LoreAnswerCacheContract:
    return LoreAnswerCacheContract(
        LoreAnswerCachePolicy(
            generation_fingerprint=generation,
            prompt_semantics_version=prompt,
            grounding_contract_version=grounding,
            ttl_seconds=120,
        )
    )


def _evidence(access: EvidenceAccess | None = None) -> Evidence:
    return Evidence(
        evidence_id="lore:point-1",
        kind="lore",
        text="Aalto is affiliated with the New Federation.",
        provenance=EvidenceProvenance(
            source_id="point-1",
            source_type="raw_wiki",
            collection="character_lore",
            source_version="v1",
        ),
        access=access or EvidenceAccess(scope="public"),
        score=EvidenceScore(final=0.9),
    )


def _context(
    *,
    user_id: str = "user-1",
    guild_id: str | None = None,
    channel_id: str | None = None,
) -> ChatContext:
    context = ChatContext(
        session=SimpleNamespace(),
        user_id=user_id,
        user_message="Aalto belongs to which organization?",
        is_community=guild_id is not None,
        guild_id=guild_id,
        channel_id=channel_id,
    )
    context.cleaned_query = "  Aalto belongs to which organization?  "
    context.rewritten_query = "Aalto belongs to which organization?"
    context.intents = [ChatIntent.LORE, ChatIntent.KNOWLEDGE_OR_TASK]
    context.llm_call_budget = LLMCallBudget(max_calls=2)
    return context


def _grounded(context: ChatContext, evidence: Evidence | None = None) -> ChatContext:
    item = evidence or _evidence()
    context.prompt = StructuredPrompt(
        system=PROTECTED_SENTINEL,
        history=[],
        user_message=context.cleaned_query,
        response_schema={"type": "object"},
        retrieved_evidence=[item],
        output_contract_name="submit_grounded_answer",
    )
    context.chisa_reply = "Aalto is affiliated with the New Federation."
    context.citation_ids = [item.evidence_id]
    context.tool_res = {
        "grounding": {"status": "verified"},
        "generation_contract": {"abstained": False},
    }
    return context


def _generation_ready(context: ChatContext) -> ChatContext:
    """Prepare a grounded request before generation, without a completed result."""
    _grounded(context)
    assert context.prompt is not None
    context.prompt = context.prompt.model_copy(
        update={
            "response_schema": {
                "type": "object",
                "properties": {"sentiment": {"type": "object"}},
            }
        }
    )
    context.chisa_reply = ""
    context.citation_ids = []
    context.tool_res = None
    return context


async def _write(
    cache: MemoryCache,
    context: ChatContext,
    contract: LoreAnswerCacheContract,
    provider: CorpusProvider | None = None,
) -> str:
    actual_provider = provider or CorpusProvider()
    read = CacheStage(cache, actual_provider, contract, clock=lambda: NOW)
    await read.process(context)
    _grounded(context)
    await CacheUpdateStage(cache, actual_provider, contract, clock=lambda: NOW).process(context)
    assert context.lore_cache_identity is not None
    return context.lore_cache_identity.key


@pytest.mark.asyncio
async def test_same_identity_hits_and_retains_server_citations_without_provider_call() -> None:
    cache = MemoryCache()
    contract = _contract()
    key = await _write(cache, _context(), contract)

    request = _context()
    result = await CacheStage(
        cache, CorpusProvider(), contract, clock=lambda: NOW + 1
    ).process(request)

    assert result.is_cached_answer is True
    assert result.citation_ids == ["lore:point-1"]
    assert result.lore_cache_outcome == "hit"
    assert result.llm_call_budget.used_calls == 0
    assert cache.ttls[key] == 120

    provider = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("provider called")))
    await LLMGenerationStage(llm=provider).process(result)
    provider.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_read_hit_and_miss_outcomes_are_observable() -> None:
    cache = MemoryCache()
    contract = _contract()
    await _write(cache, _context(), contract)
    telemetry = MagicMock()

    await CacheStage(
        cache,
        CorpusProvider(),
        contract,
        clock=lambda: NOW + 1,
        telemetry=telemetry,
    ).process(_context())
    await CacheStage(
        MemoryCache(),
        CorpusProvider(),
        contract,
        clock=lambda: NOW + 1,
        telemetry=telemetry,
    ).process(_context())

    telemetry.count.assert_any_call(
        CounterSignal.CACHE_OPERATIONS,
        TelemetryDimensions(cache_outcome="hit", status="read"),
    )
    telemetry.count.assert_any_call(
        CounterSignal.CACHE_OPERATIONS,
        TelemetryDimensions(cache_outcome="miss", status="read"),
    )


@pytest.mark.asyncio
async def test_cache_stale_version_and_write_outcomes_are_observable() -> None:
    cache = MemoryCache()
    contract = _contract()
    telemetry = MagicMock()
    provider = CorpusProvider("v1")
    stale = _context()
    await CacheStage(cache, provider, contract, clock=lambda: NOW).process(stale)
    _grounded(stale)
    provider.version = "v2"

    await CacheUpdateStage(
        cache,
        provider,
        contract,
        clock=lambda: NOW,
        telemetry=telemetry,
    ).process(stale)

    writable = _context()
    writable.lore_cache_identity = contract.identity(writable, _corpus())
    _grounded(writable)
    await CacheUpdateStage(
        cache,
        CorpusProvider(),
        contract,
        clock=lambda: NOW,
        telemetry=telemetry,
    ).process(writable)

    telemetry.count.assert_any_call(
        CounterSignal.CACHE_OPERATIONS,
        TelemetryDimensions(cache_outcome="stale_version", status="write"),
    )
    telemetry.count.assert_any_call(
        CounterSignal.CACHE_OPERATIONS,
        TelemetryDimensions(cache_outcome="write", status="write"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "contract"),
    [
        (CorpusProvider("v2"), _contract()),
        (CorpusProvider(), _contract(generation="b" * 64)),
        (CorpusProvider(), _contract(prompt="prompt-v2")),
        (CorpusProvider(), _contract(grounding="rag06-v3")),
    ],
)
async def test_version_changes_are_cache_misses(
    provider: CorpusProvider, contract: LoreAnswerCacheContract
) -> None:
    cache = MemoryCache()
    await _write(cache, _context(), _contract())

    result = await CacheStage(cache, provider, contract, clock=lambda: NOW + 1).process(
        _context()
    )

    assert result.is_cached_answer is False
    assert result.lore_cache_outcome == "miss"
    assert result.llm_call_budget.used_calls == 0


@pytest.mark.asyncio
async def test_principal_tenant_and_channel_change_cannot_reuse_entry() -> None:
    cache = MemoryCache()
    contract = _contract()
    await _write(cache, _context(user_id="one", guild_id="guild-a", channel_id="a"), contract)

    for request in (
        _context(user_id="two", guild_id="guild-a", channel_id="a"),
        _context(user_id="one", guild_id="guild-b", channel_id="a"),
        _context(user_id="one", guild_id="guild-a", channel_id="b"),
    ):
        await CacheStage(cache, CorpusProvider(), contract, clock=lambda: NOW + 1).process(
            request
        )
        assert request.is_cached_answer is False
        assert request.lore_cache_outcome == "miss"


@pytest.mark.asyncio
async def test_same_tenant_channel_can_reuse_tenant_scoped_lore() -> None:
    cache = MemoryCache()
    contract = _contract()
    context = _context(guild_id="guild-a", channel_id="channel-a")
    await CacheStage(cache, CorpusProvider(), contract, clock=lambda: NOW).process(context)
    _grounded(
        context,
        _evidence(
            EvidenceAccess(
                scope="tenant", tenant_id="guild-a", channel_id="channel-a"
            )
        ),
    )
    await CacheUpdateStage(cache, CorpusProvider(), contract, clock=lambda: NOW).process(context)

    request = _context(guild_id="guild-a", channel_id="channel-a")
    await CacheStage(cache, CorpusProvider(), contract, clock=lambda: NOW + 1).process(
        request
    )
    assert request.is_cached_answer is True
    assert request.citation_ids == ["lore:point-1"]


@pytest.mark.asyncio
async def test_narrower_authorization_rejects_forged_broader_scope_receipt() -> None:
    cache = MemoryCache()
    contract = _contract()
    broad = _context(guild_id="guild-a", channel_id="channel-a")
    broad_identity = contract.identity(broad, _corpus())
    broad_entry = contract.build_entry(
        _grounded(broad, _evidence(EvidenceAccess(scope="tenant", tenant_id="guild-a"))),
        broad_identity,
        now=NOW,
    )
    assert broad_entry is not None

    narrow = _context()
    narrow_identity = contract.identity(narrow, _corpus())
    forged = broad_entry.model_copy(
        update={
            "identity_digest": narrow_identity.digest,
            "authorization_fingerprint": narrow_identity.authorization_fingerprint,
            "prompt_fingerprint": narrow_identity.prompt_fingerprint,
        }
    )
    cache.values[narrow_identity.key] = forged.model_dump_json()

    await CacheStage(cache, CorpusProvider(), contract, clock=lambda: NOW + 1).process(narrow)
    assert narrow.is_cached_answer is False
    assert narrow.lore_cache_outcome == "acl_mismatch"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["legacy answer", "{}", "not-json"])
async def test_legacy_and_malformed_entries_fail_as_safe_misses(raw: str) -> None:
    cache = MemoryCache()
    context = _context()
    contract = _contract()
    identity = contract.identity(context, _corpus())
    cache.values[identity.key] = raw

    await CacheStage(cache, CorpusProvider(), contract, clock=lambda: NOW).process(context)
    assert context.is_cached_answer is False
    assert context.lore_cache_outcome == "malformed"
    assert cache.values[identity.key] == raw


@pytest.mark.asyncio
async def test_expired_entry_is_a_miss_without_mutation() -> None:
    cache = MemoryCache()
    contract = _contract()
    key = await _write(cache, _context(), contract)

    request = _context()
    await CacheStage(cache, CorpusProvider(), contract, clock=lambda: NOW + 121).process(request)
    assert request.is_cached_answer is False
    assert request.lore_cache_outcome == "expired"
    assert key in cache.values


@pytest.mark.asyncio
async def test_alias_swap_between_read_and_write_prevents_stale_publication() -> None:
    cache = MemoryCache()
    provider = CorpusProvider("v1")
    contract = _contract()
    context = _context()
    await CacheStage(cache, provider, contract, clock=lambda: NOW).process(context)
    _grounded(context)

    provider.version = "v2"
    await CacheUpdateStage(cache, provider, contract, clock=lambda: NOW).process(context)

    assert context.lore_cache_outcome == "stale_version"
    assert cache.values == {}


@pytest.mark.asyncio
async def test_cache_backend_failure_degrades_to_normal_miss_and_preserves_budget() -> None:
    cache = SimpleNamespace(get=AsyncMock(side_effect=ConnectionError("unavailable")))
    context = _context()

    await CacheStage(cache, CorpusProvider(), _contract(), clock=lambda: NOW).process(context)

    assert context.is_cached_answer is False
    assert context.lore_cache_outcome == "unavailable"
    assert context.llm_call_budget.used_calls == 0


@pytest.mark.asyncio
async def test_provider_failure_stops_pipeline_before_cache_publication() -> None:
    cache = MemoryCache()
    contract = _contract()
    context = _generation_ready(_context())
    context.lore_cache_identity = contract.identity(context, _corpus())
    provider = SimpleNamespace(generate=AsyncMock(side_effect=ConnectionError("offline")))
    pipeline = ChatPipeline(
        [
            LLMGenerationStage(llm=provider),
            CacheUpdateStage(cache, CorpusProvider(), contract, clock=lambda: NOW),
        ]
    )

    with pytest.raises(ConnectionError, match="offline"):
        await pipeline.execute(context)

    assert cache.values == {}


@pytest.mark.asyncio
async def test_incomplete_stream_stops_pipeline_before_cache_publication() -> None:
    class InterruptedStreamProvider:
        async def stream(self, prompt):
            del prompt
            yield '{"answer":"partial'
            raise ConnectionError("stream interrupted")

        async def validate_response(self, raw, schema):
            raise AssertionError((raw, schema))

    cache = MemoryCache()
    contract = _contract()
    context = _generation_ready(_context())
    context.on_token = lambda token: None
    context.lore_cache_identity = contract.identity(context, _corpus())
    pipeline = ChatPipeline(
        [
            LLMGenerationStage(llm=InterruptedStreamProvider()),
            CacheUpdateStage(cache, CorpusProvider(), contract, clock=lambda: NOW),
        ]
    )

    with pytest.raises(ConnectionError, match="stream interrupted"):
        await pipeline.execute(context)

    assert cache.values == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        lambda context: setattr(context, "tool_res", {"grounding": {"status": "rejected"}}),
        lambda context: setattr(context, "chisa_reply", ""),
        lambda context: context.tool_res["generation_contract"].update({"abstained": True}),
        lambda context: setattr(context, "citation_ids", []),
    ],
)
async def test_rejected_failed_or_abstained_results_are_not_cached(mutation) -> None:
    cache = MemoryCache()
    contract = _contract()
    context = _context()
    await CacheStage(cache, CorpusProvider(), contract, clock=lambda: NOW).process(context)
    _grounded(context)
    mutation(context)

    await CacheUpdateStage(cache, CorpusProvider(), contract, clock=lambda: NOW).process(context)
    assert cache.values == {}
    assert context.lore_cache_outcome == "not_cacheable"


@pytest.mark.asyncio
async def test_private_memory_mixed_into_lore_prompt_is_not_cached() -> None:
    cache = MemoryCache()
    contract = _contract()
    context = _context()
    await CacheStage(cache, CorpusProvider(), contract, clock=lambda: NOW).process(context)
    memory = _evidence(EvidenceAccess(scope="user", subject_id=context.user_id)).model_copy(
        update={"evidence_id": "memory:one", "kind": "memory"}
    )
    _grounded(context, memory)

    await CacheUpdateStage(cache, CorpusProvider(), contract, clock=lambda: NOW).process(context)
    assert cache.values == {}


@pytest.mark.asyncio
async def test_concurrent_writes_leave_one_valid_current_format_entry() -> None:
    cache = MemoryCache()
    contract = _contract()
    first = _context()
    second = _context()
    for context in (first, second):
        context.lore_cache_identity = contract.identity(context, _corpus())
        _grounded(context)

    stage = CacheUpdateStage(cache, CorpusProvider(), contract, clock=lambda: NOW)
    await asyncio.gather(stage.process(first), stage.process(second))

    assert len(cache.values) == 1
    LoreAnswerCacheEntry.model_validate_json(next(iter(cache.values.values())))


@pytest.mark.asyncio
async def test_cache_metadata_never_contains_raw_prompt_query_or_principal() -> None:
    cache = MemoryCache()
    context = _context(user_id="sensitive-user-id")
    context.history = [{"role": "system", "content": PROTECTED_SENTINEL}]
    key = await _write(cache, context, _contract())
    raw = cache.values[key]

    assert PROTECTED_SENTINEL not in key
    assert PROTECTED_SENTINEL not in raw
    assert context.cleaned_query not in key
    assert context.cleaned_query not in raw
    assert context.user_id not in key
    assert context.user_id not in raw

    tracker = SimpleNamespace(add_step=MagicMock())
    request = _context(user_id=context.user_id)
    request.history = list(context.history)
    await CacheStage(
        cache,
        CorpusProvider(),
        _contract(),
        pipeline_tracker=tracker,
        clock=lambda: NOW + 1,
    ).process(request)
    tracked = json.dumps(tracker.add_step.call_args.kwargs, default=str)
    assert PROTECTED_SENTINEL not in tracked
    assert context.cleaned_query not in tracked
    assert context.chisa_reply not in tracked


def test_generation_identity_tracks_only_enabled_be02_models_and_routing() -> None:
    base = settings.model_copy(
        update={
            "LLM_ENABLED_PROVIDERS": "deepseek",
            "LLM_PROVIDER": "deepseek",
            "LLM_FALLBACK_PROVIDERS": "",
            "DEEPSEEK_MODEL": "deepseek-a",
            "GEMINI_MODEL": "unused-a",
        }
    )
    changed_enabled = base.model_copy(update={"DEEPSEEK_MODEL": "deepseek-b"})
    changed_disabled = base.model_copy(update={"GEMINI_MODEL": "unused-b"})

    assert generation_policy_fingerprint(base) != generation_policy_fingerprint(changed_enabled)
    assert generation_policy_fingerprint(base) == generation_policy_fingerprint(changed_disabled)


@pytest.mark.asyncio
async def test_qdrant_corpus_identity_is_one_complete_versioned_alias_snapshot() -> None:
    aliases = [
        SimpleNamespace(alias_name="character_lore__active", collection_name="character_lore__v1"),
        SimpleNamespace(alias_name="world_lore__active", collection_name="world_lore__v1"),
        SimpleNamespace(alias_name="story_lore__active", collection_name="story_lore__v1"),
    ]
    client = SimpleNamespace(get_aliases=AsyncMock(return_value=SimpleNamespace(aliases=aliases)))
    service = QdrantService(client=client)

    assert await service.active_lore_corpus_identity() == _corpus()
    client.get_aliases.assert_awaited_once()

    aliases.pop()
    assert await service.active_lore_corpus_identity() is None
