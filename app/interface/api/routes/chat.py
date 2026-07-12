import asyncio
import json
from typing import Callable, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.engine import get_db_session
from app.interface.api.schemas.chat import ChatRequest, ChatResponse
from app.domain.services.chat_engine import ChatEngine
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.config.settings import settings
from app.infrastructure.llm.adapters.groq import GroqAdapter
from app.infrastructure.llm.adapters.gemini import GeminiAdapter
from app.infrastructure.llm.adapters.base import LLMRateLimitError
from app.infrastructure.logging.logger import get_logger

from app.domain.services.context_builder import ContextBuilder
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.domain.services.memory_extractor import MemoryExtractor
from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str

log = get_logger(__name__)

router = APIRouter()

# Instantiate adapters once, since they are largely stateless or manage their own pools
_embedder = FastEmbedAdapter()

if settings.LLM_PROVIDER == "gemini":
    _llm = GeminiAdapter()
elif settings.LLM_PROVIDER == "deepseek":
    from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
    _llm = DeepSeekAdapter()
else:
    _llm = GroqAdapter()

_context_builder = ContextBuilder()
_memory_extractor = MemoryExtractor(llm=_llm, embedder=_embedder, qdrant=qdrant_service)
_chat_engine = ChatEngine(
    embedder=_embedder,
    llm=_llm,
    context_builder=_context_builder,
    memory_extractor=_memory_extractor
)


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


async def _run_chat_request(session: AsyncSession, request: ChatRequest, on_token: Optional[Callable[[str], Any]] = None) -> tuple[str, dict, bool]:
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    try:
        reply_text, emotions = await _chat_engine.chat(
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
    session: AsyncSession = Depends(get_db_session)
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
        reply_text, emotions, loop_thinking_activated = await _run_chat_request(session=session, request=request)
        return ChatResponse(
            response=reply_text,
            user_id=request.user_id,
            emotions=emotions,
            loop_thinking_activated=loop_thinking_activated
        )
    except Exception as e:
        log.error("Chat orchestration failed", error=str(e), user_id=request.user_id)
        raise HTTPException(status_code=500, detail="Internal server error during chat generation")


@router.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    http_request: Request,
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
    session: AsyncSession = Depends(get_db_session)
) -> dict:
    """Retrieves the current emotional state of Chisa for the frontend UI."""
    try:
        emotion = await _chat_engine.get_emotion_state(session, normalize_user_id_str(user_id))
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
    session: AsyncSession = Depends(get_db_session)
) -> dict:
    """Retrieves recent conversation history to prepopulate the frontend."""
    try:
        history = await _chat_engine.get_history(session, normalize_user_id_str(user_id), limit)
        return {"history": history}
    except Exception as e:
        log.error("Failed to fetch chat history", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Could not retrieve history")


@router.delete("/chat/clear/{user_id}")
async def clear_user_memory(
    user_id: str,
    session: AsyncSession = Depends(get_db_session)
) -> dict:
    """
    Wipes all conversation memory (STM + LTM) and resets emotion/stats for a user.
    Triggered by the /clear command in the frontend.
    """
    from sqlalchemy import delete as sql_delete
    from app.infrastructure.database.models.message import Message
    from app.infrastructure.database.models.conversation import Conversation
    from app.infrastructure.database.models.emotion_state import EmotionState
    from app.infrastructure.database.models.user_stats import UserStats
    from app.infrastructure.vector.qdrant.qdrant_service import get_qdrant_client
    from qdrant_client.http import models as qdrant_models

    user_uuid = normalize_user_id(user_id)
    canonical_user_id = str(user_uuid)

    try:
        # 1. Delete PostgreSQL STM messages and conversations
        await session.execute(sql_delete(Message).where(Message.user_id == user_uuid).execution_options(synchronize_session=False))
        await session.execute(sql_delete(Conversation).where(Conversation.user_id == user_uuid).execution_options(synchronize_session=False))

        # 2. Reset Emotion and Stats
        await session.execute(sql_delete(EmotionState).where(EmotionState.user_id == user_uuid).execution_options(synchronize_session=False))
        await session.execute(sql_delete(UserStats).where(UserStats.user_id == user_uuid).execution_options(synchronize_session=False))
        await session.commit()

        # 3. Clear Qdrant LTM vectors (best-effort, ignore per-collection failures)
        client = get_qdrant_client()
        collections = ["emotional_memories", "conversation_summaries", "persona_embeddings", "user_facts", "memories"]
        for col in collections:
            try:
                await client.delete(
                    collection_name=col,
                    points_selector=qdrant_models.FilterSelector(
                        filter=qdrant_models.Filter(
                            must=[qdrant_models.FieldCondition(
                                key="user_id",
                                match=qdrant_models.MatchValue(value=canonical_user_id)
                            )]
                        )
                    )
                )
            except Exception as qe:
                log.warning("Could not clear Qdrant collection", collection=col, error=str(qe))

        log.info("User memory cleared via /clear command", user_id=user_id)
        return {"status": "ok", "message": "Tất cả ký ức đã được xóa. Chisa sẽ gặp lại Senpai như lần đầu tiên!"}
    except Exception as e:
        log.error("Failed to clear user memory", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=f"Could not clear user memory: {str(e)}")
