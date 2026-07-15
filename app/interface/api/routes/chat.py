import asyncio
import json
from typing import Callable, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.engine import get_db_session
from app.interface.api.schemas.chat import ChatRequest, ChatResponse
from app.domain.services.chat_engine import ChatEngine, ChatEngineBusyError
from app.domain.interfaces.llm_provider import LLMRateLimitError, LLMTimeoutError, LLMInvalidResponseError
from app.infrastructure.logging.logger import get_logger
from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str
from app.application.dependencies import get_chat_engine, get_clear_user_memory_use_case, container

log = get_logger(__name__)

router = APIRouter()


def _sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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


async def _run_chat_request(session: AsyncSession, request: ChatRequest, chat_engine: ChatEngine, on_token: Optional[Callable[[str], Any]] = None) -> tuple[str, dict, bool]:
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    try:
        reply_text, emotions = await chat_engine.chat(
            session=session,
            user_id=request.user_id,
            user_message=request.message,
            on_token=on_token,
        )
        loop_thinking_activated = pipeline_tracker.get_loop_thinking_activated()

        pipeline_tracker.end_trace(
            response_text=reply_text,
            emotions=emotions,
            status="success",
        )
        return reply_text, emotions, loop_thinking_activated
    except LLMRateLimitError:
        fallback_text = "Chisa đang hơi bận một chút, Senpai chờ em thêm lát nữa nhé."
        fallback_emotions = None
        pipeline_tracker.end_trace(
            response_text=fallback_text,
            emotions=fallback_emotions,
            status="success",
            error=None,
        )
        return fallback_text, fallback_emotions, False
    except (LLMTimeoutError, LLMInvalidResponseError) as llm_err:
        fallback_text = "Chisa hơi mệt một chút, Senpai nhắn lại sau nhé ~"
        fallback_emotions = None
        log.warning("LLM error, returning fallback", error=str(llm_err), user_id=request.user_id)
        pipeline_tracker.end_trace(
            response_text=fallback_text,
            emotions=fallback_emotions,
            status="success",
            error=str(llm_err),
        )
        return fallback_text, fallback_emotions, False
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
    from app.infrastructure.logging.llm_logger import enable_clean_log
    is_test = http_request.headers.get("X-Enable-Clean-Log") == "true"
    enable_clean_log.set(is_test)

    log.info("Received chat request", user_id=request.user_id)

    # Determine default username if not supplied
    username = request.username
    if not username and request.source == "web":
        username = "Web Guest"

    request.user_id = normalize_user_id_str(request.user_id)

    _start_chat_trace(request, username)

    try:
        reply_text, emotions, loop_thinking_activated = await _run_chat_request(
            session=session, 
            request=request, 
            chat_engine=chat_engine
        )
        return ChatResponse(
            response=reply_text,
            user_id=request.user_id,
            emotions=emotions,
            loop_thinking_activated=loop_thinking_activated
        )
    except ChatEngineBusyError:
        raise HTTPException(
            status_code=429,
            detail="Chisa đang xử lý tin nhắn trước đó, Senpai chờ em thêm lát nữa nhé~"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
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

    if request.source and request.source != "web":
        raise HTTPException(
            status_code=400,
            detail="SSE chat stream is only available for web clients. Use POST /chat instead.",
        )

    is_test = http_request.headers.get("X-Enable-Clean-Log") == "true"
    enable_clean_log.set(is_test)

    username = request.username or "Web Guest"
    request.user_id = normalize_user_id_str(request.user_id)

    trace_id = _start_chat_trace(request, username)
    queue: asyncio.Queue[dict] = asyncio.Queue()
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
            queue.put_nowait({"type": "loop_thinking_started", "trace_id": trace_id})

    pipeline_tracker.register_listener(listener)

    async def runner():
        try:
            async def sse_on_token(token: str):
                queue.put_nowait({"type": "token", "trace_id": trace_id, "data": {"token": token}})

            async with AsyncSessionFactory() as session:
                reply_text, emotions, loop_thinking_activated = await _run_chat_request(
                    session=session,
                    request=request,
                    chat_engine=chat_engine,
                    on_token=sse_on_token,
                )
            queue.put_nowait({
                "type": "complete",
                "trace_id": trace_id,
                "data": {
                    "response": reply_text,
                    "user_id": request.user_id,
                    "emotions": emotions,
                    "loop_thinking_activated": loop_thinking_activated,
                },
            })
        except Exception as error:
            log.error("SSE chat orchestration failed", error=str(error), user_id=request.user_id)
            queue.put_nowait({
                "type": "error",
                "trace_id": trace_id,
                "data": {
                    "message": "Internal server error during chat generation",
                    "error": str(error),
                },
            })

    task = asyncio.create_task(runner())

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
                except Exception:
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
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    chat_engine: ChatEngine = Depends(get_chat_engine)
) -> dict:
    """Retrieves the current emotional state of Chisa for the frontend UI."""
    try:
        emotion = await chat_engine.get_emotion_state(session, normalize_user_id_str(user_id))
        return {
            "joy": emotion.joy,
            "sadness": emotion.sadness,
            "trust": emotion.trust,
            "irritation": emotion.irritation,
            "attachment": emotion.attachment
        }
    except Exception as e:
        log.error("Failed to fetch emotions", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Could not retrieve emotions")


@router.get("/chat/history/{user_id}")
async def get_chat_history(
    user_id: str,
    limit: int = 50,
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
    user_id: str,
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
