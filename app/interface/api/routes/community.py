"""Authenticated, tenant-scoped community chat routes."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dependencies import get_chat_engine, get_clear_community_memory_use_case
from app.application.security.authorization import AuthorizationError, AuthorizationPolicy
from app.domain.entities.community import CommunityMessage
from app.domain.interfaces.llm_provider import LLMRateLimitError, LLMTimeoutError
from app.domain.services.chat_engine import ChatEngine, ChatEngineBusyError
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.logging.logger import get_logger
from app.interface.api.dependencies.security import CurrentPrincipal, require_scope
from app.interface.api.schemas.community import CommunityChatRequest, CommunityChatResponse
from app.shared.utils.user_identity import normalize_user_id

log = get_logger(__name__)
router = APIRouter(prefix="/community", tags=["community"])


def _trusted_community_context(principal: PrincipalContext) -> tuple[str, str, str]:
    """Returns actor, tenant, and channel strictly from a workload credential."""
    AuthorizationPolicy.require_source(principal, "discord")
    return (
        principal.subject_id,
        AuthorizationPolicy.tenant_id_or_deny(principal),
        AuthorizationPolicy.channel_id_or_deny(principal),
    )


def _domain_messages(request: CommunityChatRequest) -> list[CommunityMessage]:
    """Converts transcript content without granting it identity authority."""
    messages: list[CommunityMessage] = []
    for message in request.recent_messages:
        try:
            created_at = (
                datetime.fromisoformat(message.created_at) if message.created_at else datetime.now()
            )
        except ValueError:
            created_at = datetime.now()
        messages.append(
            CommunityMessage(
                message_id=message.message_id,
                speaker_id=message.speaker_id,
                speaker_name=message.speaker_name,
                content=message.content,
                created_at=created_at,
                reply_to_speaker=message.reply_to_speaker,
                reply_to_content=message.reply_to_content,
                is_bot=message.is_bot,
            )
        )
    return messages


@router.post("/chat", response_model=CommunityChatResponse)
async def community_chat_endpoint(
    request: CommunityChatRequest,
    principal: Annotated[PrincipalContext, Depends(require_scope("community:write"))],
    session: AsyncSession = Depends(get_db_session),
    chat_engine: ChatEngine = Depends(get_chat_engine),
) -> CommunityChatResponse:
    """Process tenant-scoped Discord community chat from a workload JWT."""
    try:
        actor_id, guild_id, channel_id = _trusted_community_context(principal)
    except AuthorizationError as error:
        raise HTTPException(status_code=403, detail="Access denied") from error

    username = principal.display_name or "Discord user"
    log.info(
        "Processing community chat request",
        channel_id=channel_id,
        user_id=actor_id,
        recent_count=len(request.recent_messages),
    )
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    message = request.message or ""
    pipeline_tracker.start_trace(
        user_id=actor_id,
        message=message,
        pipeline="community",
        source=principal.source,
        username=username,
        channel_name=channel_id,
        guild_name=guild_id,
    )
    started_at = time.time()

    try:
        reply_text, updated_emotions, images_processed, attached_images = (
            await chat_engine.community_chat(
                session=session,
                channel_id=channel_id,
                user_id=actor_id,
                user_message=message,
                speaker_name=username,
                channel_name=channel_id,
                guild_id=guild_id,
                guild_name=guild_id,
                recent_messages=_domain_messages(request),
                images=request.images,
                is_ephemeral_reference=bool(request.is_ephemeral_reference),
            )
        )
        await session.commit()
        pipeline_tracker.end_trace(
            response_text=reply_text,
            emotions=updated_emotions,
            status="success",
        )

        emotion_caption = None
        if updated_emotions:
            from app.domain.entities.emotion import EmotionState
            from app.domain.services.state_manager import StateManager

            try:
                emotion_caption = StateManager.get_emotion_summary_caption(
                    EmotionState(
                        user_id=normalize_user_id(actor_id),
                        trust=float(updated_emotions.get("trust", 0.50)),
                        attachment=float(updated_emotions.get("attachment", 0.00)),
                        joy=float(updated_emotions.get("joy", 0.15)),
                        sadness=float(updated_emotions.get("sadness", 0.00)),
                        irritation=float(updated_emotions.get("irritation", 0.00)),
                        shyness=float(updated_emotions.get("shyness", 0.00)),
                        curiosity=float(updated_emotions.get("curiosity", 0.10)),
                        comfort=float(updated_emotions.get("comfort", 0.50)),
                    )
                )
            except (TypeError, ValueError) as error:
                log.warning("Failed to generate emotion caption", error_type=type(error).__name__)

        return CommunityChatResponse(
            response=reply_text or "Chisa is ready to help.",
            emotions=updated_emotions or {},
            emotion_caption=emotion_caption,
            execution_time_ms=round((time.time() - started_at) * 1000, 2),
            images_processed=images_processed,
            attached_images=attached_images,
        )
    except ChatEngineBusyError as error:
        pipeline_tracker.end_trace(response_text="Busy", emotions={}, status="error", error="busy")
        raise HTTPException(status_code=429, detail="Chat is busy; try again shortly") from error
    except LLMRateLimitError:
        fallback = "The community chat is busy; please try again shortly."
        pipeline_tracker.end_trace(
            response_text=fallback, emotions={}, status="success", error="llm_rate_limited"
        )
        return CommunityChatResponse(
            response=fallback,
            execution_time_ms=round((time.time() - started_at) * 1000, 2),
        )
    except LLMTimeoutError:
        fallback = "The community chat timed out; please try again shortly."
        pipeline_tracker.end_trace(
            response_text=fallback, emotions={}, status="success", error="llm_timeout"
        )
        return CommunityChatResponse(
            response=fallback,
            execution_time_ms=round((time.time() - started_at) * 1000, 2),
        )
    except Exception as error:
        log.error(
            "Community chat failed",
            error_type=type(error).__name__,
            channel_id=channel_id,
            user_id=actor_id,
        )
        pipeline_tracker.end_trace(
            response_text="Community chat failed",
            emotions={},
            status="error",
            error=type(error).__name__,
        )
        await session.rollback()
        raise HTTPException(
            status_code=500, detail="Community chat is temporarily unavailable"
        ) from error


@router.delete("/clear/{guild_id}", response_model=None)
async def clear_community_memory_endpoint(
    guild_id: str,
    principal: CurrentPrincipal,
    scope: Literal["all", "self"] = "all",
    channel_id: str | None = None,
    user_id: str | None = None,
    session: AsyncSession = Depends(get_db_session),
    clear_use_case=Depends(get_clear_community_memory_use_case),
) -> dict | JSONResponse:
    """Clear only resources authorized by the verified Discord tenant context."""
    del channel_id, user_id  # Client query values are never identity authority.
    try:
        AuthorizationPolicy.require_source(principal, "discord")
        AuthorizationPolicy.require_tenant(principal, guild_id)
        if scope == "all":
            AuthorizationPolicy.require_scope(principal, "community:clear:any")
            trusted_channel_id = None
            trusted_user_id = None
        else:
            AuthorizationPolicy.require_scope(principal, "community:clear:self")
            trusted_channel_id = AuthorizationPolicy.channel_id_or_deny(principal)
            trusted_user_id = principal.subject_id

        result = await clear_use_case.execute(
            session=session,
            guild_id=guild_id,
            scope=scope,
            channel_id=trusted_channel_id,
            user_id=trusted_user_id,
        )
        if result["status"] != "completed":
            return JSONResponse(
                status_code=202,
                content={
                    "status": "pending_retry",
                    "erasure_job_id": result["job_id"],
                    "message": "Community erasure is pending retry.",
                },
            )
        return {
            "status": "success",
            "erasure_job_id": result["job_id"],
            "message": "Community memory cleared.",
        }
    except AuthorizationError as error:
        raise HTTPException(status_code=403, detail="Access denied") from error
    except Exception as error:
        log.error(
            "Failed to clear community memory",
            guild_id=guild_id,
            scope=scope,
            error_type=type(error).__name__,
        )
        raise HTTPException(status_code=500, detail="Could not clear community memory") from error
