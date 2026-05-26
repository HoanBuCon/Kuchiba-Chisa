from __future__ import annotations

import time
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.infrastructure.database.models.emotion_state import EmotionState
from app.domain.interfaces.repositories import IEmotionRepository


class SqlAlchemyEmotionRepository(IEmotionRepository):
    """
    SQLAlchemy implementation of IEmotionRepository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_emotion_state(self, user_id: uuid.UUID) -> EmotionState:
        stmt = select(EmotionState).where(EmotionState.user_id == user_id)
        result = await self.session.execute(stmt)
        state = result.scalar_one_or_none()
        if not state:
            state = EmotionState(
                user_id=user_id,
                joy=0.10,        # Match default baseline settings
                sadness=0.00,
                trust=0.50,
                attachment=0.00,
                irritation=0.00,
                updated_at=int(time.time() * 1000)
            )
            self.session.add(state)
            await self.session.commit()
            await self.session.refresh(state)
        return state

    async def update_emotion(self, emotion: EmotionState) -> None:
        self.session.add(emotion)
        await self.session.commit()
        await self.session.refresh(emotion)
