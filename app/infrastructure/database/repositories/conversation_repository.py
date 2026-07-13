from __future__ import annotations

import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.infrastructure.database.models.conversation import Conversation as ConversationModel
from app.infrastructure.database.models.message import Message as MessageModel, MessageRole as MessageRoleModel
from app.domain.interfaces.repositories import IConversationRepository


class SqlAlchemyConversationRepository(IConversationRepository):
    """
    SQLAlchemy implementation of IConversationRepository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_conversation(self, user_id: uuid.UUID) -> uuid.UUID:
        stmt = (
            select(ConversationModel)
            .where(
                ConversationModel.user_id == user_id,
                ConversationModel.ended_at.is_(None)
            )
            .order_by(ConversationModel.started_at.desc())
            .limit(1)
        )
        
        conv = (await self.session.execute(stmt)).scalar_one_or_none()
        if not conv:
            conv = ConversationModel(id=uuid.uuid4(), user_id=user_id)
            self.session.add(conv)
            await self.session.flush()
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
        enum_role = MessageRoleModel.USER if role == "user" else MessageRoleModel.ASSISTANT
        msg = MessageModel(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,
            role=enum_role,
            content=content,
            token_count=token_count,
            is_success=is_success
        )
        self.session.add(msg)
        await self.session.flush()

    async def get_recent_history(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 15
    ) -> List[dict[str, str]]:
        stmt = (
            select(MessageModel)
            .where(
                MessageModel.user_id == user_id,
                MessageModel.conversation_id == conversation_id,
                MessageModel.is_success == True
            )
            .order_by(MessageModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        msgs = result.scalars().all()
        # Return chronologically (oldest first)
        return [{"role": m.role.value, "content": m.content} for m in reversed(msgs)]
