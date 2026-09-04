"""RAG-06 regressions for evidence-bound citations at the generation boundary."""

from __future__ import annotations

import pytest

from app.domain.interfaces.llm_provider import (
    LLMInvalidResponseError,
    LLMResponse,
    StructuredPrompt,
)
from app.domain.models.evidence import (
    Evidence,
    EvidenceAccess,
    EvidenceProvenance,
    EvidenceScore,
)
from app.domain.models.intent_result import ChatIntent, IntentResult
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.llm_generation_stage import LLMGenerationStage


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="lore:approved",
        kind="lore",
        text="Verified lore evidence.",
        provenance=EvidenceProvenance(
            source_id="approved", source_type="wiki", collection="character_lore"
        ),
        access=EvidenceAccess(scope="public"),
        score=EvidenceScore(final=0.9),
    )


class _LLM:
    def __init__(self, parsed: dict[str, object]) -> None:
        self._parsed = parsed
        self.calls = 0

    async def generate(self, _: StructuredPrompt) -> LLMResponse:
        self.calls += 1
        return LLMResponse(raw_content="{}", parsed=self._parsed)


class _StreamingLLM:
    def __init__(self, parsed: dict[str, object]) -> None:
        self._parsed = parsed

    async def stream(self, _: StructuredPrompt):
        yield "{}"

    async def validate_response(
        self, _: str, __: dict[str, object]
    ) -> dict[str, object]:
        return self._parsed


def _context(evidence: list[Evidence]) -> ChatContext:
    return ChatContext(
        session=None,
        user_id="verified-user",
        user_message="Tell me the lore",
        prompt=StructuredPrompt(
            system="unmodified test system content",
            history=[],
            user_message="Tell me the lore",
            response_schema={"type": "object"},
            retrieved_evidence=evidence,
        ),
    )


def _factual_context(evidence: list[Evidence]) -> ChatContext:
    context = _context(evidence)
    context.intent_result = IntentResult(
        intents=[ChatIntent.LORE], confidence=0.9, routing_method="test"
    )
    return context


@pytest.mark.asyncio
async def test_valid_server_evidence_citation_reaches_chat_context() -> None:
    stage = LLMGenerationStage(
        llm=_LLM({"response": "Verified answer.", "citations": ["lore:approved"]})
    )

    result = await stage.process(_context([_evidence()]))

    assert result.chisa_reply == "Verified answer."
    assert result.citation_ids == ["lore:approved"]


@pytest.mark.asyncio
async def test_model_cannot_cite_an_identifier_outside_selected_evidence() -> None:
    stage = LLMGenerationStage(
        llm=_LLM({"response": "Untrusted answer.", "citations": ["lore:attacker"]})
    )

    with pytest.raises(LLMInvalidResponseError, match="grounding checks"):
        await stage.process(_context([_evidence()]))


@pytest.mark.asyncio
async def test_model_cannot_add_citations_when_no_evidence_was_selected() -> None:
    stage = LLMGenerationStage(
        llm=_LLM({"response": "Untrusted answer.", "citations": ["lore:attacker"]})
    )

    with pytest.raises(LLMInvalidResponseError, match="grounding checks"):
        await stage.process(_context([]))


@pytest.mark.asyncio
async def test_factual_request_without_evidence_abstains_without_calling_the_model() -> None:
    llm = _LLM({"response": "Unsupported claim."})
    stage = LLMGenerationStage(llm=llm)
    context = _context([])
    context.intent_result = IntentResult(
        intents=[ChatIntent.LORE],
        confidence=0.9,
        routing_method="test",
    )

    result = await stage.process(context)

    assert "chưa có đủ bằng chứng" in result.chisa_reply
    assert result.citation_ids == []
    assert result.tool_res["grounding"]["status"] == "abstained_missing_evidence"
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_grounded_claim_is_accepted_only_when_cited_evidence_supports_it() -> None:
    evidence = _evidence().model_copy(
        update={"text": "Jinhsi is the magistrate of Jinzhou."}
    )
    stage = LLMGenerationStage(
        llm=_LLM(
            {
                "response": "Jinhsi is magistrate of Jinzhou.",
                "citations": ["lore:approved"],
            }
        )
    )

    result = await stage.process(_factual_context([evidence]))

    assert result.tool_res["grounding"] == {
        "status": "verified",
        "verified_claims": 1,
        "unsupported_claims": 0,
        "minimum_claim_score": 1.0,
    }


@pytest.mark.asyncio
async def test_unsupported_factual_claim_is_rejected_even_with_a_valid_citation_id() -> None:
    evidence = _evidence().model_copy(
        update={"text": "Jinhsi is the magistrate of Jinzhou."}
    )
    stage = LLMGenerationStage(
        llm=_LLM(
            {
                "response": "Jinhsi lives in Black Shores.",
                "citations": ["lore:approved"],
            }
        )
    )

    with pytest.raises(LLMInvalidResponseError, match="grounding checks"):
        await stage.process(_factual_context([evidence]))


@pytest.mark.asyncio
async def test_numeric_claim_requires_the_same_number_in_cited_evidence() -> None:
    evidence = _evidence().model_copy(update={"text": "Jinhsi has 1 verified title."})
    stage = LLMGenerationStage(
        llm=_LLM(
            {
                "response": "Jinhsi has 2 verified titles.",
                "citations": ["lore:approved"],
            }
        )
    )

    with pytest.raises(LLMInvalidResponseError, match="grounding checks"):
        await stage.process(_factual_context([evidence]))


@pytest.mark.asyncio
async def test_streaming_unsupported_claim_is_rejected_before_any_token_reaches_sink() -> None:
    evidence = _evidence().model_copy(
        update={"text": "Jinhsi is the magistrate of Jinzhou."}
    )
    emitted: list[str] = []
    context = _factual_context([evidence])
    context.on_token = emitted.append
    stage = LLMGenerationStage(
        llm=_StreamingLLM(
            {
                "response": "Jinhsi lives in Black Shores.",
                "citations": ["lore:approved"],
            }
        )
    )

    with pytest.raises(LLMInvalidResponseError, match="grounding checks"):
        await stage.process(context)

    assert emitted == []
