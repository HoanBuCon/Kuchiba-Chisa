from __future__ import annotations
import uuid
from datetime import datetime, timezone
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
        rewritten_content: Optional[str] = None,
        media_metadata: Optional[Any] = None,
    ) -> None:
        enum_role = MessageRoleModel.USER if role == "user" else MessageRoleModel.ASSISTANT
        msg = MessageModel(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,
            role=enum_role,
            content=content,
            rewritten_content=rewritten_content,
            token_count=token_count,
            is_success=is_success,
            media_metadata=media_metadata,
            created_at=datetime.utcnow()
        )
        self.session.add(msg)
        await self.session.flush()

    async def get_last_user_rewritten_query(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, max_lookback: int = 3
    ) -> Optional[str]:
        """
        Knowledge-Aware Lookback: Retrieves the most recent meaningful user query from conversation history.
        Skips superficial short reactions (e.g. 'haha', 'ok', 'cảm ơn') to preserve multi-turn context
        when follow-up questions occur after short interjections.
        """
        stmt = (
            select(MessageModel.rewritten_content, MessageModel.content)
            .where(
                MessageModel.user_id == user_id,
                MessageModel.conversation_id == conversation_id,
                MessageModel.role == MessageRoleModel.USER,
                MessageModel.is_success == True
            )
            .order_by(MessageModel.created_at.desc())
            .limit(max_lookback)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        if not rows:
            return None

        from app.shared.utils.query_cleaner import is_meaningful_query
        for row in rows:
            candidate = row[0] or row[1]
            if candidate and is_meaningful_query(candidate):
                return candidate

        # Fallback to the latest message if all were short
        return rows[0][0] or rows[0][1]

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

    async def get_latest_summary(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Optional[str]:
        stmt = (
            select(ConversationModel.summary)
            .where(
                ConversationModel.id == conversation_id,
                ConversationModel.user_id == user_id
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_conversation_summary(
        self, conversation_id: uuid.UUID, summary: str
    ) -> None:
        stmt = (
            select(ConversationModel)
            .where(ConversationModel.id == conversation_id)
        )
        conv = (await self.session.execute(stmt)).scalar_one_or_none()
        if conv:
            conv.summary = summary
            await self.session.flush()

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        from sqlalchemy import delete
        # Delete messages first to satisfy foreign keys if any, though cascade might handle it. We do both just like the original code.
        await self.session.execute(delete(MessageModel).where(MessageModel.user_id == user_id).execution_options(synchronize_session=False))
        await self.session.execute(delete(ConversationModel).where(ConversationModel.user_id == user_id).execution_options(synchronize_session=False))
        await self.session.flush()
