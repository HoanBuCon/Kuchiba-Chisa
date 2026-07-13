import asyncio
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.services.rag.base import RAGContext
from app.domain.interfaces.retriever import IMemoryRetriever, ILoreRetriever
from app.domain.interfaces.assessor import IContextAssessor
from app.domain.interfaces.thinking_agent import IThinkingAgent
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

log = get_logger(__name__)

class RAGPipeline:
    """
    Coordinates the entire RAG pipeline E2E including memory/lore retrieval,
    alignment assessment, and loop thinking/self-correction.
    """
    def __init__(
        self,
        memory_retriever: Optional[IMemoryRetriever] = None,
        lore_retriever: Optional[ILoreRetriever] = None,
        assessor: Optional[IContextAssessor] = None,
        thinking_loop_agent: Optional[IThinkingAgent] = None
    ):
        if memory_retriever is None:
            from app.domain.services.rag.retriever_memory import MemoryRetriever
            self.memory_retriever = MemoryRetriever()
        else:
            self.memory_retriever = memory_retriever
            
        if lore_retriever is None:
            from app.domain.services.rag.retriever_lore import LoreRetriever
            self.lore_retriever = LoreRetriever()
        else:
            self.lore_retriever = lore_retriever
            
        if assessor is None:
            from app.domain.services.rag.assessor import ContextAssessor
            self.assessor = ContextAssessor()
        else:
            self.assessor = assessor
            
        if thinking_loop_agent is None:
            from app.domain.services.rag.thinking_loop import ThinkingLoopAgent
            self.thinking_loop_agent = ThinkingLoopAgent()
        else:
            self.thinking_loop_agent = thinking_loop_agent

    @staticmethod
    def _normalize_intents(intents: List[Any]) -> Set[str]:
        """Normalize intent values to uppercase strings for stable routing checks."""
        normalized: Set[str] = set()
        for intent in intents:
            if isinstance(intent, Enum):
                normalized.add(str(intent.value).upper())
            else:
                normalized.add(str(intent).upper())
        return normalized

    async def retrieve_and_align(
        self,
        session: AsyncSession,
        user_id: str,
        user_message: str,
        query_vector: Optional[List[float]],
        cleaned_query: str,
        intents: List[Any],
        current_emotions: Dict[str, float],
        history: List[Dict[str, str]],
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        web_search_tool: Any,
        vector_store: Any,
        is_small_talk: bool = False,
        conversation_summary: str = None,
    ) -> RAGContext:
        """
        Runs E2E RAG Pipeline: Retrieves memory & lore, checks alignment, and runs thinking loop if necessary.
        """
        lore_chunks: List[str] = []
        memories: List[str] = []
        intent_strs = self._normalize_intents(intents)
        should_retrieve = bool(intent_strs - {"OTHER", "SYSTEM_ACTION"})
        
        # 1. Standard retrieval from Qdrant (parallelized)
        if query_vector and not is_small_talk and should_retrieve:
            retrieval_tasks = []
            active_intents = []

            if "CHARACTER_LORE" in intent_strs:
                active_intents.append("CHARACTER_LORE")
                retrieval_tasks.append(
                    self.lore_retriever.retrieve_lore_parent_child(
                        vector_store=vector_store,
                        collection="character_lore",
                        query_vector=query_vector,
                        query_text=cleaned_query,
                        top_k=5,
                        score_threshold=0.35
                    )
                )
            if "WORLD_LORE" in intent_strs:
                active_intents.append("WORLD_LORE")
                retrieval_tasks.append(
                    self.lore_retriever.retrieve_lore_parent_child(
                        vector_store=vector_store,
                        collection="world_lore",
                        query_vector=query_vector,
                        query_text=cleaned_query,
                        top_k=5,
                        score_threshold=0.35
                    )
                )
            if "STORY_LORE" in intent_strs:
                active_intents.append("STORY_LORE")
                retrieval_tasks.append(
                    self.lore_retriever.retrieve_lore_parent_child(
                        vector_store=vector_store,
                        collection="story_lore",
                        query_vector=query_vector,
                        query_text=cleaned_query,
                        top_k=5,
                        score_threshold=0.35
                    )
                )
            if "MEMORY" in intent_strs:
                active_intents.append("MEMORY")
                retrieval_tasks.append(
                    self.memory_retriever.retrieve_memories(
                        vector_store=vector_store,
                        collection="memories",
                        query_vector=query_vector,
                        user_id=user_id,
                        current_emotion=current_emotions,
                        limit=10,
                        top_k=5
                    )
                )

            if retrieval_tasks:
                try:
                    results = await asyncio.gather(*retrieval_tasks)
                    for intent_type, retrieved_data in zip(active_intents, results):
                        if intent_type == "MEMORY":
                            # Deduplicate memories by content
                            for m in retrieved_data:
                                if m.text_content and m.text_content not in memories:
                                    memories.append(m.text_content)
                        else:
                            # Deduplicate lore parent chunks across collections
                            for chunk in retrieved_data:
                                if chunk not in lore_chunks:
                                    lore_chunks.append(chunk)
                except Exception as ex:
                    log.error("Failed to retrieve data from Qdrant vector database", error=str(ex))

        # 1.1 Track retrieval step in real-time
        pipeline_tracker.add_step("rag_retrieval", {
            "lore_collections_queried": [
                col for col, b in {
                    "character_lore": "CHARACTER_LORE" in intent_strs,
                    "world_lore": "WORLD_LORE" in intent_strs,
                    "story_lore": "STORY_LORE" in intent_strs
                }.items() if b
            ],
            "retrieved_lore_chunks": lore_chunks,
            "retrieved_memories": memories
        })

        # 2. Assemble retrieved context pieces
        context_pieces = []
        if lore_chunks:
            context_pieces.append("[Retrieved Lore Chunks]:\n" + "\n".join(lore_chunks))
        if memories:
            context_pieces.append("[Retrieved Memories]:\n" + "\n".join(memories))
        
        retrieved_context_str = "\n\n".join(context_pieces) if context_pieces else "(No context retrieved)"

        # 3. Assess context alignment
        is_aligned = True
        alignment_reason = "Small talk or system bypass"
        search_query = ""
        use_lore = True
        if not is_small_talk and query_vector:
            is_aligned, alignment_reason, search_query, use_lore = await self.assessor.assess_alignment(
                user_message=user_message,
                context_text=retrieved_context_str,
                llm=llm,
                history=history,
                conversation_summary=conversation_summary,
            )
            
            # Log assessment result in trace
            history_mode = "summary" if (conversation_summary and conversation_summary.strip()) else "raw"
            pipeline_tracker.add_step(
                name="information_alignment_check",
                data={
                    "is_aligned": is_aligned,
                    "reason": alignment_reason,
                    "triggers_loop_thinking": not is_aligned,
                    "use_lore": use_lore,
                    "lore_count": len(lore_chunks),
                    "memory_count": len(memories),
                    "has_rag_context": len(lore_chunks) > 0 or len(memories) > 0,
                    "generated_search_query": search_query,
                    "history_mode": history_mode,
                    "history": conversation_summary.strip() if history_mode == "summary" else "(raw - last 4 msgs)",
                    "latest_query": user_message,
                    "retrieved_context": retrieved_context_str
                }
            )

        # 4. Thinking Loop (Web Search Iteration) if context is not aligned
        tool_output_msg = ""
        thinking_steps = []
        if not is_aligned:
            retrieved_context_str, thinking_steps = await self.thinking_loop_agent.run(
                session=session,
                user_id=user_id,
                user_message=user_message,
                history=history,
                initial_context=retrieved_context_str,
                llm=llm,
                embedder=embedder,
                web_search_tool=web_search_tool,
                initial_search_query=search_query
            )
            did_search = any(step.get("search_query") for step in thinking_steps)
            if did_search or retrieved_context_str.strip() not in ("", "(No context retrieved)"):
                tool_output_msg = retrieved_context_str

        return RAGContext(
            lore_chunks=lore_chunks if use_lore else [],
            memories=memories,
            tool_output_msg=tool_output_msg,
            is_aligned=is_aligned,
            alignment_reason=alignment_reason,
            thinking_steps=thinking_steps
        )
