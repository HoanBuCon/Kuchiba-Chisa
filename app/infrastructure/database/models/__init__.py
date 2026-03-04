"""
SQLAlchemy models package.
Importing this module must load ALL models so that Alembic's `target_metadata`
can auto-detect the entire schema during migrations.
"""

from app.infrastructure.database.models.base import Base
from app.infrastructure.database.models.user import User
from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.message import Message, MessageRole
from app.infrastructure.database.models.memory_metadata import MemoryMetadata, MemoryType
from app.infrastructure.database.models.emotion import EmotionalState, AffectionLog, Mood

__all__ = [
    "Base",
    "User",
    "Conversation",
    "Message",
    "MessageRole",
    "MemoryMetadata",
    "MemoryType",
    "EmotionalState",
    "AffectionLog",
    "Mood",
]
