"""One v2 chat turn as typed events: mode, retrieval, Composer, persistence (ADV-001, ADV-009)."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.domain.entities.emotion import EmotionState
from app.domain.ingestion.entity_linking import EntityLinker
from app.domain.interfaces.llm_provider import LLMCallBudget
from app.domain.interfaces.personal_context import IPersonalContext, PersonalContext
from app.domain.interfaces.threads import IThreadStore
from app.domain.models.evidence import Evidence
from app.domain.models.thread import ChatMode, ModeDecision, Thread, TurnRecord, resolve_mode
from app.domain.services.chisa_voice import INPUT_BLOCKED
from app.domain.services.guardrails.injection_guard import (
    ContentSource,
    GuardAction,
    InjectionGuard,
)
from app.domain.services.guardrails.pii_redaction import PiiRedactor
from app.domain.services.knowledge.advanced_retrieval import AdvancedEvidence
from app.domain.services.knowledge.composer import ComposedAnswer
from app.domain.services.knowledge.lane_router import Lane, choose_lane
from app.domain.services.state_manager import StateManager

# The translation and the Composer; a turn never spends a third call (ADV-009).
ADVANCED_MAX_LLM_CALLS = 2
ADVANCED_DEADLINE_SECONDS = 30.0
HISTORY_TURNS = 6
EVENT_STARTED = "turn.started"
EVENT_EVIDENCE = "evidence.added"
EVENT_TOKEN = "token"
EVENT_COMPLETED = "turn.completed"
EVENT_FAILED = "turn.failed"
STATUS_INPUT_BLOCKED = "input_blocked"
# Keeps the whitespace, so the deltas of a turn join back into its exact text.
_SENTENCE = re.compile(r"(?<=[.!?]\s)")


class ThreadNotFoundError(LookupError):
    """The thread is missing or belongs to someone else; the two are not told apart."""


@dataclass(frozen=True)
class TurnRequest:
    owner: str
    channel: str
    message: str
    turn_id: UUID
    thread_id: UUID | None = None
    mode_override: ChatMode | None = None
    can_use_agentic: bool = False
    is_guest: bool = True


@dataclass(frozen=True)
class TurnEvent:
    type: str
    data: dict[str, Any]


class IEvidenceFlow(Protocol):
    async def retrieve(
        self, question: str, budget: LLMCallBudget | None = None
    ) -> AdvancedEvidence: ...


class IAnswerComposer(Protocol):
    async def compose_companion(
        self,
        question: str,
        *,
        emotion: EmotionState,
        history: list[dict[str, str]],
        memories: list[str],
        summary: str | None,
        budget: LLMCallBudget,
    ) -> ComposedAnswer: ...

    def compose_list(self, listed: Sequence[Evidence]) -> ComposedAnswer: ...

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
    ) -> ComposedAnswer: ...


def _history(turns: list[TurnRecord]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in turns:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.answer})
    return messages


class AdvancedTurnService:
    """Agentic does not exist yet, so the mode is decided here and always clamps to Advanced."""

    def __init__(
        self,
        threads: IThreadStore,
        flow: IEvidenceFlow,
        composer: IAnswerComposer,
        *,
        injection_guard: InjectionGuard | None = None,
        pii: PiiRedactor | None = None,
        personal: IPersonalContext | None = None,
        linker: EntityLinker | None = None,
    ) -> None:
        self._threads = threads
        self._flow = flow
        self._composer = composer
        self._injection_guard = injection_guard or InjectionGuard()
        self._pii = pii or PiiRedactor()
        self._personal = personal
        self._linker = linker

    async def run(self, request: TurnRequest) -> AsyncIterator[TurnEvent]:
        thread = await self._thread(request)
        existing = await self._threads.find_turn(thread.id, request.turn_id)
        if existing is not None:
            # A retried request must not spend LLM calls or store the exchange twice.
            yield await self._completed(request.owner, existing, replayed=True)
            return
        decision = resolve_mode(
            override=request.mode_override,
            thread_mode=thread.mode,
            account_default=None,
            can_use_agentic=request.can_use_agentic,
        )
        # Everything below reaches providers or storage, so it sees only the masked text.
        request = replace(request, message=self._pii.redact(request.message).value)
        assessment = self._injection_guard.assess(request.message, ContentSource.USER)
        blocked = assessment.action is GuardAction.BLOCK
        lane = Lane.ADVANCED if blocked else self._lane(request.message)
        yield self._started(request, thread, decision, lane)
        budget = LLMCallBudget.with_deadline(
            max_calls=ADVANCED_MAX_LLM_CALLS, timeout_seconds=ADVANCED_DEADLINE_SECONDS
        )
        if blocked:
            refused = ComposedAnswer(INPUT_BLOCKED, abstained=True, status=STATUS_INPUT_BLOCKED)
            record = self._record(request, thread, decision, refused, (), budget, Lane.ADVANCED)
            await self._threads.save_turn(record)
            yield await self._completed(request.owner, record, replayed=False)
            return
        if lane is Lane.COMPANION:
            answer = await self._companion(request, thread, budget)
            record = self._record(request, thread, decision, answer, (), budget, Lane.COMPANION)
            async for event in self._deliver(request, record, answer):
                yield event
            return
        found = await self._flow.retrieve(request.message, budget)
        for item in found.evidence:
            yield TurnEvent(
                EVENT_EVIDENCE,
                {
                    "evidence_id": item.evidence_id,
                    "source_kind": item.provenance.source_type,
                    "title": item.provenance.source_id,
                },
            )
        answer = await self._compose(request, thread, found, budget)
        record = self._record(
            request, thread, decision, answer, found.degraded, budget, Lane.ADVANCED
        )
        async for event in self._deliver(request, record, answer):
            yield event

    async def _deliver(
        self, request: TurnRequest, record: TurnRecord, answer: ComposedAnswer
    ) -> AsyncIterator[TurnEvent]:
        stored = await self._threads.save_turn(record)
        # Only the retry that stored the turn may move emotion, so it moves once (EMO-003).
        if stored is not False and answer.sentiment and self._personal is not None:
            await self._personal.apply_sentiment(request.owner, answer.sentiment)
        for piece in _SENTENCE.split(answer.text):
            yield TurnEvent(EVENT_TOKEN, {"delta": piece})
        yield await self._completed(request.owner, record, replayed=False)

    async def _completed(self, owner: str, record: TurnRecord, replayed: bool) -> TurnEvent:
        emotion = await self._personal.current_emotion(owner) if self._personal else None
        return TurnEvent(
            EVENT_COMPLETED,
            {
                "turn_id": str(record.turn_id),
                "thread_id": str(record.thread_id),
                "response": record.answer,
                "citations": list(record.citations),
                "status": record.status,
                "replayed": replayed,
                "emotions": emotion.values() if emotion else None,
                "emotion_caption": (
                    StateManager.get_emotion_summary_caption(emotion) if emotion else None
                ),
            },
        )

    def _lane(self, message: str) -> Lane:
        entities = self._linker.link(message) if self._linker is not None else ()
        return choose_lane(message, entities)

    async def _companion(
        self, request: TurnRequest, thread: Thread, budget: LLMCallBudget
    ) -> ComposedAnswer:
        recent = await self._threads.recent_turns(thread.id, HISTORY_TURNS)
        personal = await self._personal_context(request)
        return await self._composer.compose_companion(
            request.message,
            emotion=personal.emotion,
            history=_history(recent),
            memories=list(personal.memories),
            summary=None,
            budget=budget,
        )

    async def _thread(self, request: TurnRequest) -> Thread:
        if request.thread_id is None:
            return await self._threads.create(request.owner, request.channel, ChatMode.ADVANCED)
        thread = await self._threads.get(request.thread_id, request.owner)
        if thread is None:
            raise ThreadNotFoundError(str(request.thread_id))
        return thread

    @staticmethod
    def _started(
        request: TurnRequest, thread: Thread, decision: ModeDecision, lane: Lane
    ) -> TurnEvent:
        reason = decision.downgrade_reason
        return TurnEvent(
            EVENT_STARTED,
            {
                "turn_id": str(request.turn_id),
                "thread_id": str(thread.id),
                "mode_effective": decision.effective.value,
                "lane": lane.value,
                "downgrade_reason": reason.value if reason else None,
            },
        )

    async def _compose(
        self,
        request: TurnRequest,
        thread: Thread,
        found: AdvancedEvidence,
        budget: LLMCallBudget,
    ) -> ComposedAnswer:
        if found.listed:
            return self._composer.compose_list(found.listed)
        recent = await self._threads.recent_turns(thread.id, HISTORY_TURNS)
        personal = await self._personal_context(request)
        return await self._composer.compose(
            request.message,
            () if found.abstain else found.evidence,
            emotion=personal.emotion,
            history=_history(recent),
            memories=list(personal.memories),
            summary=None,
            budget=budget,
        )

    async def _personal_context(self, request: TurnRequest) -> PersonalContext:
        if self._personal is None:
            return PersonalContext(EmotionState(user_id=uuid4()))
        return await self._personal.load(
            request.owner, is_guest=request.is_guest, question=request.message
        )

    @staticmethod
    def _record(
        request: TurnRequest,
        thread: Thread,
        decision: ModeDecision,
        answer: ComposedAnswer,
        degraded: tuple[str, ...],
        budget: LLMCallBudget,
        lane: Lane,
    ) -> TurnRecord:
        return TurnRecord(
            thread_id=thread.id,
            turn_id=request.turn_id,
            question=request.message,
            answer=answer.text,
            mode_requested=decision.requested,
            mode_effective=decision.effective,
            lane=lane.value,
            status=answer.status,
            downgrade_reason=decision.downgrade_reason,
            llm_calls=budget.used_calls,
            citations=tuple(asdict(citation) for citation in answer.citations),
            degraded=degraded,
        )
