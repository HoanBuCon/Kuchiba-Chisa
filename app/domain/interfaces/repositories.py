from __future__ import annotations

import uuid
from typing import Protocol, List, Optional

from app.domain.entities.user import User, UserStats
from app.domain.entities.emotion import EmotionState
from app.domain.entities.conversation import Conversation
from app.domain.entities.message import Message


class IUserRepository(Protocol):
    """
    Domain adapter port for User and UserStats persistence.
    """

    async def get_or_create_user(self, user_id: uuid.UUID) -> User:
        """
        Retrieves a user by UUID, or creates a default one if not found.
        """
        ...

    async def get_user_stats(self, user_id: uuid.UUID) -> UserStats:
        """
        Retrieves statistics for a user, or creates default stats if not found.
        """
        ...

    async def update_stats(self, stats: UserStats) -> None:
        """
        Saves changes to UserStats.
        """
        ...

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        """
        Deletes all user data (User and UserStats).
        """
        ...


class IEmotionRepository(Protocol):
    """
    Domain adapter port for EmotionState persistence.
    """

    async def get_emotion_state(self, user_id: uuid.UUID) -> EmotionState:
        """
        Retrieves Chisa's emotional state for a user, or creates a default state.
        """
        ...

    async def update_emotion(self, emotion: EmotionState) -> None:
        """
        Saves changes to EmotionState.
        """
        ...

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        """
        Deletes the EmotionState for a user.
        """
        ...


class IConversationRepository(Protocol):
    """
    Domain adapter port for Conversations and Messages history (STM).
    """

    async def get_or_create_conversation(self, user_id: uuid.UUID) -> uuid.UUID:
        """
        Retrieves the most recent active conversation ID, or creates a new one.
        """
        ...

    async def save_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        content: str,
        token_count: Optional[int] = None,
        is_success: bool = True,
    ) -> None:
        """
        Persists a new message into STM.
        """
        ...

    async def get_recent_history(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 15
    ) -> List[dict[str, str]]:
        """
        Retrieves the recent messages in a conversation as a list of dicts (oldest first).
        """
        ...

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        """
        Deletes all conversations and messages for a user.
        """
        ...
