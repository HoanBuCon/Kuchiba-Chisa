"""Question understanding: lane and standalone query from one cached LLM call."""

import contextlib
import json
from dataclasses import fields
from types import SimpleNamespace

import pytest

from app.domain.interfaces.llm_provider import LLMCallBudget, LLMError
from app.domain.interfaces.observability import CounterSignal
from app.domain.services.knowledge.lane_router import Lane
from app.domain.services.knowledge.understanding import PriorTurn, UnderstandingError
from app.infrastructure.knowledge.llm_question_understander import (
    ANSWER_CHARS,
    CACHE_PREFIX,
    LlmQuestionUnderstander,
)


class FakeLlm:
    def __init__(self, parsed=None, error=None) -> None:
        self.parsed = parsed or {"lane": "advanced", "query": "Where does Chisa study?"}
        self.error = error
        self.prompts = []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return SimpleNamespace(parsed=self.parsed)


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl=None):
        self.store[key] = value


PREVIOUS = [PriorTurn("Chisa là ai?", "Chisa là một Resonator. " + "x" * 1000)]


async def test_parses_lane_and_query() -> None:
    understander = LlmQuestionUnderstander(FakeLlm())

    result = await understander.understand("Còn cô ấy học ở đâu?", PREVIOUS)

    assert result.lane is Lane.ADVANCED
    assert result.query == "Where does Chisa study?"


async def test_companion_keeps_an_empty_query() -> None:
    llm = FakeLlm({"lane": "companion", "query": ""})

    result = await LlmQuestionUnderstander(llm).understand("Em dễ thương quá", [])

    assert (result.lane, result.query) == (Lane.COMPANION, "")


async def test_history_is_alternating_roles_with_truncated_answers() -> None:
    llm = FakeLlm()

    await LlmQuestionUnderstander(llm).understand("Còn cô ấy?", PREVIOUS)

    prompt = llm.prompts[0]
    assert [m["role"] for m in prompt.history] == ["user", "assistant"]
    assert prompt.history[0]["content"] == "Chisa là ai?"
    assert len(prompt.history[1]["content"]) == ANSWER_CHARS
    assert prompt.user_message == "Còn cô ấy?"
    assert prompt.output_contract_name == "question_understanding"


async def test_identical_input_hits_the_cache_and_other_history_misses() -> None:
    llm, cache = FakeLlm(), FakeCache()
    understander = LlmQuestionUnderstander(llm, cache)

    await understander.understand("Còn cô ấy?", PREVIOUS)
    await understander.understand("Còn cô ấy?", PREVIOUS)
    await understander.understand("Còn cô ấy?", [PriorTurn("Khác", "Khác")])

    assert len(llm.prompts) == 2
    assert all(key.startswith(CACHE_PREFIX) for key in cache.store)
    assert len(cache.store) == 2


async def test_budget_is_passed_to_the_prompt() -> None:
    llm = FakeLlm()
    budget = LLMCallBudget(max_calls=2)

    await LlmQuestionUnderstander(llm).understand("Tacet Field là gì?", [], budget)

    assert llm.prompts[0].call_budget is budget


async def test_llm_error_becomes_understanding_error() -> None:
    understander = LlmQuestionUnderstander(FakeLlm(error=LLMError("down")))

    with pytest.raises(UnderstandingError):
        await understander.understand("Tacet Field là gì?", [])


@pytest.mark.parametrize(
    "parsed",
    [{"lane": "advanced", "query": "  "}, {"lane": "other", "query": "x"}, {"query": "x"}],
)
async def test_unusable_answers_raise(parsed) -> None:
    with pytest.raises(UnderstandingError):
        await LlmQuestionUnderstander(FakeLlm(parsed)).understand("Tacet Field là gì?", [])


async def test_corrupt_cache_value_is_a_miss() -> None:
    llm, cache = FakeLlm(), FakeCache()
    understander = LlmQuestionUnderstander(llm, cache)
    await understander.understand("Tacet Field là gì?", [])
    (key,) = cache.store
    cache.store[key] = "{not json"

    result = await understander.understand("Tacet Field là gì?", [])

    assert len(llm.prompts) == 2
    assert result.query == "Where does Chisa study?"
    assert json.loads(cache.store[key])["lane"] == "advanced"


class RecordingTelemetry:
    def __init__(self) -> None:
        self.counts = []

    def count(self, signal, dimensions, amount=1):
        self.counts.append((signal, dimensions, amount))

    def outcomes(self):
        return [dimensions.outcome for _, dimensions, _ in self.counts]


async def _outcomes(llm, cache=None, message="Em dễ thương quá"):
    telemetry = RecordingTelemetry()
    understander = LlmQuestionUnderstander(llm, cache, telemetry=telemetry)
    with contextlib.suppress(UnderstandingError):
        await understander.understand(message, [])
    return telemetry


async def test_a_model_call_counts_one_llm_outcome_without_any_text() -> None:
    telemetry = await _outcomes(FakeLlm(), message="Bí mật của Chisa")

    assert telemetry.outcomes() == ["llm"]
    signal, dimensions, amount = telemetry.counts[0]
    assert signal is CounterSignal.QUESTION_UNDERSTANDING
    assert amount == 1
    assert {value for value in vars_of(dimensions) if value} == {"llm"}


async def test_a_cached_answer_counts_one_cache_hit_and_no_model_call() -> None:
    cache = FakeCache()
    await _outcomes(FakeLlm(), cache)
    llm = FakeLlm()

    telemetry = await _outcomes(llm, cache)

    assert telemetry.outcomes() == ["cache_hit"]
    assert llm.prompts == []


@pytest.mark.parametrize(
    "llm",
    [FakeLlm(error=LLMError("down")), FakeLlm({"lane": "bogus", "query": ""})],
)
async def test_a_provider_error_or_bad_answer_counts_one_failure(llm) -> None:
    telemetry = await _outcomes(llm)

    assert telemetry.outcomes() == ["failed"]


def vars_of(dimensions):
    return [getattr(dimensions, item.name) for item in fields(dimensions)]
