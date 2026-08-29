from __future__ import annotations
from functools import cached_property
from app.config.settings import settings
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt, LLMResponse
from app.domain.services.chat_engine import ChatEngine
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.memory_extractor import MemoryExtractor
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.shared.utils.circuit_breaker import llm_circuit_breaker
from typing import AsyncIterator

class LLMCircuitBreakerProxy(BaseLLMAdapter):
    """Proxy to apply circuit breaker pattern to any LLM adapter."""
    def __init__(self, adapter: BaseLLMAdapter):
        self.adapter = adapter
    
    def __getattr__(self, name):
        return getattr(self.adapter, name)
    
    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        llm_circuit_breaker.check_state()
        try:
            res = await self.adapter.generate(prompt)
            llm_circuit_breaker.record_success()
            return res
        except Exception as e:
            llm_circuit_breaker.record_failure(e)
            raise

    async def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
        llm_circuit_breaker.check_state()
        try:
            async for chunk in self.adapter.stream(prompt):
                yield chunk
            llm_circuit_breaker.record_success()
        except Exception as e:
            llm_circuit_breaker.record_failure(e)
            raise
            
    async def validate_response(self, raw: str, schema: dict) -> dict:
        return await self.adapter.validate_response(raw, schema)
        
    async def estimate_tokens(self, text: str) -> int:
        return await self.adapter.estimate_tokens(text)

class AppContainer:
    """Dependency Injection Container for the application."""

    @cached_property
    def http_client(self) -> httpx.AsyncClient:
        import httpx
        return httpx.AsyncClient(timeout=10.0, follow_redirects=True)

    @cached_property
    def embedder(self) -> IEmbeddingProvider:
        return FastEmbedAdapter()

    @cached_property
    def llm(self) -> BaseLLMAdapter:
        if settings.LLM_PROVIDER == "gemini":
            from app.infrastructure.llm.adapters.gemini import GeminiAdapter
            raw_adapter = GeminiAdapter()
        elif settings.LLM_PROVIDER == "deepseek":
            from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
            raw_adapter = DeepSeekAdapter(http_client=self.http_client)
        else:
            from app.infrastructure.llm.adapters.groq import GroqAdapter
            raw_adapter = GroqAdapter()
            
        return LLMCircuitBreakerProxy(raw_adapter)

    @cached_property
    def context_builder(self) -> ContextBuilder:
        return ContextBuilder()

    @cached_property
    def memory_extractor(self) -> MemoryExtractor:
        return MemoryExtractor(
            llm=self.llm,
            embedder=self.embedder,
            vector_store=qdrant_service,
        )

    @cached_property
    def vector_store(self):
        return qdrant_service

    @cached_property
    def entity_resolver(self) -> Any:
        from app.domain.services.rag.entity_resolver import EntityResolver
        res = EntityResolver()
        res.load()
        return res

    @cached_property
    def chat_engine(self) -> ChatEngine:
        from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
        from app.infrastructure.database.repositories.emotion_repository import SqlAlchemyEmotionRepository
        from app.infrastructure.database.repositories.conversation_repository import SqlAlchemyConversationRepository
        from app.infrastructure.database.repositories.lore_parent import LoreParentRepository
        from app.infrastructure.database.uow import UnitOfWork
        from app.infrastructure.cache.redis.redis_service import redis_service
        from app.domain.services.intent_classifier import IntentClassifier
        from app.domain.services.tool_router import LLMToolRouter
        from app.domain.services.emotion_engine import EmotionEngine
        from app.domain.services.chat_engine import ChatPipeline
        from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
        from app.infrastructure.logging.llm_logger import log_routing_transaction, log_llm_transaction
        from app.infrastructure.database.engine import AsyncSessionFactory
        from app.domain.services.chat_pipeline.stages.initialization_stage import InitializationStage
        from app.domain.services.chat_pipeline.stages.intent_stage import IntentStage
        from app.domain.services.chat_pipeline.stages.cache_stage import CacheStage
        from app.domain.services.chat_pipeline.stages.tool_routing_stage import ToolRoutingStage
        from app.domain.services.chat_pipeline.stages.rag_stage import RAGStage
        from app.domain.services.chat_pipeline.stages.context_building_stage import ContextBuildingStage
        from app.domain.services.chat_pipeline.stages.llm_generation_stage import LLMGenerationStage
        from app.domain.services.chat_pipeline.stages.emotion_update_stage import EmotionUpdateStage
        from app.domain.services.chat_pipeline.stages.persistence_stage import PersistenceStage
        from app.domain.services.chat_pipeline.stages.cache_update_stage import CacheUpdateStage
        from app.domain.services.chat_pipeline.stages.background_task_stage import BackgroundTaskStage
        
        entity_resolver = self.entity_resolver
        intent_classifier = IntentClassifier(llm=self.llm, embedder=self.embedder, entity_resolver=entity_resolver)
        
        # Tools registration
        from app.domain.services.tools.web_search import WebSearchAgentTool
        from app.domain.services.tools.summarize import ConversationSummarizerAgentTool
        from app.domain.services.tools.emotion_report import EmotionReportAgentTool
        from app.infrastructure.search.providers import (
            TavilySearchProvider,
            SerperSearchProvider,
            DDGScraperSearchProvider
        )
        
        web_search_providers = [
            TavilySearchProvider(http_client=self.http_client),
            SerperSearchProvider(http_client=self.http_client),
            DDGScraperSearchProvider(http_client=self.http_client),
        ]
        
        import httpx
        import asyncio
        async def fetch_page(url: str) -> str:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            if "wikipedia.org" in url:
                headers["User-Agent"] = "KuchibaChisa/2.1 (contact: bot@chisa.ai) Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            try:
                resp = await self.http_client.get(url, timeout=3.5, headers=headers, follow_redirects=True)
                if resp.status_code == 200:
                    return resp.text
            except Exception as e:
                from app.infrastructure.logging.logger import get_logger
                _dep_log = get_logger(__name__)
                _dep_log.debug("Web search page fetch failed", url=url, error=str(e))
            return ""

        agent_tools = [
            WebSearchAgentTool(providers=web_search_providers, page_fetcher=fetch_page),
            ConversationSummarizerAgentTool(),
            EmotionReportAgentTool()
        ]
        
        tool_router = LLMToolRouter(llm=self.llm, embedder=self.embedder, tools=agent_tools)
        emotion_engine = EmotionEngine()

        # Build stages
        # To handle the _auto_summarize_conversation and _summarize_and_store_memories callbacks,
        # we will create a partial ChatEngine and attach the callbacks to it.
        # But wait, we can just instantiate ChatEngine and pass its methods to stages!
        
        # We need a two-step initialization for ChatEngine because stages need callbacks, 
        # and ChatEngine needs pipeline.
        
        # Instantiate RAG dependencies
        from app.domain.services.rag.pipeline import RAGPipeline
        from app.domain.services.rag.retriever_memory import MemoryRetriever
        from app.domain.services.rag.retriever_lore import LoreRetriever
        from app.domain.services.rag.assessor import ContextAssessor
        from app.domain.services.rag.thinking_loop import ThinkingLoopAgent
        
        rag_pipeline = RAGPipeline(
            memory_retriever=MemoryRetriever(vector_store=qdrant_service),
            lore_retriever=LoreRetriever(
                vector_store=qdrant_service,
                lore_parent_repo_factory=LoreParentRepository
            ),
            assessor=ContextAssessor(),
            thinking_loop_agent=ThinkingLoopAgent(pipeline_tracker=pipeline_tracker),
            pipeline_tracker=pipeline_tracker,
            entity_resolver=entity_resolver
        )
        
        from app.domain.services.rag.query_rewriter import QueryRewriter
        query_rewriter = QueryRewriter(llm=self.llm, entity_resolver=entity_resolver)

        # Let's instantiate ChatPipeline first, we can use a lambda to defer the callback.
        engine_ref: list[ChatEngine] = []

        stages = [
            InitializationStage(
                user_repo_factory=SqlAlchemyUserRepository,
                emotion_repo_factory=SqlAlchemyEmotionRepository,
                conv_repo_factory=SqlAlchemyConversationRepository,
                cache_provider=redis_service,
                pipeline_tracker=pipeline_tracker
            ),
            IntentStage(
                intent_classifier=intent_classifier,
                embedder=self.embedder,
                query_rewriter=query_rewriter,
                conv_repo_factory=SqlAlchemyConversationRepository,
                pipeline_tracker=pipeline_tracker
            ),
            CacheStage(
                cache=redis_service,
                pipeline_tracker=pipeline_tracker
            ),
            ToolRoutingStage(
                tool_router=tool_router,
                cache=redis_service,
                conv_repo_factory=SqlAlchemyConversationRepository,
                emotion_repo_factory=SqlAlchemyEmotionRepository,
                pipeline_tracker=pipeline_tracker,
                routing_logger_callback=log_routing_transaction
            ),
            RAGStage(
                llm=self.llm,
                embedder=self.embedder,
                tool_router=tool_router,
                rag_pipeline=rag_pipeline
            ),
            ContextBuildingStage(
                context_builder=self.context_builder,
                pipeline_tracker=pipeline_tracker
            ),
            LLMGenerationStage(
                llm=self.llm,
                llm_logger_callback=log_llm_transaction,
                pipeline_tracker=pipeline_tracker
            ),
            EmotionUpdateStage(
                emotion_engine=emotion_engine,
                emotion_repo_factory=SqlAlchemyEmotionRepository,
                cache_provider=redis_service,
                pipeline_tracker=pipeline_tracker
            ),
            PersistenceStage(
                user_repo_factory=SqlAlchemyUserRepository,
                conv_repo_factory=SqlAlchemyConversationRepository,
                pipeline_tracker=pipeline_tracker
            ),
            CacheUpdateStage(
                cache=redis_service
            ),
            BackgroundTaskStage(
                memory_extractor=self.memory_extractor,
                unified_auto_summarize_callback=lambda uid, cid: engine_ref[0]._unified_auto_summarize(uid, cid),
                pipeline_tracker=pipeline_tracker
            )
        ]

        
        pipeline = ChatPipeline(stages=stages)
        
        engine = ChatEngine(
            pipeline=pipeline,
            uow_factory=UnitOfWork,
            cache_provider=redis_service,
            emotion_repo_factory=SqlAlchemyEmotionRepository,
            conv_repo_factory=SqlAlchemyConversationRepository,
            user_repo_factory=SqlAlchemyUserRepository,
            db_session_factory=AsyncSessionFactory,
            llm=self.llm,
            embedder=self.embedder,
            vector_store=qdrant_service
        )
        engine_ref.append(engine)
        
        return engine

    @cached_property
    def clear_user_memory_use_case(self):
        from app.application.usecases.clear_user_memory import ClearUserMemoryUseCase
        from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
        from app.infrastructure.database.repositories.emotion_repository import SqlAlchemyEmotionRepository
        from app.infrastructure.database.repositories.conversation_repository import SqlAlchemyConversationRepository
        from app.infrastructure.database.uow import UnitOfWork
        
        return ClearUserMemoryUseCase(
            uow_factory=UnitOfWork,
            user_repo_factory=SqlAlchemyUserRepository,
            emotion_repo_factory=SqlAlchemyEmotionRepository,
            conv_repo_factory=SqlAlchemyConversationRepository,
            vector_store=qdrant_service
        )

# Global container instance
container = AppContainer()


def get_chat_engine() -> ChatEngine:
    """FastAPI Dependency for injecting ChatEngine."""
    return container.chat_engine

def get_clear_user_memory_use_case():
    """FastAPI Dependency for injecting ClearUserMemoryUseCase."""
    return container.clear_user_memory_use_case

async def get_vector_store():
    return qdrant_service

async def get_entity_resolver():
    from app.domain.services.rag.entity_resolver import EntityResolver
    resolver = EntityResolver()
    resolver.load()
    return resolver

async def get_embedder():
    return container.embedder
