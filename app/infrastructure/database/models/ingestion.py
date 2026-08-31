import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class WikiSyncStateModel(Base):
    __tablename__ = "wiki_sync_state"
    
    page_id = Column(Integer, primary_key=True)
    page_title = Column(String, nullable=False, index=True)
    revision_id = Column(Integer, nullable=False)
    content_hash = Column(String, nullable=True)
    sync_status = Column(String, nullable=False)
    last_synced_at = Column(DateTime, default=datetime.utcnow)

class ChunkStateModel(Base):
    __tablename__ = "chunk_state"
    
    chunk_id = Column(UUID(as_uuid=True), primary_key=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("lore_parents.id"), nullable=False, index=True)
    chunk_hash = Column(String, nullable=False, index=True)
    embedded = Column(Boolean, default=False)
    embedding_model = Column(String, nullable=True)
    embedding_dimension = Column(Integer, nullable=True)
    embedding_version = Column(String, nullable=True)
    schema_version = Column(Integer, default=1)
    parser_version = Column(String, nullable=True)
    dictionary_version = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PipelineJobModel(Base):
    __tablename__ = "pipeline_jobs"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    worker: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    elapsed_ms = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0)
    statistics = Column(Text, nullable=True) # JSON payload
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

class PipelineEventModel(Base):
    __tablename__ = "pipeline_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_jobs.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False) # e.g., 'Download', 'Parse', 'Chunk'
    details = Column(Text, nullable=True) # JSON payload
    created_at = Column(DateTime, default=datetime.utcnow)

class IngestionMetricModel(Base):
    __tablename__ = "ingestion_metrics"
    
    run_id = Column(UUID(as_uuid=True), primary_key=True)
    downloaded_pages = Column(Integer, default=0)
    parsed_pages = Column(Integer, default=0)
    parent_documents = Column(Integer, default=0)
    child_chunks = Column(Integer, default=0)
    embedded_chunks = Column(Integer, default=0)
    failed_chunks = Column(Integer, default=0)
    unknown_entities = Column(Integer, default=0)
    total_duration_ms = Column(Integer, default=0)

from sqlalchemy.orm import relationship


class EntityModel(Base):
    __tablename__ = "entities"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name = Column(String, nullable=False, unique=True, index=True)
    entity_type = Column(String, nullable=True)
    region = Column(String, nullable=True)
    faction = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    aliases = relationship("AliasModel", back_populates="entity")

class AliasModel(Base):
    __tablename__ = "aliases"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False, index=True)
    alias = Column(String, nullable=False, unique=True, index=True)

    entity = relationship("EntityModel", back_populates="aliases")

class EntityRelationshipModel(Base):
    __tablename__ = "entity_relationships"
    
    source_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True)
    target_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), primary_key=True)
    relationship_type = Column(String, nullable=False)
