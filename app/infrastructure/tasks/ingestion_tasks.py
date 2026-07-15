import asyncio
import uuid
from typing import List

from app.domain.entities.wiki import DownloadedPage
from app.application.ingestion.stages.parser_stage import ParserStage, ParserInput
from app.application.ingestion.stages.parent_builder_stage import ParentBuilderStage, ParentBuilderInput
from app.application.ingestion.stages.semantic_chunk_builder_stage import SemanticChunkBuilderStage, SemanticChunkBuilderInput
from app.application.ingestion.stages.entity_resolver_stage import EntityResolverStage, EntityResolverInput
from app.application.ingestion.stages.metadata_enricher_stage import MetadataEnricherStage, MetadataEnricherInput
from app.application.ingestion.stages.validation_stage import ValidationStage, ValidationInput
from app.application.ingestion.stages.incremental_router_stage import IncrementalRouterStage, IncrementalRouterInput
from app.application.ingestion.stages.batch_embedding_stage import BatchEmbeddingStage, BatchEmbeddingInput
from app.application.ingestion.stages.qdrant_upsert_stage import QdrantUpsertStage, QdrantUpsertInput

from app.shared.utils.logger import get_logger

log = get_logger(__name__)

from app.infrastructure.tasks.celery_app import celery_app

@celery_app.task(name="process_page_task")
def process_page_task(page_data: dict):
    """
    Celery task that processes a single Wiki page through the entire ingestion pipeline.
    Avoids IPC serialization overhead by executing all 9 micro-stages sequentially in one worker.
    """
    page = DownloadedPage(**page_data)
    log.info("Starting ProcessPageTask", page_id=page.page_id, title=page.title)
    asyncio.run(_async_process_page(page))

async def _async_process_page(page: DownloadedPage):
    from app.infrastructure.database.engine import AsyncSessionFactory
    from app.infrastructure.storage.filesystem_storage import FilesystemStorage
    from app.infrastructure.database.repositories.postgres_pipeline_job import PostgresPipelineJobRepository
    from app.infrastructure.database.repositories.postgres_chunk_state import PostgresChunkStateRepository
    from app.infrastructure.database.repositories.postgres_entity import PostgresEntityRepository
    from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
    from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
    from app.application.services.entity_cache_manager import EntityCacheManager

    async with AsyncSessionFactory() as session:
        job_repo = PostgresPipelineJobRepository(session)
        chunk_repo = PostgresChunkStateRepository(session)
        
        # We need a real job in the DB to log events
        job_id = await job_repo.create_job("process_page", "celery_worker_1")
        
        raw_storage = FilesystemStorage()
        embedder = FastEmbedAdapter()
        entity_repo = PostgresEntityRepository(session)
        entity_manager = EntityCacheManager(entity_repo)
        await entity_manager.start_polling() # This loads the cache initially
        
        parser_stage = ParserStage(raw_storage, job_repo)
        parent_builder = ParentBuilderStage(job_repo)
        chunk_builder = SemanticChunkBuilderStage(job_repo)
        entity_resolver = EntityResolverStage(entity_manager, job_repo)
        metadata_enricher = MetadataEnricherStage(job_repo)
        validator = ValidationStage(job_repo)
        incremental_router = IncrementalRouterStage(chunk_repo, job_repo)
        batch_embedding = BatchEmbeddingStage(embedder, job_repo)
        qdrant_upsert = QdrantUpsertStage(qdrant_service, job_repo)
        
        # 1. Parse
        parsed_result = await parser_stage.execute(job_id, ParserInput(downloaded_pages=[page]))
        if not parsed_result.output:
            log.warning("Parser returned empty", page_id=page.page_id)
            return
            
        # 2. Parent Builder
        parents_result = await parent_builder.execute(job_id, ParentBuilderInput(parsed_page=parsed_result.output[0]))
        
        # 3. Chunk Builder
        chunks_result = await chunk_builder.execute(job_id, SemanticChunkBuilderInput(parents=parents_result.output))
        
        # 4. Entity Extractor/Resolver
        chunks_result = await entity_resolver.execute(job_id, EntityResolverInput(chunks=chunks_result.output))
        
        # 5. Metadata Enricher
        chunks_result = await metadata_enricher.execute(job_id, MetadataEnricherInput(chunks=chunks_result.output))
        
        # 6. Validation
        chunks_result = await validator.execute(job_id, ValidationInput(chunks=chunks_result.output))
        
        # 7. Incremental Router
        chunks_result = await incremental_router.execute(job_id, IncrementalRouterInput(chunks=chunks_result.output))
        
        # 8. Batch Embedding
        chunks_result = await batch_embedding.execute(job_id, BatchEmbeddingInput(chunks=chunks_result.output))
        
        # 9. Qdrant Upsert
        chunks_result = await qdrant_upsert.execute(job_id, QdrantUpsertInput(chunks=chunks_result.output))
        
        log.info("ProcessPageTask completed successfully", page_id=page.page_id, chunks_upserted=len(chunks_result.output))
