import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dependencies import get_chat_engine, get_clear_community_memory_use_case
from app.domain.entities.community import CommunityMessage
from app.domain.interfaces.llm_provider import LLMRateLimitError, LLMTimeoutError
from app.domain.services.chat_engine import ChatEngine, ChatEngineBusyError
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.logging.logger import get_logger
from app.interface.api.schemas.community import CommunityChatRequest, CommunityChatResponse

log = get_logger(__name__)

router = APIRouter(prefix="/community", tags=["community"])


@router.post("/chat", response_model=CommunityChatResponse)
async def community_chat_endpoint(
    request: CommunityChatRequest,
    session: AsyncSession = Depends(get_db_session),
    chat_engine: ChatEngine = Depends(get_chat_engine),
) -> CommunityChatResponse:
    """
    Multi-user community channel chat endpoint.
    Processes multi-speaker dialogue context through the unified 10-stage RAG pipeline.
    """
    log.info(
        "Processing community chat request",
        channel_id=request.channel_id,
        user_id=request.user_id,
        username=request.username,
        recent_count=len(request.recent_messages),
    )

    domain_messages = []
    for msg in request.recent_messages:
        created_dt = datetime.now()
        if msg.created_at:
            try:
                created_dt = datetime.fromisoformat(msg.created_at)
            except Exception:
                created_dt = datetime.now()

        domain_messages.append(
            CommunityMessage(
                message_id=msg.message_id,
                speaker_id=msg.speaker_id,
                speaker_name=msg.speaker_name,
                content=msg.content,
                created_at=created_dt,
                reply_to_speaker=msg.reply_to_speaker,
                reply_to_content=msg.reply_to_content,
                is_bot=msg.is_bot,
            )
        )

    t0 = time.time()
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    pipeline_tracker.start_trace(
        user_id=request.user_id,
        message=request.message,
        pipeline="community",
        source="discord_community",
        username=request.username,
        channel_name=request.channel_name,
        guild_name=request.guild_name,
    )

    try:
        reply_text, updated_emotions, images_processed = await chat_engine.community_chat(
            session=session,
            channel_id=request.channel_id,
            user_id=request.user_id,
            user_message=request.message,
            speaker_name=request.username,
            channel_name=request.channel_name,
            guild_id=request.guild_id,
            guild_name=request.guild_name,
            recent_messages=domain_messages,
            images=request.images,
            is_ephemeral_reference=bool(request.is_ephemeral_reference),
        )

        await session.commit()
        duration_ms = round((time.time() - t0) * 1000, 2)

        pipeline_tracker.end_trace(
            response_text=reply_text,
            emotions=updated_emotions,
            status="success",
        )

        emotion_caption = None
        if updated_emotions and isinstance(updated_emotions, dict):
            from app.domain.services.state_manager import StateManager
            from app.domain.entities.emotion import EmotionState
            try:
                state_obj = EmotionState(
                    user_id=request.user_id,
                    trust=float(updated_emotions.get("trust", 0.50)),
                    attachment=float(updated_emotions.get("attachment", 0.00)),
                    joy=float(updated_emotions.get("joy", 0.15)),
                    sadness=float(updated_emotions.get("sadness", 0.00)),
                    irritation=float(updated_emotions.get("irritation", 0.00)),
                    shyness=float(updated_emotions.get("shyness", 0.00)),
                    curiosity=float(updated_emotions.get("curiosity", 0.10)),
                    comfort=float(updated_emotions.get("comfort", 0.50)),
                )
                emotion_caption = StateManager.get_emotion_summary_caption(state_obj)
            except Exception as e:
                log.warning("Failed to generate emotion caption", error=str(e))

        return CommunityChatResponse(
            response=reply_text or "Chisa chào mọi người ạ ~",
            emotions=updated_emotions or {},
            emotion_caption=emotion_caption,
            execution_time_ms=duration_ms,
            images_processed=images_processed,
        )

    except ChatEngineBusyError:
        pipeline_tracker.end_trace(
            response_text="Chisa đang xử lý tin nhắn trước đó của bạn, vui lòng chờ một nhịp nhé!",
            emotions={},
            status="error",
            error="ChatEngineBusyError",
        )
        raise HTTPException(
            status_code=429,
            detail="Chisa đang xử lý tin nhắn trước đó của bạn, vui lòng chờ một nhịp nhé!",
        )
    except LLMRateLimitError:
        log.warning("Community chat rate limited", channel_id=request.channel_id, user_id=request.user_id)
        fallback = "Kênh chat đang sôi nổi quá, mọi người đợi Chisa một nhịp xíu nhé!"
        pipeline_tracker.end_trace(
            response_text=fallback,
            emotions={},
            status="success",
            error="LLMRateLimitError",
        )
        return CommunityChatResponse(
            response=fallback,
            emotions={},
            execution_time_ms=round((time.time() - t0) * 1000, 2),
        )
    except LLMTimeoutError:
        log.error("Community chat timeout", channel_id=request.channel_id, user_id=request.user_id)
        fallback = "Chisa đang xử lý nhiều dữ liệu cùng lúc nên hơi chậm một chút, mọi người nhắn lại giúp em nha."
        pipeline_tracker.end_trace(
            response_text=fallback,
            emotions={},
            status="success",
            error="LLMTimeoutError",
        )
        return CommunityChatResponse(
            response=fallback,
            emotions={},
            execution_time_ms=round((time.time() - t0) * 1000, 2),
        )
    except Exception as e:
        log.error("Community chat failed", error=str(e), channel_id=request.channel_id, user_id=request.user_id)
        pipeline_tracker.end_trace(
            response_text=f"Lỗi: {str(e)}",
            emotions={},
            status="error",
            error=str(e),
        )
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi xử lý tin nhắn cộng đồng: {str(e)}",
        )


@router.delete("/clear/{guild_id}")
async def clear_community_memory_endpoint(
    guild_id: str,
    scope: str = "all",
    channel_id: Optional[str] = None,
    user_id: Optional[str] = None,
    clear_use_case = Depends(get_clear_community_memory_use_case),
) -> dict:
    """
    Clears collective community memory (guild_memories, topic summaries, ambient mood).
    Supports scope='all' (server-wide) or scope='self' (user's community interactions).
    """
    try:
        from app.application.dependencies import get_clear_community_memory_use_case
        result = await clear_use_case.execute(
            guild_id=guild_id,
            scope=scope,
            channel_id=channel_id,
            user_id=user_id,
        )
        return {
            "status": "success",
            "message": f"Community memory cleared successfully for guild {guild_id} with scope '{scope}'.",
            "details": result,
        }
    except Exception as e:
        log.error("Failed to clear community memory", guild_id=guild_id, scope=scope, error=str(e))
        raise HTTPException(status_code=500, detail=f"Could not clear community memory: {str(e)}")

