from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dependencies import get_community_pipeline
from app.domain.entities.community import CommunityMessage
from app.domain.interfaces.llm_provider import LLMInvalidResponseError, LLMRateLimitError, LLMTimeoutError
from app.domain.services.community.community_pipeline import CommunityChatPipeline
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.database.repositories.conversation_repository import SqlAlchemyConversationRepository
from app.infrastructure.database.repositories.emotion_repository import SqlAlchemyEmotionRepository
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.infrastructure.logging.logger import get_logger
from app.interface.api.schemas.community import CommunityChatRequest, CommunityChatResponse

log = get_logger(__name__)

router = APIRouter(prefix="/community", tags=["community"])


@router.post("/chat", response_model=CommunityChatResponse)
async def community_chat_endpoint(
    request: CommunityChatRequest,
    session: AsyncSession = Depends(get_db_session),
    pipeline: CommunityChatPipeline = Depends(get_community_pipeline),
) -> CommunityChatResponse:
    """
    Multi-user community channel chat endpoint.
    Processes multi-speaker dialogue context and provides group-aware responses.
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

    user_repo = SqlAlchemyUserRepository(session)
    emotion_repo = SqlAlchemyEmotionRepository(session)
    conv_repo = SqlAlchemyConversationRepository(session)

    try:
        context = await pipeline.execute(
            session=session,
            channel_id=request.channel_id,
            guild_id=request.guild_id,
            channel_name=request.channel_name,
            guild_name=request.guild_name,
            current_speaker_id=request.user_id,
            current_speaker_name=request.username,
            user_message=request.message,
            recent_messages=domain_messages,
            user_repo=user_repo,
            emotion_repo=emotion_repo,
            conv_repo=conv_repo,
        )

        await session.commit()

        return CommunityChatResponse(
            response=context.cleaned_response or "Chisa chào mọi người ạ ~",
            emotions=context.updated_speaker_emotions or {},
            sentiment=context.extracted_sentiment,
            execution_time_ms=context.execution_time_ms,
        )

    except LLMRateLimitError:
        log.warning("Community chat rate limited", channel_id=request.channel_id, user_id=request.user_id)
        return CommunityChatResponse(
            response="Kênh chat đang sôi nổi quá, mọi người đợi Chisa một nhịp xíu nhé!",
            emotions={},
            execution_time_ms=0.0,
        )
    except LLMTimeoutError:
        log.error("Community chat timeout", channel_id=request.channel_id, user_id=request.user_id)
        return CommunityChatResponse(
            response="Chisa đang xử lý nhiều dữ liệu cùng lúc nên hơi chậm một chút, mọi người nhắn lại giúp em nha.",
            emotions={},
            execution_time_ms=0.0,
        )
    except Exception as e:
        log.error("Community chat failed", error=str(e), channel_id=request.channel_id, user_id=request.user_id)
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi xử lý tin nhắn cộng đồng: {str(e)}",
        )
