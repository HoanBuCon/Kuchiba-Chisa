import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dependencies import get_chat_engine
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
    try:
        reply_text, updated_emotions = await chat_engine.community_chat(
            session=session,
            channel_id=request.channel_id,
            user_id=request.user_id,
            user_message=request.message,
            speaker_name=request.username,
            channel_name=request.channel_name,
            guild_id=request.guild_id,
            guild_name=request.guild_name,
            recent_messages=domain_messages,
        )

        await session.commit()
        duration_ms = round((time.time() - t0) * 1000, 2)

        return CommunityChatResponse(
            response=reply_text or "Chisa chào mọi người ạ ~",
            emotions=updated_emotions or {},
            execution_time_ms=duration_ms,
        )

    except ChatEngineBusyError:
        raise HTTPException(
            status_code=429,
            detail="Chisa đang xử lý tin nhắn trước đó của bạn, vui lòng chờ một nhịp nhé!",
        )
    except LLMRateLimitError:
        log.warning("Community chat rate limited", channel_id=request.channel_id, user_id=request.user_id)
        return CommunityChatResponse(
            response="Kênh chat đang sôi nổi quá, mọi người đợi Chisa một nhịp xíu nhé!",
            emotions={},
            execution_time_ms=round((time.time() - t0) * 1000, 2),
        )
    except LLMTimeoutError:
        log.error("Community chat timeout", channel_id=request.channel_id, user_id=request.user_id)
        return CommunityChatResponse(
            response="Chisa đang xử lý nhiều dữ liệu cùng lúc nên hơi chậm một chút, mọi người nhắn lại giúp em nha.",
            emotions={},
            execution_time_ms=round((time.time() - t0) * 1000, 2),
        )
    except Exception as e:
        log.error("Community chat failed", error=str(e), channel_id=request.channel_id, user_id=request.user_id)
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi xử lý tin nhắn cộng đồng: {str(e)}",
        )
