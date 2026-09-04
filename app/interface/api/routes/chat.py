import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dependencies import (
    get_chat_engine,
    get_clear_user_memory_use_case,
    get_memory_policy_service,
)
from app.application.security.authorization import AuthorizationError, AuthorizationPolicy
from app.domain.interfaces.llm_provider import (
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.domain.services.chat_engine import ChatEngine, ChatEngineBusyError
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.logging.logger import get_logger
from app.interface.api.dependencies.security import CurrentPrincipal, require_scope
from app.interface.api.schemas.chat import (
    ChatRequest,
    ChatResponse,
    MemoryConsentRequest,
    MemoryConsentResponse,
)
from app.shared.utils.circuit_breaker import CircuitBreakerError
from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str

log = get_logger(__name__)

router = APIRouter()


def _sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _prepare_chat_context(principal: PrincipalContext, http_request: Request) -> tuple[str, str]:
    """Uses verified identity for all user-scoped chat state."""
    from app.infrastructure.logging.llm_logger import enable_clean_log

    is_test = http_request.headers.get("X-Enable-Clean-Log") == "true"
    enable_clean_log.set(is_test)

    username = principal.display_name or ("Web Guest" if principal.source == "web" else "Unknown")
    normalized_user_id = normalize_user_id_str(principal.subject_id)
    return username, normalized_user_id


UserIdPath = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\:]+$")]


@router.get("/chat/me/memory-consent", response_model=MemoryConsentResponse)
async def get_memory_consent(
    principal: Annotated[PrincipalContext, Depends(require_scope("chat:write"))],
    session: AsyncSession = Depends(get_db_session),
    memory_policy_service=Depends(get_memory_policy_service),
) -> MemoryConsentResponse:
    """Read only the verified principal's long-term-memory preference."""
    policy = await memory_policy_service.get(session, normalize_user_id(principal.subject_id))
    return MemoryConsentResponse(
        enabled=policy.long_term_memory_enabled,
        retention_days=policy.retention_days,
        consented_at=policy.consented_at.isoformat() if policy.consented_at else None,
    )


@router.put("/chat/me/memory-consent", response_model=MemoryConsentResponse)
async def set_memory_consent(
    request: MemoryConsentRequest,
    principal: Annotated[PrincipalContext, Depends(require_scope("chat:write"))],
    session: AsyncSession = Depends(get_db_session),
    memory_policy_service=Depends(get_memory_policy_service),
) -> MemoryConsentResponse:
    """Persist explicit consent; revocation removes active long-term vector memory."""
    policy = await memory_policy_service.update(
        session,
        normalize_user_id(principal.subject_id),
        enabled=request.enabled,
        retention_days=request.retention_days,
    )
    await session.commit()
    return MemoryConsentResponse(
        enabled=policy.long_term_memory_enabled,
        retention_days=policy.retention_days,
        consented_at=policy.consented_at.isoformat() if policy.consented_at else None,
    )


def _start_chat_trace(
    principal: PrincipalContext, username: str | None, message: str
) -> str:
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    return pipeline_tracker.start_trace(
        user_id=principal.subject_id,
        message=message,
        pipeline="production",
        source=principal.source,
        username=username,
        channel_name=principal.channel_id,
        guild_name=principal.tenant_id,
    )


async def _run_chat_request(
    session: AsyncSession,
    message: str,
    original_user_id: str,
    normalized_user_id: str,
    chat_engine: ChatEngine,
    on_token: Callable[[str], Any] | None = None,
    images: list[str] | None = None,
    is_ephemeral_reference: bool = False,
) -> tuple[str, dict[str, Any] | None, bool, list, list, list[str]]:
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    try:
        execution = await chat_engine.chat_detailed(
            session=session,
            user_id=normalized_user_id,
            user_message=message,
            on_token=on_token,
            images=images,
            is_ephemeral_reference=is_ephemeral_reference,
        )
        reply_text = execution.reply_text
        emotions = execution.emotions
        images_processed = execution.images_processed
        attached_images = execution.attached_images
        citation_ids = execution.citation_ids
        loop_thinking_activated = pipeline_tracker.get_loop_thinking_activated()

        pipeline_tracker.end_trace(
            response_text=reply_text,
            emotions=emotions,
            status="success",
        )
        return (
            reply_text,
            emotions,
            loop_thinking_activated,
            images_processed,
            attached_images,
            citation_ids,
        )
    except LLMRateLimitError:
        fallback_text = "Chisa đang hơi bận một chút, Senpai chờ em thêm lát nữa nhé."
        fallback_emotions = None
        pipeline_tracker.end_trace(
            response_text=fallback_text,
            emotions=fallback_emotions,
            status="success",
            error=None,
        )
        return fallback_text, fallback_emotions, False, [], [], []
    except (LLMTimeoutError, LLMInvalidResponseError, CircuitBreakerError) as llm_err:
        fallback_text = "Chisa hơi mệt một chút, Senpai nhắn lại sau nhé ~"
        fallback_emotions = None
        log.warning(
            "LLM error, returning fallback",
            error=str(llm_err),
            user_id=original_user_id,
            normalized_user_id=normalized_user_id,
        )
        pipeline_tracker.end_trace(
            response_text=fallback_text,
            emotions=fallback_emotions,
            status="success",
            error=str(llm_err),
        )
        return fallback_text, fallback_emotions, False, [], [], []
    except Exception as error:
        pipeline_tracker.end_trace(
            status="failed",
            error=str(error),
        )
        raise


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    http_request: Request,
    principal: Annotated[PrincipalContext, Depends(require_scope("chat:write"))],
    session: AsyncSession = Depends(get_db_session),
    chat_engine: ChatEngine = Depends(get_chat_engine),
) -> ChatResponse:
    """
    Primary endpoint for User <-> AI interactions scoped by verified identity.
    """
    username, normalized_user_id = _prepare_chat_context(principal, http_request)
    message = request.message or ""
    log.info(
        "Received chat request",
        user_id=principal.subject_id,
        normalized_user_id=normalized_user_id,
        has_images=bool(request.images),
    )

    _start_chat_trace(principal, username, message)

    try:
        (
            reply_text,
            emotions,
            loop_thinking_activated,
            images_processed,
            attached_images,
            citation_ids,
        ) = await _run_chat_request(
            session=session,
            message=message,
            original_user_id=principal.subject_id,
            normalized_user_id=normalized_user_id,
            chat_engine=chat_engine,
            images=request.images,
            is_ephemeral_reference=bool(request.is_ephemeral_reference),
        )

        emotion_caption = None
        if emotions and isinstance(emotions, dict):
            from app.domain.entities.emotion import EmotionState
            from app.domain.services.state_manager import StateManager

            try:
                state_obj = EmotionState(
                    user_id=normalize_user_id(principal.subject_id),
                    trust=float(emotions.get("trust", 0.50)),
                    attachment=float(emotions.get("attachment", 0.00)),
                    joy=float(emotions.get("joy", 0.15)),
                    sadness=float(emotions.get("sadness", 0.00)),
                    irritation=float(emotions.get("irritation", 0.00)),
                    shyness=float(emotions.get("shyness", 0.00)),
                    curiosity=float(emotions.get("curiosity", 0.10)),
                    comfort=float(emotions.get("comfort", 0.50)),
                )
                emotion_caption = StateManager.get_emotion_summary_caption(state_obj)
            except Exception as e:
                log.warning("Failed to generate emotion caption", error=str(e))

        return ChatResponse(
            response=reply_text,
            user_id=principal.subject_id,
            emotions=emotions,
            emotion_caption=emotion_caption,
            loop_thinking_activated=loop_thinking_activated,
            images_processed=images_processed,
            attached_images=attached_images,
            citations=citation_ids,
        )
    except ChatEngineBusyError:
        raise HTTPException(
            status_code=429,
            detail="Chisa đang xử lý tin nhắn trước đó, Senpai chờ em thêm lát nữa nhé~",
        ) from None
    except SQLAlchemyError as db_err:
        log.error(
            "Database connection or operation failed",
            error=str(db_err),
            user_id=principal.subject_id,
        )
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from db_err
    except Exception as e:
        log.error(
            "Chat orchestration failed",
            error=str(e),
            error_type=type(e).__name__,
            user_id=principal.subject_id,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    http_request: Request,
    principal: Annotated[PrincipalContext, Depends(require_scope("chat:write"))],
    chat_engine: ChatEngine = Depends(get_chat_engine),
):
    """SSE stream for realtime loop-thinking updates — web clients only."""
    from app.config.settings import settings
    from app.infrastructure.database.engine import AsyncSessionFactory
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
    from app.shared.utils.background_tasks import BackgroundTaskManager

    if principal.source != "web":
        raise HTTPException(
            status_code=400,
            detail="SSE chat stream is only available for web clients. Use POST /chat instead.",
        )

    username, normalized_user_id = _prepare_chat_context(principal, http_request)
    message = request.message or ""
    log.info(
        "Received chat stream request",
        user_id=principal.subject_id,
        normalized_user_id=normalized_user_id,
    )

    trace_id = _start_chat_trace(principal, username, message)
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=settings.SSE_MAX_QUEUE_SIZE)
    loop_event_sent = False

    def listener(event: dict):
        nonlocal loop_event_sent
        if event.get("trace_id") != trace_id:
            return

        if event.get("type") != "step":
            return

        step = event.get("step") or {}
        step_name = step.get("name", "")
        if step_name.startswith("thinking_loop_cycle_") and not loop_event_sent:
            loop_event_sent = True
            with suppress(asyncio.QueueFull):
                queue.put_nowait({"type": "loop_thinking_started", "trace_id": trace_id})

    pipeline_tracker.register_listener(listener)

    async def runner():
        try:

            async def sse_on_token(token: str):
                with suppress(asyncio.QueueFull):
                    queue.put_nowait(
                        {"type": "token", "trace_id": trace_id, "data": {"token": token}}
                    )

            async with AsyncSessionFactory() as session:
                (
                    reply_text,
                    emotions,
                    loop_thinking_activated,
                    images_processed,
                    attached_images,
                    citation_ids,
                ) = await _run_chat_request(
                    session=session,
                    message=message,
                    original_user_id=principal.subject_id,
                    normalized_user_id=normalized_user_id,
                    chat_engine=chat_engine,
                    on_token=sse_on_token,
                    images=request.images,
                    is_ephemeral_reference=bool(request.is_ephemeral_reference),
                )
                await session.commit()

            emotion_caption = None
            if emotions and isinstance(emotions, dict):
                from app.domain.entities.emotion import EmotionState
                from app.domain.services.state_manager import StateManager

                try:
                    state_obj = EmotionState(
                        user_id=normalize_user_id(principal.subject_id),
                        trust=float(emotions.get("trust", 0.50)),
                        attachment=float(emotions.get("attachment", 0.00)),
                        joy=float(emotions.get("joy", 0.15)),
                        sadness=float(emotions.get("sadness", 0.00)),
                        irritation=float(emotions.get("irritation", 0.00)),
                        shyness=float(emotions.get("shyness", 0.00)),
                        curiosity=float(emotions.get("curiosity", 0.10)),
                        comfort=float(emotions.get("comfort", 0.50)),
                    )
                    emotion_caption = StateManager.get_emotion_summary_caption(state_obj)
                except Exception:
                    emotion_caption = None

            await queue.put(
                {
                    "type": "citation",
                    "trace_id": trace_id,
                    "data": {"citation_ids": citation_ids},
                }
            )
            await queue.put(
                {
                    "type": "done",
                    "trace_id": trace_id,
                    "data": {
                        "response": reply_text,
                        "user_id": principal.subject_id,
                        "emotions": emotions,
                        "emotion_caption": emotion_caption,
                        "loop_thinking_activated": loop_thinking_activated,
                        "images_processed": images_processed,
                        "attached_images": attached_images,
                        "citations": citation_ids,
                    },
                }
            )
        except asyncio.CancelledError:
            raise
        except SQLAlchemyError as db_err:
            log.error(
                "SSE database connection or operation failed",
                error=str(db_err),
                user_id=principal.subject_id,
            )
            with suppress(asyncio.QueueFull):
                queue.put_nowait(
                    {
                        "type": "error",
                        "trace_id": trace_id,
                        "data": {
                            "message": "Service temporarily unavailable",
                            "error": "ServiceUnavailable",
                        },
                    }
                )
        except Exception as error:
            log.error(
                "SSE chat orchestration failed", error=str(error), user_id=principal.subject_id
            )
            with suppress(asyncio.QueueFull):
                queue.put_nowait(
                    {
                        "type": "error",
                        "trace_id": trace_id,
                        "data": {
                            "message": "Internal server error during chat generation",
                            "error": "InternalServerError",
                        },
                    }
                )

    async def run_with_timeout():
        try:
            await asyncio.wait_for(runner(), timeout=settings.SSE_TIMEOUT)
        except TimeoutError:
            log.warning("SSE runner timed out", user_id=principal.subject_id)
            with suppress(asyncio.QueueFull):
                queue.put_nowait(
                    {
                        "type": "error",
                        "trace_id": trace_id,
                        "data": {"message": "Request timed out", "error": "TimeoutError"},
                    }
                )
        except asyncio.CancelledError:
            pass

    task = BackgroundTaskManager.spawn(run_with_timeout(), name=f"sse_runner:{trace_id}")

    async def event_generator():
        try:
            yield _sse_event("meta", {"trace_id": trace_id})
            while True:
                event = await queue.get()
                yield _sse_event(event["type"], event.get("data", {}))
                if event["type"] in {"done", "error"}:
                    break
        finally:
            pipeline_tracker.unregister_listener(listener)
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/emotions/{user_id}")
async def get_emotions(
    user_id: UserIdPath,
    principal: CurrentPrincipal,
    session: AsyncSession = Depends(get_db_session),
    chat_engine: ChatEngine = Depends(get_chat_engine),
) -> dict:
    """Retrieves the current emotional state of Chisa for the frontend UI."""
    try:
        AuthorizationPolicy.require_subject_access(
            principal,
            user_id,
            own_scope="chat:read",
            elevated_scope="chat:read:any",
        )
        emotion = await chat_engine.get_emotion_state(session, normalize_user_id_str(user_id))
        from app.domain.services.state_manager import StateManager

        return {
            "joy": emotion.joy,
            "sadness": emotion.sadness,
            "trust": emotion.trust,
            "irritation": emotion.irritation,
            "attachment": emotion.attachment,
            "shyness": getattr(emotion, "shyness", 0.0),
            "curiosity": getattr(emotion, "curiosity", 0.20),
            "comfort": getattr(emotion, "comfort", 0.50),
            "caption": StateManager.get_emotion_summary_caption(emotion),
        }
    except AuthorizationError as error:
        raise HTTPException(status_code=403, detail="Access denied") from error
    except Exception as e:
        log.error("Failed to fetch emotions", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Could not retrieve emotions") from e


@router.get("/chat/history/{user_id}")
async def get_chat_history(
    user_id: UserIdPath,
    principal: CurrentPrincipal,
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    chat_engine: ChatEngine = Depends(get_chat_engine),
) -> dict:
    """Retrieves recent conversation history to prepopulate the frontend."""
    try:
        AuthorizationPolicy.require_subject_access(
            principal,
            user_id,
            own_scope="chat:read",
            elevated_scope="chat:read:any",
        )
        history = await chat_engine.get_history(session, normalize_user_id_str(user_id), limit)
        return {"history": history}
    except AuthorizationError as error:
        raise HTTPException(status_code=403, detail="Access denied") from error
    except Exception as e:
        log.error("Failed to fetch chat history", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Could not retrieve history") from e


@router.delete("/chat/clear/{user_id}", response_model=None)
async def clear_user_memory(
    user_id: UserIdPath,
    principal: CurrentPrincipal,
    session: AsyncSession = Depends(get_db_session),
    clear_use_case=Depends(get_clear_user_memory_use_case),
) -> dict | JSONResponse:
    """
    Wipes all conversation memory (STM + LTM) and resets emotion/stats for a user.
    Triggered by the /clear command in the frontend.
    """
    try:
        AuthorizationPolicy.require_subject_access(
            principal,
            user_id,
            own_scope="chat:clear",
            elevated_scope="chat:clear:any",
        )
        result = await clear_use_case.execute(session, normalize_user_id_str(user_id))
        if result["status"] != "completed":
            return JSONResponse(
                status_code=202,
                content={
                    "status": "pending_retry",
                    "erasure_job_id": result["job_id"],
                    "message": "Erasure is pending retry.",
                },
            )
        return {
            "status": "ok",
            "erasure_job_id": result["job_id"],
            "message": "Tất cả ký ức đã được xóa. Chisa sẽ gặp lại Senpai như lần đầu tiên!",
        }
    except AuthorizationError as error:
        raise HTTPException(status_code=403, detail="Access denied") from error
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to clear user memory", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Could not clear user memory") from e
