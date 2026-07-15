from __future__ import annotations

import uuid
from typing import Protocol, List, Optional
from datetime import datetime

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

from app.domain.entities.lore import LoreParent

class ILoreParentRepository(Protocol):
    """
    Domain adapter port for storing and retrieving full parent lore documents.
    """

    async def get_parent(self, parent_id: uuid.UUID) -> Optional[LoreParent]:
        """
        Retrieves a single parent document by its UUID.
        """
        ...

    async def get_parents_batch(self, parent_ids: List[uuid.UUID]) -> List[LoreParent]:
        """
        Retrieves multiple parent documents efficiently.
        """
        ...

    async def save_parent(self, parent: LoreParent) -> None:
        """
        Persists a new parent document to storage.
        """
        ...

class IWikiSyncRepository(Protocol):
    """
    Domain adapter port for tracking Wiki page synchronization state in Postgres.
    """

    async def get_latest_revision_id(self, page_id: int) -> Optional[int]:
        """
        Returns the last synced revision ID for a given page, or None if never synced.
        """
        ...

    async def update_sync_state(self, page_id: int, title: str, revision_id: int, status: str) -> None:
        """
        Updates the sync status and revision ID for a page.
        """
        ...

class IChunkStateRepository(Protocol):
    async def get_chunk_state(self, chunk_id: uuid.UUID) -> Optional[dict]:
        ...
    async def check_hash_exists(self, chunk_hash: str) -> bool:
        ...
        
class IEntityRepository(Protocol):
    async def get_all_entities(self) -> List[dict]:
        ...
    async def get_latest_update_timestamp(self) -> Optional[datetime]:
        ...

class IAliasRepository(Protocol):
    async def get_all_aliases(self) -> List[dict]:
        ...

class IPipelineJobRepository(Protocol):
    async def create_job(self, stage: str, worker: str) -> uuid.UUID:
        ...
        
    async def update_job_status(self, job_id: uuid.UUID, status: str, error: Optional[str] = None) -> None:
        ...
        
    async def log_event(self, job_id: uuid.UUID, event_type: str, details: dict) -> None:
        ...
