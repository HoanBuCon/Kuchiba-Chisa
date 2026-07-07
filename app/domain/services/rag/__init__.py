from typing import Any, List, Tuple, Dict, Optional
from app.domain.services.rag.base import ScoredMemory, RAGContext
from app.domain.services.rag.retriever_memory import MemoryRetriever
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.domain.services.rag.assessor import ContextAssessor
from app.domain.services.rag.thinking_loop import ThinkingLoopAgent
from app.domain.services.rag.pipeline import RAGPipeline

# Singleton instances
memory_retriever = MemoryRetriever()
lore_retriever = LoreRetriever()
context_assessor = ContextAssessor()
thinking_loop_agent = ThinkingLoopAgent()

rag_pipeline = RAGPipeline(
    memory_retriever=memory_retriever,
    lore_retriever=lore_retriever,
    assessor=context_assessor,
    thinking_loop_agent=thinking_loop_agent
)

__all__ = [
    "ScoredMemory",
    "RAGContext",
    "MemoryRetriever",
    "LoreRetriever",
    "ContextAssessor",
    "ThinkingLoopAgent",
    "RAGPipeline",
    "memory_retriever",
    "lore_retriever",
    "context_assessor",
    "thinking_loop_agent",
    "rag_pipeline",
]
