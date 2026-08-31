"""
Redis Write-Through User State Cache for Kuchiba Chisa.
Location: app/domain/services/user_state_cache.py

Provides high-performance (~0.2ms) reading and post-commit write-through
for UserStats and EmotionState, eliminating repeated SQL queries at Stage 1.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional, Tuple

from app.domain.entities.emotion import EmotionState as EmotionStateEntity
from app.domain.entities.user import UserStats as UserStatsEntity
from app.domain.interfaces.cache_provider import ICacheProvider
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

USER_STATE_CACHE_TTL = 7 * 24 * 3600  # 7 days with rolling expiration


class UserStateCache:
    """
    Helper for serialization, deserialization, reading and writing
    User State (Stats + Emotion + ConvId) on Redis.
    """

    @staticmethod
    def get_cache_key(user_id: uuid.UUID | str) -> str:
        return f"chisa:user:{str(user_id)}:state"

    @classmethod
    async def get_state(
        cls, cache: ICacheProvider, user_id: uuid.UUID
    ) -> Optional[Tuple[UserStatsEntity, EmotionStateEntity, Optional[uuid.UUID]]]:
        """
        Reads user state from Redis.
        Returns (UserStats, EmotionState, Optional[conv_id]) if cache hit, or None if miss/error.
        """
        if not cache:
            return None
        key = cls.get_cache_key(user_id)
        try:
            data = await cache.get_json(key)
            if not data or not isinstance(data, dict):
                return None

            stats_raw = data.get("stats", {})
            emotion_raw = data.get("emotion", {})
            conv_id_raw = data.get("conv_id")

            stats = UserStatsEntity(
                user_id=user_id,
                interaction_count=int(stats_raw.get("interaction_count", 0)),
                last_seen=int(stats_raw.get("last_seen", 0)),
            )
            emotion = EmotionStateEntity(
                user_id=user_id,
                joy=float(emotion_raw.get("joy", 0.15)),
                sadness=float(emotion_raw.get("sadness", 0.0)),
                trust=float(emotion_raw.get("trust", 0.50)),
                attachment=float(emotion_raw.get("attachment", 0.0)),
                irritation=float(emotion_raw.get("irritation", 0.0)),
                shyness=float(emotion_raw.get("shyness", 0.0)),
                curiosity=float(emotion_raw.get("curiosity", 0.10)),
                comfort=float(emotion_raw.get("comfort", 0.50)),
                updated_at=int(emotion_raw.get("updated_at", 0)),
            )
            conv_id = uuid.UUID(str(conv_id_raw)) if conv_id_raw else None
            return stats, emotion, conv_id
        except Exception as e:
            log.warning(
                "Failed to read user state from Redis cache, falling back to SQL",
                error=str(e),
                user_id=str(user_id),
            )
            return None

    @classmethod
    async def set_state(
        cls,
        cache: ICacheProvider,
        user_id: uuid.UUID,
        stats: UserStatsEntity,
        emotion: EmotionStateEntity,
        conv_id: Optional[uuid.UUID] = None,
        ttl: int = USER_STATE_CACHE_TTL,
    ) -> None:
        """
        Writes user state to Redis with rolling TTL.
        """
        if not cache:
            return
        key = cls.get_cache_key(user_id)
        payload = {
            "user_id": str(user_id),
            "stats": {
                "interaction_count": stats.interaction_count,
                "last_seen": stats.last_seen,
            },
            "emotion": {
                "joy": emotion.joy,
                "sadness": emotion.sadness,
                "trust": emotion.trust,
                "attachment": emotion.attachment,
                "irritation": emotion.irritation,
                "shyness": getattr(emotion, "shyness", 0.0),
                "curiosity": getattr(emotion, "curiosity", 0.10),
                "comfort": getattr(emotion, "comfort", 0.50),
                "updated_at": emotion.updated_at,
            },
            "conv_id": str(conv_id) if conv_id else None,
            "cached_at": int(time.time() * 1000),
        }
        try:
            await cache.set_json(key, payload, ttl=ttl)
        except Exception as e:
            log.warning(
                "Failed to save user state to Redis cache",
                error=str(e),
                user_id=str(user_id),
            )

    @classmethod
    async def invalidate(cls, cache: ICacheProvider, user_id: uuid.UUID | str) -> None:
        """
        Invalidates user state from Redis on /clear or reset.
        """
        if not cache:
            return
        key = cls.get_cache_key(user_id)
        try:
            await cache.delete(key)
        except Exception as e:
            log.warning(
                "Failed to invalidate user state cache in Redis",
                error=str(e),
                user_id=str(user_id),
            )
