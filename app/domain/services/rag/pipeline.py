import asyncio
from enum import Enum
from typing import Any

from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.interfaces.session import IDbSession
from app.domain.interfaces.tracker import IPipelineTracker
from app.domain.services.rag.assessor import ContextAssessor
from app.domain.services.rag.base import RAGContext
from app.domain.services.rag.entity_resolver import EntityResolver
from app.domain.services.rag.retriever_guild_memory import GuildMemoryRetriever
from app.domain.services.rag.retriever_image_memory import ImageMemoryRetriever
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.domain.services.rag.retriever_memory import MemoryRetriever
from app.domain.services.rag.thinking_loop import ThinkingLoopAgent
from app.domain.tuning.rag import RAGTuning
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class RAGPipeline:
    """
    Coordinates the entire RAG pipeline E2E including memory/lore retrieval,
    alignment assessment, and loop thinking/self-correction.
    """
    def __init__(
        self,
        memory_retriever: MemoryRetriever | None = None,
        lore_retriever: LoreRetriever | None = None,
        guild_memory_retriever: GuildMemoryRetriever | None = None,
        image_memory_retriever: ImageMemoryRetriever | None = None,
        assessor: ContextAssessor | None = None,
        thinking_loop_agent: ThinkingLoopAgent | None = None,
        pipeline_tracker: IPipelineTracker | None = None,
        entity_resolver: EntityResolver | None = None
    ):
        if memory_retriever is None:
            raise ValueError("memory_retriever is required")
        else:
            self.memory_retriever = memory_retriever
            
        if lore_retriever is None:
            raise ValueError("lore_retriever is required")
        else:
            self.lore_retriever = lore_retriever
            
        self.guild_memory_retriever = guild_memory_retriever
        self.image_memory_retriever = image_memory_retriever
            
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
    def _normalize_intents(intents: list[Any]) -> set[str]:
        """Normalize intent values to uppercase strings for stable routing checks."""
        normalized: set[str] = set()
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
        query_vector: list[float] | None,
        cleaned_query: str,
        intents: list[Any],
        current_emotions: dict[str, float],
        history: list[dict[str, str]],
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        web_search_tool: Any,
        is_small_talk: bool = False,
        conversation_summary: str | None = None,
        conversation_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        needs_vector_search: bool = True,
        needs_web_search: bool = False,
    ) -> RAGContext:
        """
        Runs E2E RAG Pipeline: Retrieves memory & lore, checks alignment, and runs thinking loop if necessary.
        """
        lore_scored = []
        memories = []
        guild_memories = []
        retrieved_images = []
        lore_chunks = []
        queried_lore_cols = []
        intent_strs = self._normalize_intents(intents)
        has_knowledge_intent = ("LORE" in intent_strs or "MEMORY" in intent_strs or "OTHER" in intent_strs or "KNOWLEDGE_OR_TASK" in intent_strs or "RETRIEVE_PAST_IMAGE" in intent_strs)
        
        is_hybrid_search_mode = bool(needs_web_search and needs_vector_search and not is_small_talk)
        is_web_search_mode = bool(needs_web_search and not needs_vector_search and not is_small_talk)
        is_vector_search_mode = bool(
            not is_small_talk 
            and "SMALL_TALK" not in intent_strs 
            and has_knowledge_intent 
            and (needs_vector_search is not False)
            and not is_web_search_mode
            and not is_hybrid_search_mode
        )

        lore_collections = ["character_lore", "world_lore", "story_lore"]
        extracted = set()
        expanded = set()
        scoring_details = []
        web_search_1_res = None
        search_msg = ""
        web_search_1_query = cleaned_query or user_message
        retrieved_context_str = "(No context retrieved)"

        # Helper coroutine: Execute Qdrant Vector Lore & Memory Retrieval
        async def _fetch_vector_lore_and_memory():
            nonlocal lore_scored, memories, guild_memories, retrieved_images, lore_chunks, queried_lore_cols, extracted, expanded, scoring_details
            if not query_vector:
                return

            retrieval_tasks = []
            active_intents = []
            should_fetch_lore = ("LORE" in intent_strs or "OTHER" in intent_strs or "KNOWLEDGE_OR_TASK" in intent_strs)

            if should_fetch_lore:
                if self.entity_resolver:
                    extracted = self.entity_resolver.extract_entities(cleaned_query)
                    expanded = self.entity_resolver.expand_entities(extracted)
                    log.info("Entity Resolver Output", extracted=list(extracted), expanded=list(expanded))

                for col_name in lore_collections:
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

            if "MEMORY" in intent_strs or "KNOWLEDGE_OR_TASK" in intent_strs or "OTHER" in intent_strs or "LORE" in intent_strs:
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

                if self.guild_memory_retriever and guild_id and not guild_id.startswith("CHANNEL_") and guild_id != "DM":
                    active_intents.append("GUILD_MEMORY")
                    retrieval_tasks.append(
                        self.guild_memory_retriever.retrieve_guild_memories(
                            collection="guild_memories",
                            query_vector=query_vector,
                            guild_id=str(guild_id),
                            channel_id=str(channel_id) if channel_id else None,
                            limit=10,
                            top_k=RAGTuning.TOP_K
                        )
                    )

            if "RETRIEVE_PAST_IMAGE" in intent_strs and self.image_memory_retriever and query_vector:
                active_intents.append("IMAGE_MEMORY")
                retrieval_tasks.append(
                    self.image_memory_retriever.retrieve_image_memories(
                        query_vector=query_vector,
                        user_id=user_id,
                        guild_id=guild_id,
                        is_community=bool(guild_id and not str(guild_id).startswith("CHANNEL_") and guild_id != "DM"),
                        limit=5,
                        score_threshold=0.68,
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

                    # Fair Multi-Collection Fusion (RRF + Normalized Score Fusion)
                    collection_buckets: dict[str, list[tuple[str, float, dict]]] = {}
                    for intent_type, col_name, retrieved_data in zip(
                        active_intents,
                        queried_lore_cols
                        + ["guild_memories"]
                        * (len(active_intents) - len(queried_lore_cols)),
                        results,
                        strict=False,
                    ):
                        if isinstance(retrieved_data, Exception):
                            log.warning("Retrieval sub-task failed", error=str(retrieved_data), collection=col_name)
                            continue
                        if intent_type == "MEMORY":
                            for m in retrieved_data:
                                if m.text_content and m.text_content not in memories:
                                    memories.append(m.text_content)
                        elif intent_type == "GUILD_MEMORY":
                            for m in retrieved_data:
                                if m.text_content and m.text_content not in guild_memories:
                                    guild_memories.append(m.text_content)
                        elif intent_type == "IMAGE_MEMORY":
                            for img_mem in retrieved_data:
                                if hasattr(img_mem, "model_dump"):
                                    retrieved_images.append(img_mem.model_dump())
                                elif isinstance(img_mem, dict):
                                    retrieved_images.append(img_mem)
                        else:
                            if col_name not in collection_buckets:
                                collection_buckets[col_name] = []
                            for item in retrieved_data:
                                if len(item) == 3:
                                    text, score, meta = item
                                else:
                                    text, score = item
                                    meta = {}
                                collection_buckets[col_name].append((text, score, meta))

                    # Apply RRF and Interleaving to prevent single-collection starvation
                    scored_by_text: dict[str, tuple[float, dict]] = {}
                    for items in collection_buckets.values():
                        for rank, (text, score, meta) in enumerate(items, start=1):
                            rrf_score = (1.0 / (60.0 + rank)) * 10.0 + score
                            if text not in scored_by_text:
                                scored_by_text[text] = (rrf_score, meta)
                            else:
                                existing_score, existing_meta = scored_by_text[text]
                                scored_by_text[text] = (existing_score + rrf_score, {**existing_meta, **meta})

                    lore_scored = [(t, s, m) for t, (s, m) in scored_by_text.items()]
                    lore_scored.sort(key=lambda x: x[1], reverse=True)
                    lore_chunks = [x[0] for x in lore_scored[:RAGTuning.TOP_K]]
                    if len(memories) > RAGTuning.TOP_K:
                        memories = memories[:RAGTuning.TOP_K]
                    if len(guild_memories) > RAGTuning.TOP_K:
                        guild_memories = guild_memories[:RAGTuning.TOP_K]
                except Exception as ex:
                    log.error("Failed to retrieve data from Qdrant vector database", error=str(ex))

            scoring_details = [x[2] for x in lore_scored[:RAGTuning.TOP_K] if len(x) > 2 and x[2]]

            # Emit sub-nodes 5.1.a, 5.1.c, 5.1.d, 5.1.e
            if lore_chunks:
                self.pipeline_tracker.add_step(
                    name="lore_retrieval",
                    stage_id="stage_5_rag",
                    depth=1,
                    category="retrieval",
                    title="5.1.a [VECTOR] Truy hồi Lore Qdrant (Parent-Child)",
                    subtitle=f"\"{cleaned_query[:24]}...\" ({len(lore_chunks)} chunks từ {len(queried_lore_cols)} collections)",
                    data={
                        "query": cleaned_query,
                        "source": "knowledge_retrieval_round_1",
                        "collections_queried": queried_lore_cols,
                        "chunks_count": len(lore_chunks),
                        "chunks": [
                            {"text": x[0], "score": round(x[1], 3), "metadata": x[2] if len(x) > 2 else {}}
                            for x in lore_scored[:RAGTuning.TOP_K]
                        ],
                        "extracted_entities": list(extracted),
                        "expanded_entities": list(expanded),
                    }
                )

            if memories:
                self.pipeline_tracker.add_step(
                    name="memory_retrieval",
                    stage_id="stage_5_rag",
                    depth=1,
                    category="retrieval",
                    title="5.1.c [MEMORY] Truy hồi Ký ức Dài hạn (Qdrant Memory)",
                    subtitle=f"Đã tìm thấy {len(memories)} ký ức liên quan",
                    data={
                        "source": "knowledge_retrieval_round_1",
                        "memories_count": len(memories),
                        "memories": memories,
                    }
                )

            if guild_memories:
                self.pipeline_tracker.add_step(
                    name="guild_memory_retrieval",
                    stage_id="stage_5_rag",
                    depth=1,
                    category="retrieval",
                    title="5.1.d [GUILD MEMORY] Truy hồi Tri thức Server (Qdrant Guild)",
                    subtitle=f"Đã tìm thấy {len(guild_memories)} tri thức / sự kiện chung của Server",
                    data={
                        "source": "knowledge_retrieval_round_1",
                        "guild_id": str(guild_id),
                        "guild_memories_count": len(guild_memories),
                        "guild_memories": guild_memories,
                    }
                )

            if retrieved_images:
                self.pipeline_tracker.add_step(
                    name="image_memory_retrieval",
                    stage_id="stage_5_rag",
                    depth=1,
                    category="retrieval",
                    title="5.1.e [IMAGE MEMORY] Truy hồi Ký Ức Hình Ảnh (Qdrant Image Memories)",
                    subtitle=f"Đã tìm thấy {len(retrieved_images)} ảnh phù hợp (Top Score: {retrieved_images[0].get('score', 0):.2f})",
                    data={
                        "source": "knowledge_retrieval_round_1",
                        "retrieved_images_count": len(retrieved_images),
                        "retrieved_images": retrieved_images,
                    }
                )

        # Helper coroutine: Execute Web Search & Deep Crawler
        async def _fetch_web_search_data():
            nonlocal web_search_1_res, search_msg
            if not web_search_tool:
                return

            log.info("Knowledge Retrieval executing Web Search (Round 1)", query=web_search_1_query)
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
                from app.domain.services.tools.web_search import web_search_trace_payload
                self.pipeline_tracker.add_step(
                    name="web_search",
                    stage_id="stage_5_rag",
                    depth=1,
                    category="retrieval",
                    title="5.1.b [SEARCH] DuckDuckGo Search & Deep Crawler",
                    subtitle=f"\"{web_search_1_query[:24]}...\" ({len(web_search_1_res.get('snippets', []))} snippets)",
                    data=web_search_trace_payload(
                        web_search_1_res,
                        source="knowledge_retrieval_round_1",
                        original_message=web_search_1_query,
                    ),
                )
            except Exception as ex:
                log.error("Failed to execute Web Search Round 1", error=str(ex))
                search_msg = "(No context retrieved from Web Search)"

        # ── EXECUTE STAGE 5 RETRIEVAL ACCORDING TO MODE ──
        if is_hybrid_search_mode:
            # Emit Stage 5 Root Step for Hybrid Mode
            self.pipeline_tracker.add_step(
                name="rag_retrieval",
                stage_id="stage_5_rag",
                depth=0,
                category="stage_root",
                title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng",
                subtitle="Hybrid Mode · Vector Lore (Qdrant) + DuckDuckGo Web Search",
                data={
                    "mode": "HYBRID_SEARCH",
                    "should_retrieve": True,
                    "search_query": web_search_1_query,
                    "intents": list(intent_strs),
                }
            )
            await asyncio.gather(_fetch_vector_lore_and_memory(), _fetch_web_search_data())

            context_pieces = []
            if lore_chunks:
                context_pieces.append("[Retrieved Lore Chunks]:\n" + "\n".join(lore_chunks))
            if memories:
                context_pieces.append("[Retrieved Memories]:\n" + "\n".join(memories))
            if web_search_1_res and search_msg:
                context_pieces.append(f"[Web Search Round 1 Results for '{web_search_1_query}']:\n{search_msg}")
            retrieved_context_str = "\n\n".join(context_pieces) if context_pieces else "(No context retrieved)"

        elif is_web_search_mode and web_search_tool:
            self.pipeline_tracker.add_step(
                name="rag_retrieval",
                stage_id="stage_5_rag",
                depth=0,
                category="stage_root",
                title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng",
                subtitle=f"Web Search Mode · \"{web_search_1_query[:25]}...\"",
                data={
                    "mode": "WEB_SEARCH",
                    "should_retrieve": True,
                    "search_query": web_search_1_query,
                    "intents": list(intent_strs),
                }
            )
            await _fetch_web_search_data()
            retrieved_context_str = f"[Web Search Round 1 Results for '{web_search_1_query}']:\n{search_msg}" if search_msg else "(No context retrieved from Web Search)"

        elif is_vector_search_mode and query_vector:
            await _fetch_vector_lore_and_memory()
            self.pipeline_tracker.add_step(
                name="rag_retrieval",
                stage_id="stage_5_rag",
                depth=0,
                category="stage_root",
                title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng",
                subtitle=f"Vector Search · {len(lore_chunks)} lore · {len(memories)} mems · {len(guild_memories)} guild",
                data={
                    "mode": "VECTOR_SEARCH",
                    "should_retrieve": True,
                    "intents": list(intent_strs),
                    "lore_collections_queried": queried_lore_cols,
                    "extracted_entities": list(extracted),
                    "expanded_entities": list(expanded),
                    "retrieved_lore_chunks": lore_chunks,
                    "lore_scoring_details": scoring_details,
                    "retrieved_memories": memories,
                    "retrieved_guild_memories": guild_memories,
                    "guild_memories_count": len(guild_memories),
                    "weights": {
                        "vector": RAGTuning.WEIGHT_VECTOR,
                        "keyword": RAGTuning.WEIGHT_KEYWORD,
                        "metadata": RAGTuning.WEIGHT_METADATA
                    }
                }
            )
            context_pieces = []
            if lore_chunks:
                context_pieces.append("[Retrieved Lore Chunks]:\n" + "\n".join(lore_chunks))
            if memories:
                context_pieces.append("[Retrieved Memories]:\n" + "\n".join(memories))
            if guild_memories:
                context_pieces.append("[Retrieved Server Guild Memories]:\n" + "\n".join(guild_memories))
            retrieved_context_str = "\n\n".join(context_pieces) if context_pieces else "(No context retrieved)"

        else:
            skip_reason = "Code / Technical or Small Talk bypass (0ms RAG)"
            if is_small_talk:
                skip_reason = "Small Talk detected (L1 Intent bypass)"
            elif not has_knowledge_intent:
                skip_reason = f"Intent '{', '.join(intent_strs)}' does not require Lore or Web retrieval"

            self.pipeline_tracker.add_step(
                name="rag_retrieval",
                stage_id="stage_5_rag",
                depth=0,
                category="stage_root",
                title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng",
                subtitle=f"0ms RAG Bypass ({skip_reason})",
                data={
                    "mode": "BYPASS",
                    "should_retrieve": False,
                    "skip_reason": skip_reason,
                    "intents": list(intent_strs),
                }
            )

        # ── UNIVERSAL CONTEXT ASSESSOR (Đánh giá Đủ Context, Viết lại Query & Chắt lọc Dữ kiện) ──
        is_aligned = True
        alignment_reason = "Small talk or system bypass"
        search_query = ""
        search_target = "web"
        use_lore = True
        extracted_facts = ""

        if not is_small_talk and (is_hybrid_search_mode or is_vector_search_mode or is_web_search_mode):
            assess_res = await self.assessor.assess_alignment(
                user_message=cleaned_query or user_message,
                context_text=retrieved_context_str,
                llm=llm,
                history=history,
                conversation_summary=conversation_summary,
            )
            if len(assess_res) == 6:
                is_aligned, alignment_reason, search_query, use_lore, extracted_facts, search_target = assess_res
            elif len(assess_res) == 5:
                is_aligned, alignment_reason, search_query, use_lore, extracted_facts = assess_res
                search_target = "both" if is_hybrid_search_mode else ("vector" if is_vector_search_mode else "web")
            else:
                is_aligned, alignment_reason, search_query, use_lore = assess_res[:4]
                extracted_facts = ""
                search_target = "both" if is_hybrid_search_mode else ("vector" if is_vector_search_mode else "web")
        else:
            is_aligned = True
            alignment_reason = "Bypassed Context Assessor (Code snippet or Small Talk)"
            search_query = ""
            search_target = "web"
            use_lore = False
            extracted_facts = ""
            
        # Log assessment result in trace
        summary_text = conversation_summary or ""
        history_mode = "summary" if summary_text.strip() else "raw"
        if history_mode == "summary":
            history_display = summary_text.strip()
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
            stage_id="stage_5_rag",
            depth=1,
            category="decision",
            title="5.2 [LLM & DECISION] Context Assessor & Chắt lọc Dữ kiện",
            subtitle="✓ Đã đủ thông tin" if is_aligned else f"⚠️ Thiếu dữ liệu ➔ Query 2 ({search_target.upper()}): \"{search_query[:20]}...\"",
            data={
                "is_aligned": is_aligned,
                "reason": alignment_reason,
                "triggers_loop_thinking": not is_aligned,
                "use_lore": use_lore,
                "extracted_facts": extracted_facts,
                "search_target": search_target,
                "lore_count": len(lore_chunks),
                "memory_count": len(memories),
                "guild_memory_count": len(guild_memories),
                "has_rag_context": bool(lore_chunks or memories or guild_memories or web_search_1_res),
                "generated_search_query": search_query,
                "history_mode": history_mode,
                "history": history_display,
                "latest_query": user_message,
                "retrieved_context": retrieved_context_str
            }
        )


        # ── LOOP THINKING (Search Lần 2 nếu ContextAssessor phát hiện thiếu dữ liệu) ──
        tool_output_msg = ""
        thinking_steps: list[dict[str, Any]] = []
        if not is_aligned:
            # Use dynamically decided target from ContextAssessor if available
            initial_target = search_target or ("both" if is_hybrid_search_mode else ("vector" if is_vector_search_mode else "web"))

            retrieved_context_str, thinking_steps = await self.thinking_loop_agent.run(
                session=session,
                user_id=user_id,
                user_message=user_message,
                history=history,
                initial_context=retrieved_context_str,
                llm=llm,
                embedder=embedder,
                web_search_tool=web_search_tool,
                initial_search_query=search_query,  # <-- Refined Query do Assessor vừa viết lại!
                initial_extracted_facts=extracted_facts,
                lore_retriever=self.lore_retriever,
                initial_search_target=initial_target,
            )

            # ── BUILD TOOL OUTPUT MESSAGE (KẾT HỢP FACTUAL SUMMARY + DỮ LIỆU TÌM KIẾM MỚI TỪ LOOP) ──
            # 1. Thu thập tất cả distilled facts đã được chắt lọc qua các bước
            step_facts = [
                step.get("distilled_facts", "").strip()
                for step in thinking_steps
                if step.get("distilled_facts", "").strip()
            ]
            if extracted_facts and extracted_facts not in step_facts:
                step_facts.insert(0, extracted_facts)

            # 2. Thu thập kết quả tìm kiếm của chu kỳ CUỐI CÙNG (Trailing Search Cycle chưa được distill)
            latest_search_detail = None
            for step in reversed(thinking_steps):
                search_res = step.get("search_result", "").strip()
                search_q = step.get("search_query", "").strip()
                cycle_num = step.get("cycle", 1)
                target = step.get("search_target", "web").upper()
                
                # Tìm chu kỳ gần nhất có thực thi search thực tế và có kết quả hợp lệ
                if search_res and search_res not in ("No further search needed.", "No search results returned.") and search_q:
                    latest_search_detail = f"[Thinking Cycle {cycle_num} ({target}) Results for '{search_q}']:\n{search_res}"
                    break

            # 3. Lắp ráp tool_output_msg (Phương án A: Facts đã chắt lọc + Kết quả tìm kiếm mới nhất)
            output_parts = []
            if step_facts:
                merged_facts = "\n".join(step_facts)
                output_parts.append(f"[SEARCH DATA — FACTUAL SUMMARY]:\n{merged_facts}")

            if latest_search_detail:
                # Đính kèm kết quả mới nhất chưa qua distill từ lượt search cuối (5.3.2.1 hoặc 5.3.1.1)
                output_parts.append(f"[SEARCH DATA — LATEST RETRIEVED DETAILS]:\n{latest_search_detail}")
            elif not step_facts:
                # Fallback an toàn nếu không có step_facts và không có latest_search_detail
                search_delta = retrieved_context_str
                if is_vector_search_mode and lore_chunks and "[Retrieved Lore Chunks]:" in search_delta:
                    parts = search_delta.split("[Thinking Cycle", 1)
                    if len(parts) > 1:
                        search_delta = "[Thinking Cycle" + parts[1]
                output_parts.append(search_delta.strip())

            tool_output_msg = "\n\n".join(output_parts).strip()
        elif (is_web_search_mode or is_hybrid_search_mode) and web_search_1_res:
            # Distilled factual summary from Round 1 (Fast & clean token budget)
            if extracted_facts:
                tool_output_msg = f"[SEARCH DATA — FACTUAL SUMMARY]:\n{extracted_facts}"
            else:
                tool_output_msg = retrieved_context_str

        return RAGContext(
            lore_chunks=lore_chunks if use_lore else [],
            memories=memories,
            guild_memories=guild_memories,
            retrieved_images=retrieved_images,
            tool_output_msg=tool_output_msg,
            is_aligned=is_aligned,
            alignment_reason=alignment_reason,
            thinking_steps=thinking_steps
        )
