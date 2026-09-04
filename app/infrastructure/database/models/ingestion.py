import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class IngestionSourceModel(Base):
    """Persistent source governance state; corpus workers only read approved rows."""

    __tablename__ = "ingestion_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    license_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    access_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    channel_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trust_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    crawl_schedule: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class IngestionSourceAuditEventModel(Base):
    """Append-only source governance audit metadata; no corpus text is stored."""

    __tablename__ = "ingestion_source_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_sources.id"), nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_status: Mapped[str] = mapped_column(String(16), nullable=False)
    old_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CorpusReleaseModel(Base):
    """Durable, non-content receipt for a staged versioned lore corpus."""

    __tablename__ = "corpus_releases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_jobs.id"), nullable=False, unique=True, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_sources.id"), nullable=False, index=True
    )
    logical_collection: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    staging_collection: Mapped[str] = mapped_column(String(192), nullable=False, unique=True)
    corpus_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parent_count: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_count: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    vector_manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_active_collection: Mapped[str | None] = mapped_column(String(192), nullable=True)


class CorpusReleaseAuditEventModel(Base):
    """Append-only release audit record without corpus content or provider output."""

    __tablename__ = "corpus_release_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus_releases.id"), nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    old_corpus_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_corpus_version: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CorpusReleaseQualityReportModel(Base):
    """Versioned aggregate evaluator outcome; no prompts, answers, or source text."""

    __tablename__ = "corpus_release_quality_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_releases.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    evaluator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_interval: Mapped[float] = mapped_column(nullable=False)
    faithfulness: Mapped[float] = mapped_column(nullable=False)
    answer_relevance: Mapped[float] = mapped_column(nullable=False)
    context_recall: Mapped[float] = mapped_column(nullable=False)
    context_precision: Mapped[float] = mapped_column(nullable=False)
    citation_correctness: Mapped[float] = mapped_column(nullable=False)
    retrieval_hit_at_5: Mapped[float] = mapped_column(nullable=False)
    retrieval_mrr_at_10: Mapped[float] = mapped_column(nullable=False)
    critical_unsupported_claims: Mapped[int] = mapped_column(Integer, nullable=False)
    cross_tenant_leakage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_leakage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    human_audit_completed: Mapped[bool] = mapped_column(nullable=False)
    security_slice_passed: Mapped[bool] = mapped_column(nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
