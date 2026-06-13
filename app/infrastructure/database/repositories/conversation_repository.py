from __future__ import annotations

import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.message import Message, MessageRole
from app.domain.interfaces.repositories import IConversationRepository


class SqlAlchemyConversationRepository(IConversationRepository):
    """
    SQLAlchemy implementation of IConversationRepository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_conversation(self, user_id: uuid.UUID) -> uuid.UUID:
        stmt = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.ended_at.is_(None)
            )
            .order_by(Conversation.started_at.desc())
            .limit(1)
        )
        
        conv = (await self.session.execute(stmt)).scalar_one_or_none()
        if not conv:
            conv = Conversation(id=uuid.uuid4(), user_id=user_id)
            self.session.add(conv)
            await self.session.commit()
            await self.session.refresh(conv)
        return conv.id

    async def save_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        content: str,
        token_count: Optional[int] = None,
        is_success: bool = True,
    ) -> None:
        enum_role = MessageRole.USER if role == "user" else MessageRole.ASSISTANT
        msg = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,
            role=enum_role,
            content=content,
            token_count=token_count,
            is_success=is_success
        )
        self.session.add(msg)
        await self.session.commit()

    async def get_recent_history(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 15
    ) -> List[dict[str, str]]:
        stmt = (
            select(Message)
            .where(
                Message.user_id == user_id,
                Message.conversation_id == conversation_id,
                Message.is_success == True
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        msgs = result.scalars().all()
        # Return chronologically (oldest first)
        return [{"role": m.role.value, "content": m.content} for m in reversed(msgs)]
