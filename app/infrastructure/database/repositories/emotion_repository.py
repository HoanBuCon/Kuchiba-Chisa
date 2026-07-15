from __future__ import annotations
import time
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.database.models.emotion_state import EmotionState as EmotionStateModel
from app.domain.interfaces.repositories import IEmotionRepository
from app.domain.entities.emotion import EmotionState as EmotionStateEntity


class SqlAlchemyEmotionRepository(IEmotionRepository):
    """
    SQLAlchemy implementation of IEmotionRepository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_emotion_state(self, user_id: uuid.UUID) -> EmotionStateEntity:
        stmt = select(EmotionStateModel).where(EmotionStateModel.user_id == user_id)
        result = await self.session.execute(stmt)
        state_db = result.scalar_one_or_none()
        if not state_db:
            state_db = EmotionStateModel(
                user_id=user_id,
                joy=0.10,        # Match default baseline settings
                sadness=0.00,
                trust=0.50,
                attachment=0.00,
                irritation=0.00,
                updated_at=int(time.time() * 1000)
            )
            self.session.add(state_db)
            await self.session.flush()
            await self.session.refresh(state_db)
        return EmotionStateEntity(
            user_id=state_db.user_id,
            joy=state_db.joy,
            sadness=state_db.sadness,
            trust=state_db.trust,
            attachment=state_db.attachment,
            irritation=state_db.irritation,
            updated_at=state_db.updated_at
        )

    async def update_emotion(self, emotion: EmotionStateEntity) -> None:
        stmt = select(EmotionStateModel).where(EmotionStateModel.user_id == emotion.user_id)
        result = await self.session.execute(stmt)
        state_db = result.scalar_one_or_none()
        if state_db:
            state_db.joy = emotion.joy
            state_db.sadness = emotion.sadness
            state_db.trust = emotion.trust
            state_db.attachment = emotion.attachment
            state_db.irritation = emotion.irritation
            state_db.updated_at = emotion.updated_at
        else:
            state_db = EmotionStateModel(
                user_id=emotion.user_id,
                joy=emotion.joy,
                sadness=emotion.sadness,
                trust=emotion.trust,
                attachment=emotion.attachment,
                irritation=emotion.irritation,
                updated_at=emotion.updated_at
            )
            self.session.add(state_db)
        await self.session.flush()

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        from sqlalchemy import delete
        await self.session.execute(delete(EmotionStateModel).where(EmotionStateModel.user_id == user_id).execution_options(synchronize_session=False))
        await self.session.flush()
