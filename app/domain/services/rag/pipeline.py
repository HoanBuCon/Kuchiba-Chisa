import asyncio
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from app.domain.tuning.rag import RAGTuning
from app.domain.interfaces.session import IDbSession
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.services.rag.base import RAGContext
from app.domain.services.rag.retriever_memory import MemoryRetriever
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.domain.services.rag.assessor import ContextAssessor
from app.domain.services.rag.thinking_loop import ThinkingLoopAgent
from app.domain.services.rag.entity_resolver import EntityResolver
from app.shared.utils.logger import get_logger
from app.domain.interfaces.tracker import IPipelineTracker

log = get_logger(__name__)

class RAGPipeline:
    """
    Coordinates the entire RAG pipeline E2E including memory/lore retrieval,
    alignment assessment, and loop thinking/self-correction.
    """
    def __init__(
        self,
        memory_retriever: Optional[MemoryRetriever] = None,
        lore_retriever: Optional[LoreRetriever] = None,
        assessor: Optional[ContextAssessor] = None,
        thinking_loop_agent: Optional[ThinkingLoopAgent] = None,
        pipeline_tracker: Optional[IPipelineTracker] = None,
        entity_resolver: Optional[EntityResolver] = None
    ):
        if memory_retriever is None:
            raise ValueError("memory_retriever is required")
        else:
            self.memory_retriever = memory_retriever
            
        if lore_retriever is None:
            raise ValueError("lore_retriever is required")
        else:
            self.lore_retriever = lore_retriever
            
        if assessor is None:
            self.assessor = ContextAssessor()
        else:
            self.assessor = assessor
            
        if thinking_loop_agent is None:
            raise ValueError("thinking_loop_agent is required")
        else:
            self.thinking_loop_agent = thinking_loop_agent
            
        if pipeline_tracker is None:
            raise ValueError("pipeline_tracker is required")
        else:
            self.pipeline_tracker = pipeline_tracker
            
        self.entity_resolver = entity_resolver

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
        session: IDbSession,
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
        is_small_talk: bool = False,
        conversation_summary: str = None,
        conversation_id: Optional[str] = None,
        needs_vector_search: bool = True,
        needs_web_search: bool = False,
    ) -> RAGContext:
        """
        Runs E2E RAG Pipeline: Retrieves memory & lore, checks alignment, and runs thinking loop if necessary.
        """
        lore_scored = []
        memories = []
        lore_chunks = []
        queried_lore_cols = []
        intent_strs = self._normalize_intents(intents)
        has_knowledge_intent = ("LORE" in intent_strs or "MEMORY" in intent_strs or "OTHER" in intent_strs or "KNOWLEDGE_OR_TASK" in intent_strs)
        
        is_web_search_mode = bool(needs_web_search and not needs_vector_search and not is_small_talk)
        is_vector_search_mode = bool(
            not is_small_talk 
            and "SMALL_TALK" not in intent_strs 
            and has_knowledge_intent 
            and (needs_vector_search is not False)
            and not is_web_search_mode
        )

        LORE_COLLECTIONS = ["character_lore", "world_lore", "story_lore"]
        extracted = set()
        expanded = set()
        scoring_details = []
        web_search_1_res = None
        retrieved_context_str = "(No context retrieved)"

        # ── OPTION 2: Web Search Mode (Search Lần 1 trực tiếp tại Knowledge Retrieval Stage) ──
        if is_web_search_mode and web_search_tool:
            web_search_1_query = cleaned_query or user_message
            log.info("Knowledge Retrieval executing Option 2 (Web Search Mode - Round 1)", query=web_search_1_query)
            try:
                web_search_1_res = await web_search_tool.execute(
                    session=session,
                    user_id=user_id,
                    user_message=web_search_1_query,
                    llm=llm,
                    embedder=embedder,
                    history=history,
                    bypass_optimize=True
                )
                search_msg = web_search_1_res.get("message", "")
                snippets = web_search_1_res.get("snippets") or []
                
                # Log step: Knowledge Retrieval (Web Search Mode)
                self.pipeline_tracker.add_step("rag_retrieval", {
                    "mode": "WEB_SEARCH",
                    "should_retrieve": True,
                    "search_query": web_search_1_query,
                    "snippets_count": len(snippets),
                    "search_result": search_msg,
                    "intents": intent_strs,
                })
                
                # Log child step: Web Search Round 1 trace
                from app.domain.services.tools.web_search import web_search_trace_payload
                self.pipeline_tracker.add_step(
                    "web_search",
                    web_search_trace_payload(
                        web_search_1_res,
                        source="knowledge_retrieval_round_1",
                        original_message=web_search_1_query,
                    ),
                )
                
                retrieved_context_str = f"[Web Search Round 1 Results for '{web_search_1_query}']:\n{search_msg}"
            except Exception as ex:
                log.error("Failed to execute Web Search Round 1", error=str(ex))
                retrieved_context_str = "(No context retrieved from Web Search)"

        # ── OPTION 1: Vector Search Mode (Qdrant Vector Retrieval for Lore & Memory) ──
        elif is_vector_search_mode and query_vector:
            retrieval_tasks = []
            active_intents = []

            # Perform lore retrieval if explicit LORE intent or fallback for OTHER / KNOWLEDGE
            should_fetch_lore = ("LORE" in intent_strs or "OTHER" in intent_strs or "KNOWLEDGE_OR_TASK" in intent_strs)

            if should_fetch_lore:
                if self.entity_resolver:
                    extracted = self.entity_resolver.extract_entities(cleaned_query)
                    expanded = self.entity_resolver.expand_entities(extracted)
                    log.info("Entity Resolver Output", extracted=list(extracted), expanded=list(expanded))

                for col_name in LORE_COLLECTIONS:
                    active_intents.append("LORE")
                    queried_lore_cols.append(col_name)
                    retrieval_tasks.append(
                        self.lore_retriever.retrieve_lore_parent_child(
                            collection=col_name,
                            query_vector=query_vector,
                            session=session,
                            query_text=cleaned_query,
                            top_k=RAGTuning.TOP_K,
                            score_threshold=RAGTuning.SCORE_THRESHOLD,
                            entities_filter=list(expanded) if expanded else None
                        )
                    )

            if "MEMORY" in intent_strs:
                active_intents.append("MEMORY")
                retrieval_tasks.append(
                    self.memory_retriever.retrieve_memories(
                        collection="memories",
                        query_vector=query_vector,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        current_emotion=current_emotions,
                        limit=10,
                        top_k=RAGTuning.TOP_K
                    )
                )

            if retrieval_tasks:
                try:
                    results = []
                    for task in retrieval_tasks:
                        try:
                            res = await task
                        except Exception as e:
                            res = e
                        results.append(res)

                    for intent_type, retrieved_data in zip(active_intents, results):
                        if isinstance(retrieved_data, Exception):
                            log.warning("Retrieval sub-task failed", error=str(retrieved_data))
                            continue
                        if intent_type == "MEMORY":
                            # Deduplicate memories by content
                            for m in retrieved_data:
                                if m.text_content and m.text_content not in memories:
                                    memories.append(m.text_content)
                        else:
                            # Deduplicate and track scores across lore collections
                            for item in retrieved_data:
                                if len(item) == 3:
                                    text, score, meta = item
                                else:
                                    text, score = item
                                    meta = {}
                                if not any(c[0] == text for c in lore_scored):
                                    lore_scored.append((text, score, meta))
                    
                    # Subject-Entity Alignment Reranking:
                    if extracted:
                        adjusted_scored = []
                        for text, score, meta in lore_scored:
                            boost = 0.0
                            text_lower = text.lower()
                            chunk_ents = [e.lower() for e in meta.get("entities", [])] if isinstance(meta, dict) else []
                            for ent in extracted:
                                ent_lower = ent.lower()
                                if ent_lower in text_lower or any(ent_lower in ce for ce in chunk_ents):
                                    boost = 0.15
                                    break
                            adjusted_scored.append((text, score + boost, meta))
                        lore_scored = adjusted_scored

                    # Sort globally by score and enforce global TOP_K limit
                    lore_scored.sort(key=lambda x: x[1], reverse=True)
                    lore_chunks = [x[0] for x in lore_scored[:RAGTuning.TOP_K]]
                    if len(memories) > RAGTuning.TOP_K:
                        memories = memories[:RAGTuning.TOP_K]

                except Exception as ex:
                    log.error("Failed to retrieve data from Qdrant vector database", error=str(ex))

            scoring_details = [x[2] for x in lore_scored[:RAGTuning.TOP_K] if len(x) > 2 and x[2]]

            self.pipeline_tracker.add_step("rag_retrieval", {
                "mode": "VECTOR_SEARCH",
                "should_retrieve": True,
                "intents": intent_strs,
                "lore_collections_queried": queried_lore_cols,
                "extracted_entities": list(extracted),
                "expanded_entities": list(expanded),
                "retrieved_lore_chunks": lore_chunks,
                "lore_scoring_details": scoring_details,
                "retrieved_memories": memories,
                "weights": {
                    "vector": RAGTuning.WEIGHT_VECTOR,
                    "keyword": RAGTuning.WEIGHT_KEYWORD,
                    "metadata": RAGTuning.WEIGHT_METADATA
                }
            })

            context_pieces = []
            if lore_chunks:
                context_pieces.append("[Retrieved Lore Chunks]:\n" + "\n".join(lore_chunks))
            if memories:
                context_pieces.append("[Retrieved Memories]:\n" + "\n".join(memories))
            retrieved_context_str = "\n\n".join(context_pieces) if context_pieces else "(No context retrieved)"

        else:
            skip_reason = "Code / Technical or Small Talk bypass (0ms RAG)"
            if is_small_talk:
                skip_reason = "Small Talk detected (L1 Intent bypass)"
            elif not has_knowledge_intent:
                skip_reason = f"Intent '{', '.join(intent_strs)}' does not require Lore or Web retrieval"

            self.pipeline_tracker.add_step("rag_retrieval", {
                "mode": "BYPASS",
                "should_retrieve": False,
                "skip_reason": skip_reason,
                "intents": intent_strs,
            })

        # ── UNIVERSAL CONTEXT ASSESSOR (Đánh giá Đủ Context & Viết lại Query Lần 2) ──
        is_aligned = True
        alignment_reason = "Small talk or system bypass"
        search_query = ""
        use_lore = True

        if not is_small_talk and (is_vector_search_mode or is_web_search_mode):
            is_aligned, alignment_reason, search_query, use_lore = await self.assessor.assess_alignment(
                user_message=cleaned_query or user_message,
                context_text=retrieved_context_str,
                llm=llm,
                history=history,
                conversation_summary=conversation_summary,
            )
        else:
            is_aligned = True
            alignment_reason = "Bypassed Context Assessor (Code snippet or Small Talk)"
            search_query = ""
            use_lore = False
            
        # Log assessment result in trace
        history_mode = "summary" if (conversation_summary and conversation_summary.strip()) else "raw"
        if history_mode == "summary":
            history_display = conversation_summary.strip()
        elif history and len(history) > 0:
            history_lines = []
            for m in history[-4:]:
                r = m.get("role", "user").upper()
                c = m.get("content", "")
                history_lines.append(f"{r}: {c}")
            history_display = "\n".join(history_lines)
        else:
            history_display = "(Không có lịch sử trò chuyện)"

        self.pipeline_tracker.add_step(
            name="information_alignment_check",
            data={
                "is_aligned": is_aligned,
                "reason": alignment_reason,
                "triggers_loop_thinking": not is_aligned,
                "use_lore": use_lore,
                "lore_count": len(lore_chunks),
                "memory_count": len(memories),
                "has_rag_context": bool(lore_chunks or memories or web_search_1_res),
                "generated_search_query": search_query,
                "history_mode": history_mode,
                "history": history_display,
                "latest_query": user_message,
                "retrieved_context": retrieved_context_str
            }
        )

        # ── LOOP THINKING (Search Lần 2 nếu ContextAssessor phát hiện thiếu dữ liệu) ──
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
                initial_search_query=search_query  # <-- Refined Query do Assessor vừa viết lại!
            )
            search_parts = []
            for step in thinking_steps:
                if step.get("search_query") and step.get("search_result") and step["search_result"] != "No further search needed.":
                    search_parts.append(f"[Thinking Cycle {step['cycle']} Search Results for '{step['search_query']}']:\n{step['search_result']}")
            if search_parts:
                tool_output_msg = "\n\n".join(search_parts)

        return RAGContext(
            lore_chunks=lore_chunks if use_lore else [],
            memories=memories,
            tool_output_msg=tool_output_msg,
            is_aligned=is_aligned,
            alignment_reason=alignment_reason,
            thinking_steps=thinking_steps
        )
