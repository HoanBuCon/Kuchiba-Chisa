from sqlalchemy import Column, Float, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.infrastructure.database.models.base import Base

class EmotionState(Base):
    """
    Multi-User Safe Emotional State.
    Each user has exactly one isolated emotional state profile mapping.
    """
    __tablename__ = "emotion_state"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True, doc="The unique ID of the user")
    
    # Core Emotion Spectrum
    joy = Column(Float, default=0.10, nullable=False)
    sadness = Column(Float, default=0.00, nullable=False)
    trust = Column(Float, default=0.50, nullable=False)
    attachment = Column(Float, default=0.00, nullable=False)
    irritation = Column(Float, default=0.00, nullable=False)
    shyness = Column(Float, default=0.00, nullable=False)
    curiosity = Column(Float, default=0.20, nullable=False)
    comfort = Column(Float, default=0.50, nullable=False)
    
    # Unix timestamp for decay calculation
    updated_at = Column(BigInteger, nullable=False, doc="Unix timestamp in milliseconds")
