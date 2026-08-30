import asyncio
import json
from typing import Callable, Optional, Any, Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.engine import get_db_session
from app.interface.api.schemas.chat import ChatRequest, ChatResponse
from app.domain.services.chat_engine import ChatEngine, ChatEngineBusyError
from app.domain.interfaces.llm_provider import LLMRateLimitError, LLMTimeoutError, LLMInvalidResponseError
from app.infrastructure.logging.logger import get_logger
from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str
from sqlalchemy.exc import SQLAlchemyError
from app.shared.utils.circuit_breaker import CircuitBreakerError
from app.application.dependencies import get_chat_engine, get_clear_user_memory_use_case

log = get_logger(__name__)

router = APIRouter()


def _sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _prepare_chat_context(request: ChatRequest, http_request: Request) -> tuple[str, str]:
    """Sets up clean log flag, determines username, and normalizes user_id."""
    from app.infrastructure.logging.llm_logger import enable_clean_log
    
    is_test = http_request.headers.get("X-Enable-Clean-Log") == "true"
    enable_clean_log.set(is_test)

    username = request.username or ("Web Guest" if request.source == "web" else "Unknown")
    normalized_user_id = normalize_user_id_str(request.user_id)
    return username, normalized_user_id


UserIdPath = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\:]+$")]

def _start_chat_trace(request: ChatRequest, username: str | None) -> str:
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    return pipeline_tracker.start_trace(
        user_id=request.user_id,
        message=request.message,
        pipeline="production",
        source=request.source,
        username=username,
        channel_name=request.channel_name,
        guild_name=request.guild_name,
    )


async def _run_chat_request(
    session: AsyncSession,
    message: str,
    original_user_id: str,
    normalized_user_id: str,
    chat_engine: ChatEngine,
    on_token: Optional[Callable[[str], Any]] = None,
    images: Optional[list[str]] = None,
    is_ephemeral_reference: bool = False,
) -> tuple[str, dict, bool, list]:
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    try:
        reply_text, emotions, images_processed = await chat_engine.chat(
            session=session,
            user_id=normalized_user_id,
            user_message=message,
            on_token=on_token,
            images=images,
            is_ephemeral_reference=is_ephemeral_reference,
        )
        loop_thinking_activated = pipeline_tracker.get_loop_thinking_activated()

        pipeline_tracker.end_trace(
            response_text=reply_text,
            emotions=emotions,
            status="success",
        )
        return reply_text, emotions, loop_thinking_activated, images_processed
    except LLMRateLimitError:
        fallback_text = "Chisa đang hơi bận một chút, Senpai chờ em thêm lát nữa nhé."
        fallback_emotions = None
        pipeline_tracker.end_trace(
            response_text=fallback_text,
            emotions=fallback_emotions,
            status="success",
            error=None,
        )
        return fallback_text, fallback_emotions, False, []
    except (LLMTimeoutError, LLMInvalidResponseError, CircuitBreakerError) as llm_err:
        fallback_text = "Chisa hơi mệt một chút, Senpai nhắn lại sau nhé ~"
        fallback_emotions = None
        log.warning("LLM error, returning fallback", error=str(llm_err), user_id=original_user_id, normalized_user_id=normalized_user_id)
        pipeline_tracker.end_trace(
            response_text=fallback_text,
            emotions=fallback_emotions,
            status="success",
            error=str(llm_err),
        )
        return fallback_text, fallback_emotions, False, []
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
    session: AsyncSession = Depends(get_db_session),
    chat_engine: ChatEngine = Depends(get_chat_engine)
) -> ChatResponse:
    """
    Primary endpoint for User <-> AI interactions.
    Requires user_id to correctly scope STM, emotions, and RAG contexts.
    """
    username, normalized_user_id = _prepare_chat_context(request, http_request)
    log.info("Received chat request", user_id=request.user_id, normalized_user_id=normalized_user_id, has_images=bool(request.images))

    _start_chat_trace(request, username)

    try:
        reply_text, emotions, loop_thinking_activated, images_processed = await _run_chat_request(
            session=session, 
            message=request.message,
            original_user_id=request.user_id,
            normalized_user_id=normalized_user_id,
            chat_engine=chat_engine,
            images=request.images,
            is_ephemeral_reference=bool(request.is_ephemeral_reference),
        )
        
        emotion_caption = None
        if emotions and isinstance(emotions, dict):
            from app.domain.services.state_manager import StateManager
            from app.domain.entities.emotion import EmotionState
            try:
                state_obj = EmotionState(
                    user_id=request.user_id,
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
            user_id=request.user_id,
            emotions=emotions,
            emotion_caption=emotion_caption,
            loop_thinking_activated=loop_thinking_activated,
            images_processed=images_processed,
        )
    except ChatEngineBusyError:
        raise HTTPException(
            status_code=429,
            detail="Chisa đang xử lý tin nhắn trước đó, Senpai chờ em thêm lát nữa nhé~"
        )
    except SQLAlchemyError as db_err:
        log.error("Database connection or operation failed", error=str(db_err), user_id=request.user_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    except Exception as e:
        log.error("Chat orchestration failed", error=str(e), error_type=type(e).__name__, user_id=request.user_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    http_request: Request,
    chat_engine: ChatEngine = Depends(get_chat_engine)
):
    """SSE stream for realtime loop-thinking updates — web clients only."""
    from app.infrastructure.logging.llm_logger import enable_clean_log
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
    from app.infrastructure.database.engine import AsyncSessionFactory
    from app.config.settings import settings
    from app.shared.utils.background_tasks import BackgroundTaskManager

    if request.source and request.source != "web":
        raise HTTPException(
            status_code=400,
            detail="SSE chat stream is only available for web clients. Use POST /chat instead.",
        )

    username, normalized_user_id = _prepare_chat_context(request, http_request)
    log.info("Received chat stream request", user_id=request.user_id, normalized_user_id=normalized_user_id)

    trace_id = _start_chat_trace(request, username)
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
            try:
                queue.put_nowait({"type": "loop_thinking_started", "trace_id": trace_id})
            except asyncio.QueueFull:
                pass

    pipeline_tracker.register_listener(listener)

    async def runner():
        try:
            async def sse_on_token(token: str):
                try:
                    queue.put_nowait({"type": "token", "trace_id": trace_id, "data": {"token": token}})
                except asyncio.QueueFull:
                    pass

            async with AsyncSessionFactory() as session:
                reply_text, emotions, loop_thinking_activated = await _run_chat_request(
                    session=session,
                    message=request.message,
                    original_user_id=request.user_id,
                    normalized_user_id=normalized_user_id,
                    chat_engine=chat_engine,
                    on_token=sse_on_token,
                )
                await session.commit()

            emotion_caption = None
            if emotions and isinstance(emotions, dict):
                from app.domain.services.state_manager import StateManager
                from app.domain.entities.emotion import EmotionState
                try:
                    state_obj = EmotionState(
                        user_id=request.user_id,
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

            await queue.put({
                "type": "complete",
                "trace_id": trace_id,
                "data": {
                    "response": reply_text,
                    "user_id": request.user_id,
                    "emotions": emotions,
                    "emotion_caption": emotion_caption,
                    "loop_thinking_activated": loop_thinking_activated,
                },
            })
        except asyncio.CancelledError:
            raise
        except SQLAlchemyError as db_err:
            log.error("SSE database connection or operation failed", error=str(db_err), user_id=request.user_id)
            try:
                queue.put_nowait({
                    "type": "error",
                    "trace_id": trace_id,
                    "data": {
                        "message": "Service temporarily unavailable",
                        "error": "ServiceUnavailable"
                    },
                })
            except asyncio.QueueFull:
                pass
        except Exception as error:
            log.error("SSE chat orchestration failed", error=str(error), user_id=request.user_id)
            try:
                queue.put_nowait({
                    "type": "error",
                    "trace_id": trace_id,
                    "data": {
                        "message": "Internal server error during chat generation",
                        "error": str(error),
                    },
                })
            except asyncio.QueueFull:
                pass

    async def run_with_timeout():
        try:
            await asyncio.wait_for(runner(), timeout=settings.SSE_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("SSE runner timed out", user_id=request.user_id)
            try:
                queue.put_nowait({
                    "type": "error",
                    "trace_id": trace_id,
                    "data": {
                        "message": "Request timed out",
                        "error": "TimeoutError"
                    }
                })
            except asyncio.QueueFull:
                pass
        except asyncio.CancelledError:
            pass

    task = BackgroundTaskManager.spawn(run_with_timeout(), name=f"sse_runner:{trace_id}")

    async def event_generator():
        try:
            yield _sse_event("trace_started", {"trace_id": trace_id})
            while True:
                event = await queue.get()
                yield _sse_event(event["type"], event.get("data", {}))
                if event["type"] in {"complete", "error"}:
                    break
        finally:
            pipeline_tracker.unregister_listener(listener)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

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
    session: AsyncSession = Depends(get_db_session),
    chat_engine: ChatEngine = Depends(get_chat_engine)
) -> dict:
    """Retrieves the current emotional state of Chisa for the frontend UI."""
    try:
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
    except Exception as e:
        log.error("Failed to fetch emotions", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Could not retrieve emotions")


@router.get("/chat/history/{user_id}")
async def get_chat_history(
    user_id: UserIdPath,
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    chat_engine: ChatEngine = Depends(get_chat_engine)
) -> dict:
    """Retrieves recent conversation history to prepopulate the frontend."""
    try:
        history = await chat_engine.get_history(session, normalize_user_id_str(user_id), limit)
        return {"history": history}
    except Exception as e:
        log.error("Failed to fetch chat history", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Could not retrieve history")


@router.delete("/chat/clear/{user_id}")
async def clear_user_memory(
    user_id: UserIdPath,
    session: AsyncSession = Depends(get_db_session),
    clear_use_case = Depends(get_clear_user_memory_use_case)
) -> dict:
    """
    Wipes all conversation memory (STM + LTM) and resets emotion/stats for a user.
    Triggered by the /clear command in the frontend.
    """
    try:
        await clear_use_case.execute(session, user_id)
        return {"status": "ok", "message": "Tất cả ký ức đã được xóa. Chisa sẽ gặp lại Senpai như lần đầu tiên!"}
    except Exception as e:
        log.error("Failed to clear user memory", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=f"Could not clear user memory: {str(e)}")
