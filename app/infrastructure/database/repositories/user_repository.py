from __future__ import annotations

import time
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.infrastructure.database.models.user import User
from app.infrastructure.database.models.user_stats import UserStats
from app.domain.interfaces.repositories import IUserRepository


class SqlAlchemyUserRepository(IUserRepository):
    """
    SQLAlchemy implementation of IUserRepository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_user(self, user_id: uuid.UUID) -> User:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            user = User(id=user_id, username=f"web_user_{str(user_id)[:6]}")
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
        return user

    async def get_user_stats(self, user_id: uuid.UUID) -> UserStats:
        stmt = select(UserStats).where(UserStats.user_id == user_id)
        result = await self.session.execute(stmt)
        stats = result.scalar_one_or_none()
        if not stats:
            stats = UserStats(
                user_id=user_id,
                interaction_count=0,
                last_seen=int(time.time() * 1000)
            )
            self.session.add(stats)
            await self.session.commit()
            await self.session.refresh(stats)
        return stats

    async def update_stats(self, stats: UserStats) -> None:
        self.session.add(stats)
        await self.session.commit()
