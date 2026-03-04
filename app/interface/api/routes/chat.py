from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.engine import get_db_session
from app.interface.api.schemas.chat import ChatRequest, ChatResponse
from app.domain.services.chat_engine import ChatEngine
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.llm.adapters.groq import GroqAdapter
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

router = APIRouter()

# Instantiate adapters once, since they are largely stateless or manage their own pools
_embedder = FastEmbedAdapter()
_llm = GroqAdapter()
_chat_engine = ChatEngine(embedder=_embedder, llm=_llm)


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    session: AsyncSession = Depends(get_db_session)
) -> ChatResponse:
    """
    Primary endpoint for User <-> AI interactions.
    Requires user_id to correctly scope STM, emotions, and RAG contexts.
    """
    log.info("Received chat request", user_id=request.user_id)
    try:
        reply_text = await _chat_engine.chat(
            session=session,
            user_id=request.user_id,
            user_message=request.message
        )
        return ChatResponse(
            response=reply_text,
            user_id=request.user_id
        )
    except Exception as e:
        log.error("Chat orchestration failed", error=str(e), user_id=request.user_id)
        raise HTTPException(status_code=500, detail="Internal server error during chat generation")


@router.get("/chat/history/{user_id}")
async def get_chat_history(
    user_id: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_db_session)
) -> dict:
    """Retrieves recent conversation history to prepopulate the frontend."""
    try:
        history = await _chat_engine.get_history(session, user_id, limit)
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
    import uuid as _uuid
    from sqlalchemy import delete as sql_delete
    from app.infrastructure.database.models.message import Message
    from app.infrastructure.database.models.conversation import Conversation
    from app.infrastructure.database.models.emotion_state import EmotionState
    from app.infrastructure.database.models.user_stats import UserStats
    from app.infrastructure.vector.qdrant.qdrant_service import get_qdrant_client
    from qdrant_client.http import models as qdrant_models

    try:
        user_uuid = _uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format")

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
        collections = ["emotional_memories", "conversation_summaries", "persona_embeddings", "user_facts"]
        for col in collections:
            try:
                await client.delete(
                    collection_name=col,
                    points_selector=qdrant_models.FilterSelector(
                        filter=qdrant_models.Filter(
                            must=[qdrant_models.FieldCondition(
                                key="user_id",
                                match=qdrant_models.MatchValue(value=user_id)
                            )]
                        )
                    )
                )
            except Exception as qe:
                log.warning("Could not clear Qdrant collection", collection=col, error=str(qe))

        log.info("User memory cleared via /clear command", user_id=user_id)
        return {"status": "ok", "message": "Tất cả ký ức đã được xóa sạch~ Chisa sẽ gặp lại Senpai như lần đầu tiên!"}
    except Exception as e:
        log.error("Failed to clear user memory", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=f"Could not clear user memory: {str(e)}")
