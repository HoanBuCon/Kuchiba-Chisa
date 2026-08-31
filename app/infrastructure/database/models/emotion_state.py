import uuid

from sqlalchemy import BigInteger, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class EmotionState(Base):
    """
    Multi-User Safe Emotional State.
    Each user has exactly one isolated emotional state profile mapping.
    """
    __tablename__ = "emotion_state"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
        doc="The unique ID of the user",
    )
    
    # Core Emotion Spectrum
    joy: Mapped[float] = mapped_column(Float, default=0.15, nullable=False)
    sadness: Mapped[float] = mapped_column(Float, default=0.00, nullable=False)
    trust: Mapped[float] = mapped_column(Float, default=0.50, nullable=False)
    attachment: Mapped[float] = mapped_column(Float, default=0.00, nullable=False)
    irritation: Mapped[float] = mapped_column(Float, default=0.00, nullable=False)
    shyness: Mapped[float] = mapped_column(Float, default=0.00, nullable=False)
    curiosity: Mapped[float] = mapped_column(Float, default=0.10, nullable=False)
    comfort: Mapped[float] = mapped_column(Float, default=0.50, nullable=False)
    
    # Unix timestamp for decay calculation
    updated_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Unix timestamp in milliseconds",
    )
