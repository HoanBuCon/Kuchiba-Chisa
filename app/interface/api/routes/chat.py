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
