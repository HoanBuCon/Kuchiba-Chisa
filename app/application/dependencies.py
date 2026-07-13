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
    def embedder(self) -> IEmbeddingProvider:
        return FastEmbedAdapter()

    @cached_property
    def llm(self) -> BaseLLMAdapter:
        if settings.LLM_PROVIDER == "gemini":
            from app.infrastructure.llm.adapters.gemini import GeminiAdapter
            raw_adapter = GeminiAdapter()
        elif settings.LLM_PROVIDER == "deepseek":
            from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
            raw_adapter = DeepSeekAdapter()
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
    def chat_engine(self) -> ChatEngine:
        from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
        from app.infrastructure.database.repositories.emotion_repository import SqlAlchemyEmotionRepository
        from app.infrastructure.database.repositories.conversation_repository import SqlAlchemyConversationRepository
        from app.infrastructure.database.uow import UnitOfWork
        
        return ChatEngine(
            embedder=self.embedder,
            llm=self.llm,
            context_builder=self.context_builder,
            memory_extractor=self.memory_extractor,
            vector_store=qdrant_service,
            user_repo_factory=SqlAlchemyUserRepository,
            emotion_repo_factory=SqlAlchemyEmotionRepository,
            conv_repo_factory=SqlAlchemyConversationRepository,
            uow_factory=UnitOfWork,
        )


# Global container instance
container = AppContainer()


def get_chat_engine() -> ChatEngine:
    """FastAPI Dependency for injecting ChatEngine."""
    return container.chat_engine
