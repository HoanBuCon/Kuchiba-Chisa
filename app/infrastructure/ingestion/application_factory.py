"""Infrastructure composition root for the canonical application ingestion DAG."""

from __future__ import annotations

from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ingestion.orchestrator import IngestionOrchestrator, IngestionRunRequest
from app.application.ingestion.source_resolver import ApprovedIngestionSourceResolver
from app.application.ingestion.stages.batch_embedding_stage import BatchEmbeddingStage
from app.application.ingestion.stages.downloader_stage import DownloaderStage
from app.application.ingestion.stages.entity_resolver_stage import EntityResolverStage
from app.application.ingestion.stages.incremental_router_stage import IncrementalRouterStage
from app.application.ingestion.stages.metadata_enricher_stage import MetadataEnricherStage
from app.application.ingestion.stages.parent_builder_stage import ParentBuilderStage
from app.application.ingestion.stages.parser_stage import ParserStage
from app.application.ingestion.stages.qdrant_upsert_stage import QdrantUpsertStage
from app.application.ingestion.stages.semantic_chunk_builder_stage import SemanticChunkBuilderStage
from app.application.ingestion.stages.validation_stage import ValidationStage
from app.application.ingestion.sync_strategies.all_pages_sync import AllPagesSyncStrategy
from app.application.services.entity_cache_manager import EntityCacheManager
from app.config.settings import Settings
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.vector_store import IVectorStore
from app.infrastructure.database.repositories.corpus_release import CorpusReleaseRepository
from app.infrastructure.database.repositories.ingestion_source import IngestionSourceRepository
from app.infrastructure.database.repositories.lore_parent import LoreParentRepository
from app.infrastructure.database.repositories.postgres_chunk_state import (
    PostgresChunkStateRepository,
)
from app.infrastructure.database.repositories.postgres_entity import PostgresEntityRepository
from app.infrastructure.database.repositories.postgres_pipeline_job import (
    PostgresPipelineJobRepository,
)
from app.infrastructure.database.repositories.postgres_wiki_sync_state import (
    PostgresWikiSyncStateRepository,
)
from app.infrastructure.ingestion.mediawiki_source import MediaWikiSource
from app.infrastructure.ingestion.raw_storage import FileRawStorage


async def build_ingestion_orchestrator(
    *,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    embedder: IEmbeddingProvider,
    vector_store: IVectorStore,
    settings: Settings,
    request: IngestionRunRequest,
) -> IngestionOrchestrator:
    """Wire every port of the DAG at the infrastructure boundary.

    This function deliberately does not provision, delete, or promote a Qdrant
    collection.  The caller must provide a physical staging collection and
    `ING-02` owns quality-gated publication.
    """
    job_repository = PostgresPipelineJobRepository(session)
    raw_storage = FileRawStorage(Path(settings.INGESTION_RAW_STORAGE_DIR))
    approved_source = await ApprovedIngestionSourceResolver(
        IngestionSourceRepository(session)
    ).resolve(request.source_id)
    source = MediaWikiSource(
        http_client=http_client,
        api_url=approved_source.uri,
        categories=settings.INGESTION_WIKI_CATEGORIES.split(","),
        allowed_hosts=settings.INGESTION_ALLOWED_SOURCE_HOSTS.split(","),
        timeout_seconds=settings.INGESTION_SOURCE_TIMEOUT_SECONDS,
        max_retries=settings.INGESTION_SOURCE_MAX_RETRIES,
    )
    entity_cache = EntityCacheManager(PostgresEntityRepository(session))

    return IngestionOrchestrator(
        downloader=DownloaderStage(
            source=source,
            sync_state_repository=PostgresWikiSyncStateRepository(session),
            sync_strategy=AllPagesSyncStrategy(),
            raw_storage=raw_storage,
            job_repository=job_repository,
        ),
        parser=ParserStage(raw_storage=raw_storage, job_repo=job_repository),
        parent_builder=ParentBuilderStage(job_repo=job_repository),
        semantic_chunk_builder=SemanticChunkBuilderStage(job_repo=job_repository),
        entity_resolver=EntityResolverStage(cache_manager=entity_cache, job_repo=job_repository),
        metadata_enricher=MetadataEnricherStage(job_repo=job_repository),
        validator=ValidationStage(job_repo=job_repository),
        incremental_router=IncrementalRouterStage(
            chunk_repo=PostgresChunkStateRepository(session),
            job_repo=job_repository,
        ),
        batch_embedding=BatchEmbeddingStage(provider=embedder, job_repo=job_repository),
        qdrant_upsert=QdrantUpsertStage(vector_store=vector_store, job_repo=job_repository),
        parent_repository=LoreParentRepository(session),
        release_repository=CorpusReleaseRepository(session),
        job_repository=job_repository,
        source_access=approved_source.access_policy.access,
    )
