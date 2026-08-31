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
            try:
                state_db = EmotionStateModel(
                    user_id=user_id,
                    joy=0.15,        # Match default baseline settings
                    sadness=0.00,
                    trust=0.50,
                    attachment=0.00,
                    irritation=0.00,
                    shyness=0.00,
                    curiosity=0.10,
                    comfort=0.50,
                    updated_at=int(time.time() * 1000)
                )
                self.session.add(state_db)
                await self.session.flush()
                await self.session.refresh(state_db)
            except Exception:
                return EmotionStateEntity(
                    user_id=user_id,
                    joy=0.15,
                    sadness=0.00,
                    trust=0.50,
                    attachment=0.00,
                    irritation=0.00,
                    shyness=0.00,
                    curiosity=0.10,
                    comfort=0.50,
                    updated_at=int(time.time() * 1000)
                )
        return EmotionStateEntity(
            user_id=state_db.user_id,
            joy=float(state_db.joy) if getattr(state_db, "joy", None) is not None else 0.15,
            sadness=float(state_db.sadness) if getattr(state_db, "sadness", None) is not None else 0.00,
            trust=float(state_db.trust) if getattr(state_db, "trust", None) is not None else 0.50,
            attachment=float(state_db.attachment) if getattr(state_db, "attachment", None) is not None else 0.00,
            irritation=float(state_db.irritation) if getattr(state_db, "irritation", None) is not None else 0.00,
            shyness=float(state_db.shyness) if getattr(state_db, "shyness", None) is not None else 0.00,
            curiosity=float(state_db.curiosity) if getattr(state_db, "curiosity", None) is not None else 0.10,
            comfort=float(state_db.comfort) if getattr(state_db, "comfort", None) is not None else 0.50,
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
            state_db.shyness = getattr(emotion, "shyness", 0.0)
            state_db.curiosity = getattr(emotion, "curiosity", 0.20)
            state_db.comfort = getattr(emotion, "comfort", 0.50)
            state_db.updated_at = emotion.updated_at
        else:
            state_db = EmotionStateModel(
                user_id=emotion.user_id,
                joy=emotion.joy,
                sadness=emotion.sadness,
                trust=emotion.trust,
                attachment=emotion.attachment,
                irritation=emotion.irritation,
                shyness=getattr(emotion, "shyness", 0.0),
                curiosity=getattr(emotion, "curiosity", 0.20),
                comfort=getattr(emotion, "comfort", 0.50),
                updated_at=emotion.updated_at
            )
            self.session.add(state_db)
        await self.session.flush()

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        from sqlalchemy import delete
        await self.session.execute(delete(EmotionStateModel).where(EmotionStateModel.user_id == user_id).execution_options(synchronize_session=False))
        await self.session.flush()
