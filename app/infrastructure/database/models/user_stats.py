import uuid

from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class UserStats(Base):
    """
    Tracks analytical metadata for users to drive emergent behaviors like Attachment Growth.
    attachment_bonus = log(interaction_count + 1) * 0.05
    """
    __tablename__ = "user_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    interaction_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Total conversation turns",
    )
    last_seen: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Unix timestamp in milliseconds",
    )
