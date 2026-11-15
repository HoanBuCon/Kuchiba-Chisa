"""One v2 chat turn as typed events: mode, retrieval, Composer, persistence (ADV-001, ADV-009)."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.domain.entities.emotion import EmotionState
from app.domain.ingestion.entity_linking import EntityLinker
from app.domain.interfaces.llm_provider import LLMCallBudget
from app.domain.interfaces.observability import (
    CounterSignal,
    IOperationalTelemetry,
    NoopOperationalTelemetry,
    TelemetryDimensions,
)
from app.domain.interfaces.personal_context import IPersonalContext, PersonalContext
from app.domain.interfaces.threads import (
    IThreadStore,
    IThreadSummaryStore,
    ITurnCommit,
    ITurnLock,
)
from app.domain.models.evidence import Evidence
from app.domain.models.thread import (
    ChatMode,
    ModeDecision,
    Thread,
    ThreadSummary,
    TurnRecord,
    resolve_mode,
)
from app.domain.services.chisa_voice import INPUT_BLOCKED
from app.domain.services.conversation_window import (
    UNCOVERED_FETCH_LIMIT,
    TokenCounter,
    require_trigger_below_budget,
    summary_due,
    turn_tokens,
    window_turns,
)
from app.domain.services.guardrails.injection_guard import (
    ContentSource,
    GuardAction,
    InjectionGuard,
)
from app.domain.services.guardrails.pii_redaction import PiiRedactor
from app.domain.services.guardrails.safety_boundaries import apply_boundaries
from app.domain.services.knowledge.advanced_retrieval import AdvancedEvidence
from app.domain.services.knowledge.composer import ComposedAnswer
from app.domain.services.knowledge.lane_router import CHISA, Lane, choose_lane
from app.domain.services.knowledge.understanding import (
    IQuestionUnderstander,
    PriorTurn,
    UnderstandingError,
)
from app.domain.services.state_manager import StateManager
from app.shared.utils.token_estimator import TokenEstimator

# The understanding step and the Composer; a turn never spends a third call (ADV-009).
ADVANCED_MAX_LLM_CALLS = 2
ADVANCED_DEADLINE_SECONDS = 30.0
HISTORY_TOKEN_BUDGET = 1_500
SUMMARY_TRIGGER_TOKENS = 1_200
UNDERSTANDING_TURNS = 2
DEGRADED_UNDERSTANDING = "understanding_failed"
EVENT_STARTED = "turn.started"
EVENT_EVIDENCE = "evidence.added"
EVENT_TOKEN = "token"
EVENT_COMPLETED = "turn.completed"
EVENT_FAILED = "turn.failed"
STATUS_INPUT_BLOCKED = "input_blocked"
STATUS_BOUNDARY_REFUSED = "boundary_refused"
# Keeps the whitespace, so the deltas of a turn join back into its exact text.
_SENTENCE = re.compile(r"(?<=[.!?]\s)")


class ThreadBusyError(RuntimeError):
    """Another turn is still running in this thread (MODE-005)."""


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
    # Set for bots, which keep no thread id: the same channel always means the same thread.
    channel_thread_id: UUID | None = None


@dataclass(frozen=True)
class TurnEvent:
    type: str
    data: dict[str, Any]


class IEvidenceFlow(Protocol):
    async def retrieve(
        self,
        question: str,
        budget: LLMCallBudget | None = None,
        *,
        english: str | None = None,
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


def _worth_remembering(request: TurnRequest, record: TurnRecord) -> bool:
    """Guests have no long-term memory, and only conversation carries facts about the person."""
    return not request.is_guest and record.lane == Lane.COMPANION.value


@dataclass(frozen=True)
class _Conversation:
    """The thread so far: turns the summary lacks, the part of them that fits, and the summary."""

    uncovered: list[TurnRecord]
    uncovered_tokens: int
    history: list[TurnRecord]
    summary: ThreadSummary | None


@dataclass(frozen=True)
class _TurnPlan:
    lane: Lane
    english: str | None = None
    degraded: tuple[str, ...] = ()


def _only_chisa(entities: Sequence[str]) -> bool:
    return all(entity == CHISA for entity in entities)


def _bounded(message: str, answer: ComposedAnswer) -> ComposedAnswer:
    """A refused reply keeps no sentiment, so it cannot move Chisa's emotions (EMO-002)."""
    check = apply_boundaries(message, answer.text)
    if check.replaced:
        return ComposedAnswer(check.text, abstained=False, status=STATUS_BOUNDARY_REFUSED)
    return replace(answer, text=check.text)


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
        understander: IQuestionUnderstander | None = None,
        commit: ITurnCommit | None = None,
        lock: ITurnLock | None = None,
        summaries: IThreadSummaryStore | None = None,
        history_token_budget: int = HISTORY_TOKEN_BUDGET,
        summary_trigger_tokens: int = SUMMARY_TRIGGER_TOKENS,
        count_tokens: TokenCounter = TokenEstimator.estimate,
        telemetry: IOperationalTelemetry | None = None,
    ) -> None:
        self._threads = threads
        self._flow = flow
        self._composer = composer
        self._injection_guard = injection_guard or InjectionGuard()
        self._pii = pii or PiiRedactor()
        self._personal = personal
        self._linker = linker
        self._understander = understander
        self._commit = commit
        self._lock = lock
        if summaries is not None:
            require_trigger_below_budget(history_token_budget, summary_trigger_tokens)
        self._summaries = summaries
        self._history_budget = history_token_budget
        self._summary_trigger = summary_trigger_tokens
        self._count_tokens: Callable[[str], int] = count_tokens
        self._telemetry = telemetry or NoopOperationalTelemetry()

    async def run(self, request: TurnRequest) -> AsyncIterator[TurnEvent]:
        thread = await self._thread(request)
        token = await self._lock.acquire(thread.id) if self._lock else None
        if self._lock and token is None:
            raise ThreadBusyError(str(thread.id))
        try:
            async for event in self._run_locked(request, thread):
                yield event
        finally:
            if self._lock and token:
                await self._lock.release(thread.id, token)

    async def _run_locked(self, request: TurnRequest, thread: Thread) -> AsyncIterator[TurnEvent]:
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
        budget = LLMCallBudget.with_deadline(
            max_calls=ADVANCED_MAX_LLM_CALLS, timeout_seconds=ADVANCED_DEADLINE_SECONDS
        )
        if blocked:
            yield self._started(request, thread, decision, Lane.ADVANCED)
            refused = ComposedAnswer(INPUT_BLOCKED, abstained=True, status=STATUS_INPUT_BLOCKED)
            record = self._record(request, thread, decision, refused, (), budget, Lane.ADVANCED)
            await self._threads.save_turn(record)
            yield await self._completed(request.owner, record, replayed=False)
            return
        conversation = await self._conversation(thread.id)
        plan = await self._plan(request, conversation.history, budget)
        yield self._started(request, thread, decision, plan.lane)
        if plan.lane is Lane.COMPANION:
            companion = await self._companion(request, conversation, budget)
            answer = _bounded(request.message, companion)
            record = self._record(request, thread, decision, answer, (), budget, Lane.COMPANION)
            async for event in self._deliver(request, record, answer, conversation):
                yield event
            return
        found = await self._flow.retrieve(request.message, budget, english=plan.english)
        degraded = (*plan.degraded, *found.degraded)
        for item in found.evidence:
            yield TurnEvent(
                EVENT_EVIDENCE,
                {
                    "evidence_id": item.evidence_id,
                    "source_kind": item.provenance.source_type,
                    "title": item.provenance.source_id,
                },
            )
        composed = await self._compose(request, conversation, found, budget)
        answer = _bounded(request.message, composed)
        record = self._record(request, thread, decision, answer, degraded, budget, Lane.ADVANCED)
        async for event in self._deliver(request, record, answer, conversation):
            yield event

    async def _conversation(self, thread_id: UUID) -> _Conversation:
        summary = await self._summaries.get(thread_id) if self._summaries else None
        uncovered = await self._threads.recent_turns(
            thread_id,
            UNCOVERED_FETCH_LIMIT,
            after_turn=summary.covered_turn_id if summary else None,
        )
        # Counted once here: the window and the summary trigger both read these costs.
        costs = [turn_tokens(turn, self._count_tokens) for turn in uncovered]
        history = window_turns(uncovered, costs, self._history_budget)
        return _Conversation(uncovered, sum(costs), history, summary)

    async def _deliver(
        self,
        request: TurnRequest,
        record: TurnRecord,
        answer: ComposedAnswer,
        conversation: _Conversation,
    ) -> AsyncIterator[TurnEvent]:
        await self._store(request, record, answer, conversation)
        for piece in _SENTENCE.split(answer.text):
            yield TurnEvent(EVENT_TOKEN, {"delta": piece})
        yield await self._completed(request.owner, record, replayed=False)

    async def _store(
        self,
        request: TurnRequest,
        record: TurnRecord,
        answer: ComposedAnswer,
        conversation: _Conversation,
    ) -> None:
        if self._commit is not None:
            await self._commit.commit(
                record,
                request.owner,
                answer.sentiment,
                remember=_worth_remembering(request, record),
                summary_version=self._summary_version(request, record, conversation),
            )
            return
        stored = await self._threads.save_turn(record)
        # Only the retry that stored the turn may move emotion, so it moves once (EMO-003).
        if stored is not False and answer.sentiment and self._personal is not None:
            await self._personal.apply_sentiment(request.owner, answer.sentiment)

    def _summary_version(
        self, request: TurnRequest, record: TurnRecord, conversation: _Conversation
    ) -> int | None:
        """The stored summary version when one is due; guests have no users row for the job."""
        if self._summaries is None or request.is_guest:
            return None
        due = summary_due(
            len(conversation.uncovered),
            conversation.uncovered_tokens,
            turn_tokens(record, self._count_tokens),
            self._summary_trigger,
        )
        if not due:
            return None
        return conversation.summary.version if conversation.summary else 0

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

    async def _plan(
        self, request: TurnRequest, history: list[TurnRecord], budget: LLMCallBudget
    ) -> _TurnPlan:
        entities = self._linker.link(request.message) if self._linker is not None else ()
        lane = choose_lane(request.message, entities)
        # Rules that are sure of the lane leave nothing for the understander to decide (ADV-003).
        if lane is Lane.COMPANION or self._understander is None:
            if lane is Lane.COMPANION:
                self._count_understanding("skipped_rules")
            return _TurnPlan(lane)
        recent = history[-UNDERSTANDING_TURNS:]
        previous = [PriorTurn(turn.question, turn.answer) for turn in recent]
        try:
            understood = await self._understander.understand(request.message, previous, budget)
        except UnderstandingError:
            # The message itself is the query, so retrieval does not spend a second call.
            return _TurnPlan(lane, request.message, (DEGRADED_UNDERSTANDING,))
        if understood.lane is Lane.COMPANION and _only_chisa(entities):
            return _TurnPlan(Lane.COMPANION)
        # A lore question sent to companion would be answered from nothing, so it stays grounded.
        if understood.lane is Lane.COMPANION:
            self._count_understanding("overridden")
        return _TurnPlan(Lane.ADVANCED, understood.query or request.message)

    def _count_understanding(self, outcome: str) -> None:
        self._telemetry.count(
            CounterSignal.QUESTION_UNDERSTANDING, TelemetryDimensions(outcome=outcome)
        )

    async def _companion(
        self, request: TurnRequest, conversation: _Conversation, budget: LLMCallBudget
    ) -> ComposedAnswer:
        personal = await self._personal_context(request)
        return await self._composer.compose_companion(
            request.message,
            emotion=personal.emotion,
            history=_history(conversation.history),
            memories=list(personal.memories),
            summary=conversation.summary.summary if conversation.summary else None,
            budget=budget,
        )

    async def _thread(self, request: TurnRequest) -> Thread:
        if request.thread_id is None and request.channel_thread_id is not None:
            return await self._threads.get_or_create(
                request.channel_thread_id, request.owner, request.channel, ChatMode.ADVANCED
            )
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
        conversation: _Conversation,
        found: AdvancedEvidence,
        budget: LLMCallBudget,
    ) -> ComposedAnswer:
        if found.listed:
            return self._composer.compose_list(found.listed)
        personal = await self._personal_context(request)
        return await self._composer.compose(
            request.message,
            () if found.abstain else found.evidence,
            emotion=personal.emotion,
            history=_history(conversation.history),
            memories=list(personal.memories),
            summary=conversation.summary.summary if conversation.summary else None,
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
