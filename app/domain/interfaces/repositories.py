from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from app.domain.entities.emotion import EmotionState
from app.domain.entities.lore import LoreParent
from app.domain.entities.user import User, UserStats


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
        token_count: int | None = None,
        is_success: bool = True,
        rewritten_content: str | None = None,
        media_metadata: Any | None = None,
    ) -> None:
        """
        Persists a new message into STM.
        """
        ...

    async def get_last_user_rewritten_query(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str | None:
        """
        Retrieves the rewritten_content (or original content) of the most recent user message.
        """
        ...

    async def get_recent_history(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 15
    ) -> list[dict[str, str]]:
        """
        Retrieves the recent messages in a conversation as a list of dicts (oldest first).
        """
        ...

    async def get_latest_summary(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str | None:
        """
        Retrieves the latest summary string for a conversation if available.
        """
        ...

    async def update_conversation_summary(
        self, conversation_id: uuid.UUID, summary: str
    ) -> None:
        """
        Updates the summary field for a conversation.
        """
        ...

    async def delete_all_for_user(self, user_id: uuid.UUID) -> None:
        """
        Deletes all conversations and messages for a user.
        """
        ...

    async def get_image_ids_for_user(self, user_id: uuid.UUID) -> list[str]:
        """Return image object IDs referenced only by this user's messages."""
        ...


class ILoreParentRepository(Protocol):
    """
    Domain adapter port for storing and retrieving full parent lore documents.
    """

    async def get_parent(self, parent_id: uuid.UUID) -> LoreParent | None:
        """
        Retrieves a single parent document by its UUID.
        """
        ...

    async def get_parents_batch(self, parent_ids: list[uuid.UUID]) -> list[LoreParent]:
        """
        Retrieves multiple parent documents efficiently.
        """
        ...

    async def save_parent(self, parent: LoreParent) -> None:
        """
        Persists a new parent document to storage.
        """
        ...


class IChunkStateRepository(Protocol):
    async def get_chunk_state(self, chunk_id: uuid.UUID) -> dict | None:
        ...
    async def check_hash_exists(self, chunk_hash: str) -> bool:
        ...


class IEntityRepository(Protocol):
    async def get_all_entities(self) -> list[dict]:
        ...
    async def get_latest_update_timestamp(self) -> datetime | None:
        ...

class IAliasRepository(Protocol):
    async def get_all_aliases(self) -> list[dict]:
        ...


class IErasureJobRepository(Protocol):
    async def create(self, subject_hash: str) -> Any:
        ...

    async def finish(
        self,
        job_id: uuid.UUID,
        *,
        status: str,
        store_results: dict[str, str],
        error_code: str | None = None,
    ) -> None:
        ...

class IPipelineJobRepository(Protocol):
    async def create_job(self, stage: str, worker: str) -> uuid.UUID:
        ...
        
    async def update_job_status(
        self, job_id: uuid.UUID, status: str, error: str | None = None
    ) -> None:
        ...
        
    async def log_event(self, job_id: uuid.UUID, event_type: str, details: dict) -> None:
        ...
