from __future__ import annotations

import time
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User as UserEntity
from app.domain.entities.user import UserStats as UserStatsEntity
from app.domain.interfaces.repositories import IUserRepository
from app.infrastructure.database.models.user import User as UserModel
from app.infrastructure.database.models.user_stats import UserStats as UserStatsModel


class SqlAlchemyUserRepository(IUserRepository):
    """
    SQLAlchemy implementation of IUserRepository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_user(self, user_id: uuid.UUID) -> UserEntity:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        user_db = result.scalar_one_or_none()
        if not user_db:
            user_db = UserModel(id=user_id, username=f"web_user_{str(user_id)[:6]}")
            self.session.add(user_db)
            await self.session.flush()
            await self.session.refresh(user_db)
        return UserEntity(
            id=user_db.id,
            username=user_db.username,
            is_active=user_db.is_active,
            discord_id=user_db.discord_id
        )

    async def get_user_stats(self, user_id: uuid.UUID) -> UserStatsEntity:
        stmt = select(UserStatsModel).where(UserStatsModel.user_id == user_id)
        result = await self.session.execute(stmt)
        stats_db = result.scalar_one_or_none()
        if not stats_db:
            stats_db = UserStatsModel(
                user_id=user_id,
                interaction_count=0,
                last_seen=int(time.time() * 1000)
            )
            self.session.add(stats_db)
            await self.session.flush()
            await self.session.refresh(stats_db)
        return UserStatsEntity(
            user_id=stats_db.user_id,
            interaction_count=stats_db.interaction_count,
            last_seen=stats_db.last_seen,
            state_revision=stats_db.state_revision,
        )

    async def apply_interaction(
        self, user_id: uuid.UUID, *, last_seen: int
    ) -> UserStatsEntity:
        row = (
            await self.session.execute(
                update(UserStatsModel)
                .where(UserStatsModel.user_id == user_id)
                .values(
                    interaction_count=UserStatsModel.interaction_count + 1,
                    last_seen=func.greatest(UserStatsModel.last_seen, last_seen),
                    state_revision=UserStatsModel.state_revision + 1,
                )
                .returning(UserStatsModel)
            )
        ).scalar_one()
        return UserStatsEntity(
            user_id=row.user_id,
            interaction_count=row.interaction_count,
            last_seen=row.last_seen,
            state_revision=row.state_revision,
        )

    async def update_stats(self, stats: UserStatsEntity) -> None:
        stmt = select(UserStatsModel).where(UserStatsModel.user_id == stats.user_id)
        result = await self.session.execute(stmt)
        stats_db = result.scalar_one_or_none()
        if stats_db:
            stats_db.interaction_count = stats.interaction_count
            stats_db.last_seen = stats.last_seen
        else:
            stats_db = UserStatsModel(
                user_id=stats.user_id,
                interaction_count=stats.interaction_count,
                last_seen=stats.last_seen,
                state_revision=stats.state_revision,
            )
            self.session.add(stats_db)
        await self.session.flush()

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        from sqlalchemy import delete
        await self.session.execute(delete(UserStatsModel).where(UserStatsModel.user_id == user_id).execution_options(synchronize_session=False))
        await self.session.execute(
            delete(UserModel)
            .where(UserModel.id == user_id)
            .execution_options(synchronize_session=False)
        )
        await self.session.flush()
