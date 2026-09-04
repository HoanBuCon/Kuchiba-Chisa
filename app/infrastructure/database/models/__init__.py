"""
SQLAlchemy models package.
Importing this module must load ALL models so that Alembic's `target_metadata`
can auto-detect the entire schema during migrations.
"""

from app.infrastructure.database.models.base import Base
from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.emotion_state import EmotionState
from app.infrastructure.database.models.erasure_job import ErasureJobModel
from app.infrastructure.database.models.ingestion import (
    AliasModel,
    ChunkStateModel,
    EntityModel,
    EntityRelationshipModel,
    IngestionMetricModel,
    PipelineEventModel,
    PipelineJobModel,
    WikiSyncStateModel,
)
from app.infrastructure.database.models.lore_parent import LoreParentModel
from app.infrastructure.database.models.memory_metadata import MemoryMetadata, MemoryType
from app.infrastructure.database.models.message import Message, MessageRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.models.user_stats import UserStats

__all__ = [
    "Base",
    "User",
    "Conversation",
    "Message",
    "MessageRole",
    "MemoryMetadata",
    "MemoryType",
    "EmotionState",
    "ErasureJobModel",
    "UserStats",
    "LoreParentModel",
    "WikiSyncStateModel",
    "ChunkStateModel",
    "PipelineJobModel",
    "PipelineEventModel",
    "IngestionMetricModel",
    "EntityModel",
    "AliasModel",
    "EntityRelationshipModel",
]
