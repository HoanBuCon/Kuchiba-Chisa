"""`/api/v2` chat turns and threads, behind CHAT_V2_ENABLED while v1 keeps running (section 8.1)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.chat_turns import (
    EVENT_COMPLETED,
    EVENT_FAILED,
    EVENT_TOKEN,
    ThreadBusyError,
    ThreadNotFoundError,
    TurnRequest,
)
from app.application.dependencies import (
    get_chat_turn_runtime,
    get_entity_image_service,
    get_memory_policy_service,
)
from app.application.entity_images import EntityImageService, InvalidImageLinkError
from app.config.settings import settings
from app.domain.interfaces.llm_provider import LLMError
from app.domain.models.thread import ChatMode, Thread, TurnRecord, channel_thread_id
from app.domain.services.chisa_voice import TURN_BUSY, TURN_FAILED
from app.domain.services.core_memory import CoreMemory
from app.domain.services.guardrails.pii_redaction import PiiRedactor
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.database.engine import get_db_session
from app.interface.api.dependencies.chat_admission import Admission, admit_chat
from app.interface.api.dependencies.security import require_scope
from app.interface.middlewares.observability import mark_stream_first_token
from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str

router = APIRouter(tags=["Chat v2"])
Writer = Annotated[PrincipalContext, Depends(require_scope("chat:write"))]
MAX_MESSAGE_CHARS = 4000
SHA256_PATTERN = r"^[0-9a-f]{64}$"
MAX_TITLE_CHARS = 255
THREAD_LIST_LIMIT = 50
THREAD_TURNS_LIMIT = 50
STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
ACCOUNT_AUTHENTICATION = "account"
ANONYMOUS_AUTHENTICATION = "anonymous"
WORKLOAD_KIND = "workload"
PII_REDACTOR = PiiRedactor()
# The service stores a turn before it streams the first token, so either event proves storage.
STORED_EVENTS = frozenset({EVENT_TOKEN, EVENT_COMPLETED})


class TurnBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    turn_id: UUID
    thread_id: UUID | None = None
    mode_override: ChatMode | None = None


class ThreadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ChatMode = ChatMode.ADVANCED


class ThreadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_CHARS)
    mode: ChatMode | None = None


class ThreadView(BaseModel):
    id: UUID
    channel: str
    mode: ChatMode
    title: str | None


class TurnView(BaseModel):
    turn_id: UUID
    question: str
    answer: str
    lane: str
    status: str
    citations: list[dict[str, Any]]


class _QuotaCharge:
    """One quota reservation that is refunded at most once, and never once the turn is stored."""

    def __init__(self, admission: Any, reservation: Any) -> None:
        self._admission = admission
        self._reservation = reservation
        self._stored = False
        self._refunded = False

    def keep(self) -> None:
        self._stored = True

    async def refund(self) -> None:
        if self._refunded:
            return
        self._refunded = True
        await self._admission.refund(self._reservation)

    async def refund_unless_kept(self) -> None:
        if self._stored:
            return
        # Shielded so the cancellation that brought us here cannot cut the refund short.
        await asyncio.shield(self.refund())


def _view(thread: Thread) -> ThreadView:
    return ThreadView(id=thread.id, channel=thread.channel, mode=thread.mode, title=thread.title)


def _turn_view(turn: TurnRecord) -> TurnView:
    return TurnView(
        turn_id=turn.turn_id,
        question=turn.question,
        answer=turn.answer,
        lane=turn.lane,
        status=turn.status,
        citations=list(turn.citations),
    )


def _owner(principal: PrincipalContext) -> str:
    """The same identity erasure and consent use, so they reach everything stored here."""
    return normalize_user_id_str(principal.subject_id)


def _bot_thread(principal: PrincipalContext) -> UUID | None:
    if principal.kind != WORKLOAD_KIND or not principal.channel_id:
        return None
    return channel_thread_id(_owner(principal), principal.tenant_id, principal.channel_id)


def _require_member(principal: PrincipalContext) -> None:
    """Guests have no long-term memory, so they have no memory to manage (MEM-007)."""
    if principal.authentication != ACCOUNT_AUTHENTICATION:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account required")


def _enabled() -> None:
    if not settings.CHAT_V2_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/turns", dependencies=[Depends(_enabled)])
async def create_turn(
    body: TurnBody, http_request: Request, principal: Writer, admission: Admission
) -> StreamingResponse:
    reservation = await admit_chat(admission, principal, http_request)
    runtime = await get_chat_turn_runtime()
    request = TurnRequest(
        owner=_owner(principal),
        channel=principal.source,
        message=body.message,
        turn_id=body.turn_id,
        thread_id=body.thread_id,
        mode_override=body.mode_override,
        # Bot users keep the long-term memory they have on v1; consent still decides per person.
        is_guest=principal.authentication == ANONYMOUS_AUTHENTICATION,
        channel_thread_id=_bot_thread(principal),
    )
    if (
        body.thread_id is not None
        and await runtime.threads.get(body.thread_id, _owner(principal)) is None
    ):
        raise _not_found()

    charge = _QuotaCharge(admission, reservation)

    async def events() -> AsyncIterator[str]:
        try:
            async for event in runtime.turns.run(request):
                if event.type in STORED_EVENTS:
                    charge.keep()
                if event.type == EVENT_TOKEN:
                    mark_stream_first_token(http_request.scope)
                if event.type == EVENT_COMPLETED and event.data.get("replayed"):
                    # A replay spends nothing, so it is not charged (REL-003, REL-007).
                    await charge.refund()
                yield _sse(event.type, event.data)
        except (LLMError, ThreadNotFoundError, ThreadBusyError) as error:
            await charge.refund()
            busy = isinstance(error, ThreadBusyError)
            # Only a bounded class name leaves the server; the message is a voice constant.
            yield _sse(
                EVENT_FAILED,
                {"code": type(error).__name__, "message": TURN_BUSY if busy else TURN_FAILED},
            )
        except (asyncio.CancelledError, GeneratorExit):
            # The client left; a turn that was never stored gave it nothing to keep (REL-007).
            await charge.refund_unless_kept()
            raise

    return StreamingResponse(events(), media_type="text/event-stream", headers=STREAM_HEADERS)


@router.get("/images/{sha256}", dependencies=[Depends(_enabled)])
async def get_entity_image(
    sha256: Annotated[str, Path(pattern=SHA256_PATTERN)],
    expires: int,
    sig: str,
    service: Annotated[EntityImageService, Depends(get_entity_image_service)],
    original: bool = False,
) -> Response:
    """Authorised by the signature alone, because an img tag cannot send a bearer token."""
    try:
        served = service.serve(sha256, original=original, expires=expires, signature=sig)
    except InvalidImageLinkError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid or expired image link") from None
    except FileNotFoundError:
        raise _not_found() from None
    headers = {"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"}
    return Response(served.content, media_type=served.mime, headers=headers)


@router.get("/threads", dependencies=[Depends(_enabled)])
async def list_threads(principal: Writer) -> list[ThreadView]:
    runtime = await get_chat_turn_runtime()
    threads = await runtime.threads.list_for(_owner(principal), THREAD_LIST_LIMIT)
    return [_view(thread) for thread in threads]


@router.post("/threads", dependencies=[Depends(_enabled)], status_code=status.HTTP_201_CREATED)
async def create_thread(body: ThreadCreate, principal: Writer) -> ThreadView:
    _require_member(principal)
    runtime = await get_chat_turn_runtime()
    return _view(await runtime.threads.create(_owner(principal), principal.source, body.mode))


@router.get("/threads/{thread_id}/turns", dependencies=[Depends(_enabled)])
async def list_thread_turns(thread_id: UUID, principal: Writer) -> list[TurnView]:
    runtime = await get_chat_turn_runtime()
    # The store reads turns by thread alone, so ownership is settled here first.
    if await runtime.threads.get(thread_id, _owner(principal)) is None:
        raise _not_found()
    turns = await runtime.threads.recent_turns(thread_id, THREAD_TURNS_LIMIT)
    return [_turn_view(turn) for turn in turns]


@router.get("/threads/{thread_id}", dependencies=[Depends(_enabled)])
async def get_thread(thread_id: UUID, principal: Writer) -> ThreadView:
    runtime = await get_chat_turn_runtime()
    thread = await runtime.threads.get(thread_id, _owner(principal))
    if thread is None:
        raise _not_found()
    return _view(thread)


@router.patch("/threads/{thread_id}", dependencies=[Depends(_enabled)])
async def patch_thread(thread_id: UUID, body: ThreadPatch, principal: Writer) -> ThreadView:
    runtime = await get_chat_turn_runtime()
    # Clients title a thread from its first message, which turns only ever store masked.
    title = PII_REDACTOR.redact(body.title).value if body.title else None
    thread = await runtime.threads.update(thread_id, _owner(principal), title=title, mode=body.mode)
    if thread is None:
        raise _not_found()
    return _view(thread)


@router.delete(
    "/threads/{thread_id}",
    dependencies=[Depends(_enabled)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_thread(thread_id: UUID, principal: Writer) -> None:
    runtime = await get_chat_turn_runtime()
    if not await runtime.threads.delete(thread_id, _owner(principal)):
        raise _not_found()


@router.get("/me/memory/core", dependencies=[Depends(_enabled)])
async def get_core_memory(principal: Writer) -> CoreMemory:
    _require_member(principal)
    runtime = await get_chat_turn_runtime()
    return CoreMemory.model_validate(await runtime.core_memory.get(_owner(principal)) or {})


@router.put("/me/memory/core", dependencies=[Depends(_enabled)])
async def put_core_memory(
    body: CoreMemory,
    principal: Writer,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    memory_policy: Annotated[Any, Depends(get_memory_policy_service)],
) -> CoreMemory:
    _require_member(principal)
    policy = await memory_policy.get(session, normalize_user_id(principal.subject_id))
    if not policy.allows_long_term_memory:
        # Storing memory needs consent even when the person typed it (MEM-006).
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Memory is turned off")
    runtime = await get_chat_turn_runtime()
    await runtime.core_memory.put(_owner(principal), body.model_dump())
    return body


@router.delete(
    "/me/memory/core",
    dependencies=[Depends(_enabled)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_core_memory(principal: Writer) -> None:
    _require_member(principal)
    runtime = await get_chat_turn_runtime()
    await runtime.core_memory.delete(_owner(principal))
