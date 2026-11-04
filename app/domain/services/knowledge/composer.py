"""Grounded Composer: Chisa's only voice, reusing the protected prompts in place (PER-001)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.domain.entities.emotion import EmotionState
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.llm_provider import (
    BaseLLMAdapter,
    LLMCallBudget,
    LLMPurpose,
    StructuredPrompt,
)
from app.domain.models.evidence import Evidence
from app.domain.services.budget_mode import BudgetMode
from app.domain.services.chisa_voice import (
    COMPANION_ADDRESS_NOTE,
    GROUNDED_ABSTENTION,
    GROUNDED_ANSWER_LEAD,
    GROUNDED_EXTRACTIVE_FRAME,
    GROUNDED_LIST_LEAD,
    GROUNDED_QUOTE_SOURCES,
    TURN_FAILED,
)
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.guardrails import (
    GroundedOutputAssembler,
    GroundedOutputValidationError,
    PromptLeakageGuard,
    build_grounded_response_schema,
)
from app.domain.services.knowledge.cross_language_claims import CrossLanguageClaimCheck

CONTRACT_NAME = "submit_grounded_answer"
ADDRESSING = "Senpai"
INTENT_NAME = "lore"
COMPANION_INTENT = "conversational"
# Same warmth the v1 path uses for casual talk.
COMPANION_TEMPERATURE = 0.8


@dataclass(frozen=True)
class CitationSnapshot:
    """Stored with the message, so history stays correct after a new release (GRD-005)."""

    evidence_id: str
    title_or_url: str
    source_kind: str
    corpus_version: str | None
    quote: str
    revision: int | None = None


@dataclass(frozen=True)
class ComposedAnswer:
    text: str
    abstained: bool
    citations: tuple[CitationSnapshot, ...] = ()
    sentiment: Mapping[str, Any] = field(default_factory=dict)
    # Machine-readable outcome: answered, no_evidence, invalid_output or output_leakage.
    status: str = "answered"


def _snapshots(ids: Sequence[str], evidence: Sequence[Evidence]) -> tuple[CitationSnapshot, ...]:
    by_id = {item.evidence_id: item for item in evidence}
    return tuple(
        CitationSnapshot(
            evidence_id=item.evidence_id,
            title_or_url=item.provenance.source_id,
            source_kind=item.provenance.source_type,
            corpus_version=item.provenance.source_version,
            quote=item.text,
            revision=item.provenance.source_revision,
        )
        for item in (by_id[evidence_id] for evidence_id in ids if evidence_id in by_id)
    )


def _in_chisa_voice(text: str) -> str:
    """A reply that already addresses Senpai keeps its wording; quote frames always do."""
    return text if ADDRESSING in text else f"{GROUNDED_ANSWER_LEAD}{text}"


def _quote_sources(ids: Sequence[str], evidence: Sequence[Evidence]) -> str:
    by_id = {item.evidence_id: item for item in evidence}
    titles = dict.fromkeys(
        title for title in (by_id[i].provenance.source_title for i in ids if i in by_id) if title
    )
    return GROUNDED_QUOTE_SOURCES.format(titles=", ".join(titles)) if titles else ""


def _abstained(status: str) -> ComposedAnswer:
    return ComposedAnswer(GROUNDED_ABSTENTION, abstained=True, status=status)


class GroundedComposer:
    def __init__(
        self,
        llm: BaseLLMAdapter,
        builder: ContextBuilder,
        assembler: GroundedOutputAssembler | None = None,
        leakage_guard: PromptLeakageGuard | None = None,
        embedder: IEmbeddingProvider | None = None,
    ) -> None:
        self._llm = llm
        self._builder = builder
        self._assembler = assembler or GroundedOutputAssembler()
        self._leakage_guard = leakage_guard or PromptLeakageGuard()
        self._embedder = embedder

    def compose_list(self, listed: Sequence[Evidence]) -> ComposedAnswer:
        """An exact lookup needs no LLM: nothing can be invented, and a call is saved."""
        lines = (f"- {item.text.splitlines()[0]}" for item in listed)
        return ComposedAnswer(
            text="\n".join((GROUNDED_LIST_LEAD, *lines)),
            abstained=False,
            citations=_snapshots([item.evidence_id for item in listed], listed),
            status="listed",
        )

    async def compose(
        self,
        question: str,
        evidence: Sequence[Evidence],
        *,
        emotion: EmotionState,
        history: list[dict[str, str]],
        memories: list[str],
        summary: str | None,
        budget: LLMCallBudget,
    ) -> ComposedAnswer:
        """No evidence means no LLM call: a reply with nothing to bind to could only invent."""
        if not evidence:
            return _abstained("no_evidence")
        prompt = self._prompt(question, evidence, emotion, history, memories, summary, budget)
        response = await self._llm.generate(prompt)
        check = await self._claim_check(response.parsed)
        try:
            envelope = self._assembler.assemble(
                payload=response.parsed,
                evidence=prompt.retrieved_evidence,
                abstention_answer=GROUNDED_ABSTENTION,
                extractive_frame=GROUNDED_EXTRACTIVE_FRAME,
                # A second frame mid-answer reads as Chisa repeating herself.
                gather_quotes=True,
                claim_check=check,
            )
        except (GroundedOutputValidationError, ValueError):
            return _abstained("invalid_output")
        leak = self._leakage_guard.inspect(
            prompt.system,
            envelope.answer,
            allowed_source_texts=[item.text for item in prompt.retrieved_evidence],
        )
        if leak.leaked:
            return _abstained("output_leakage")
        if envelope.abstained:
            return _abstained("no_evidence")
        sources = (
            _quote_sources(envelope.citations, prompt.retrieved_evidence)
            if envelope.extractive_claims
            else ""
        )
        return ComposedAnswer(
            text=_in_chisa_voice(envelope.presented_answer or envelope.answer) + sources,
            abstained=False,
            citations=_snapshots(envelope.citations, prompt.retrieved_evidence),
            sentiment=response.parsed.get("sentiment", {}),
        )

    async def _claim_check(self, parsed: Mapping[str, Any]) -> CrossLanguageClaimCheck | None:
        """Quotes may need resolving against the source, so both forms of each pair are prepared."""
        claims = parsed.get("claims")
        if self._embedder is None or not isinstance(claims, list):
            return None
        pairs = [
            (claim["text"], claim["evidence_quote"])
            for claim in claims
            if isinstance(claim, dict)
            and isinstance(claim.get("text"), str)
            and isinstance(claim.get("evidence_quote"), str)
        ]
        return await CrossLanguageClaimCheck.prepare(self._embedder, pairs)

    async def compose_companion(
        self,
        question: str,
        *,
        emotion: EmotionState,
        history: list[dict[str, str]],
        memories: list[str],
        summary: str | None,
        budget: LLMCallBudget,
    ) -> ComposedAnswer:
        """Conversation in Chisa's own voice; no retrieval and no claims to bind (MODE-008)."""
        built = self._builder.build(
            emotion=emotion,
            attachment_bonus=0.0,
            memories=memories,
            lore=[],
            history=history,
            user_message=question,
            intent_name=COMPANION_INTENT,
            conversation_summary=summary,
            budget_mode=BudgetMode.SMALL_TALK,
            is_small_talk=True,
        ).prompt
        prompt = built.model_copy(
            update={
                # Added here so the protected persona prompts stay verbatim (CON-001).
                "system": f"{built.system}\n\n{COMPANION_ADDRESS_NOTE}",
                "temperature": COMPANION_TEMPERATURE,
                "purpose": LLMPurpose.CHAT_RESPONSE,
                "call_budget": budget,
            }
        )
        response = await self._llm.generate(prompt)
        text = response.parsed.get("response")
        if not isinstance(text, str) or not text.strip():
            return ComposedAnswer(TURN_FAILED, abstained=True, status="invalid_output")
        if self._leakage_guard.inspect(prompt.system, text, allowed_source_texts=[]).leaked:
            return ComposedAnswer(TURN_FAILED, abstained=True, status="output_leakage")
        return ComposedAnswer(
            text=text,
            abstained=False,
            sentiment=response.parsed.get("sentiment", {}),
            status="companion",
        )

    def _prompt(
        self,
        question: str,
        evidence: Sequence[Evidence],
        emotion: EmotionState,
        history: list[dict[str, str]],
        memories: list[str],
        summary: str | None,
        budget: LLMCallBudget,
    ) -> StructuredPrompt:
        built = self._builder.build(
            emotion=emotion,
            attachment_bonus=0.0,
            memories=memories,
            lore=[item.text for item in evidence],
            history=history,
            user_message=question,
            intent_name=INTENT_NAME,
            conversation_summary=summary,
            budget_mode=BudgetMode.RAG,
            evidence=list(evidence),
        ).prompt
        sentiment = built.response_schema.get("properties", {}).get("sentiment")
        if not isinstance(sentiment, dict):
            raise RuntimeError("Grounded generation requires the sentiment schema")
        return built.model_copy(
            update={
                "response_schema": build_grounded_response_schema(
                    evidence_ids=[item.evidence_id for item in built.retrieved_evidence],
                    sentiment_schema=sentiment,
                ),
                "output_contract_name": CONTRACT_NAME,
                "temperature": 0.0,
                "purpose": LLMPurpose.CHAT_RESPONSE,
                "call_budget": budget,
            }
        )
