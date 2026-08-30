import uuid
import time
from typing import Any, Optional
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.entities.memory import MemoryPayload, GuildMemoryPayload
from app.domain.interfaces.vector_store import IVectorStore
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class MemoryExtractor:
    """
    Background worker that extracts long-term facts/preferences from user messages and stores them.
    Supports both Individual memories (memories collection) and Guild memories (guild_memories collection).
    """
    def __init__(self, llm: BaseLLMAdapter, embedder: IEmbeddingProvider, vector_store: IVectorStore):
        self.llm = llm
        self.embedder = embedder
        self.vector_store = vector_store
        self.RESPONSE_SCHEMA = {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["user_fact", "shared_story", "guild_event", "guild_culture", "none"]
                },
                "content": {"type": "string"},
                "importance_score": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 1.0
                }
            },
            "required": ["type"]
        }
        self.BATCH_RESPONSE_SCHEMA = {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["user_fact", "shared_story", "guild_event", "guild_culture"]
                            },
                            "content": {"type": "string"},
                            "importance_score": {
                                "type": "number",
                                "minimum": 0.1,
                                "maximum": 1.0
                            },
                            "expires_at": {
                                "type": "integer",
                                "description": "Optional epoch timestamp when this event ends/expires (if applicable)"
                            }
                        },
                        "required": ["type", "content"]
                    }
                }
            },
            "required": ["facts"]
        }

    async def reconcile_memory_conflicts_batch(
        self,
        items: list[dict[str, Any]],
    ) -> dict[int, tuple[str, Optional[str]]]:
        """
        Batched reconciliation: Evaluates logical relationships between MULTIPLE new facts
        and their candidate existing memories in a single LLM call.
        
        Uses Candidate Index Mapping ([cand_0], [cand_1], ...) to prevent UUID hallucinations.
        
        Input: items = [
            {"index": int, "content": str, "candidates": list[dict]},
            ...
        ]
        
        Returns: {
            index: (action, conflicting_id)  # action: 'CONTRADICT' | 'DUPLICATE' | 'KEEP_BOTH'
        }
        """
        if not items:
            return {}

        formatted_blocks = []
        item_candidates_map: dict[int, list[dict[str, Any]]] = {}

        for item in items:
            idx = item.get("index", 0)
            content = item.get("content", "")
            candidates = item.get("candidates", [])
            item_candidates_map[idx] = candidates
            
            candidates_formatted = []
            for c_idx, c in enumerate(candidates):
                c_text = c.get("payload", {}).get("text_content") or c.get("text_content") or ""
                candidates_formatted.append(f"    - [cand_{c_idx}] \"{c_text}\"")
            candidates_str = "\n".join(candidates_formatted) if candidates_formatted else "    (No candidate memories)"
            
            formatted_blocks.append(
                f"[Fact Item #{idx}]\n"
                f"  NEW FACT: \"{content}\"\n"
                f"  EXISTING CANDIDATES:\n{candidates_str}"
            )

        items_str = "\n\n".join(formatted_blocks)

        schema = {
            "type": "object",
            "properties": {
                "reconciliations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "action": {
                                "type": "string",
                                "enum": ["CONTRADICT", "DUPLICATE", "KEEP_BOTH"]
                            },
                            "conflicting_candidate_index": {
                                "type": ["integer", "null"],
                                "description": "Integer index of the candidate (e.g. 0 for [cand_0], 1 for [cand_1]) if action is CONTRADICT, otherwise null"
                            },
                            "reasoning": {"type": "string"}
                        },
                        "required": ["index", "action"]
                    }
                }
            },
            "required": ["reconciliations"]
        }

        system_prompt = (
            "You are a Memory Reconciliation AI.\n"
            "Your job is to compare MULTIPLE NEW extracted facts about the user against their respective EXISTING candidate memories.\n\n"
            "For EACH fact item (identified by its 'index'):\n"
            "Determine the logical relationship:\n"
            "1. 'CONTRADICT': The NEW fact directly contradicts, updates, or supersedes an existing memory "
            "(e.g. user changed preference, job, location, opinion, or status). Set 'conflicting_candidate_index' to the candidate's index number (e.g. 0 for [cand_0], 1 for [cand_1]) to delete.\n"
            "2. 'DUPLICATE': The NEW fact is exact same or semantically identical to an existing memory. Set 'conflicting_candidate_index' to null. No need to store again.\n"
            "3. 'KEEP_BOTH': Both facts are true, distinct, and complementary (they do NOT contradict each other). Set 'conflicting_candidate_index' to null.\n\n"
            "Output JSON format:\n"
            "{\"reconciliations\": [{\"index\": 0, \"action\": \"CONTRADICT\" | \"DUPLICATE\" | \"KEEP_BOTH\", \"conflicting_candidate_index\": 0 | null, \"reasoning\": \"...\"}]}"
        )

        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=f"FACT ITEMS TO RECONCILE:\n\n{items_str}",
            response_schema=schema,
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={"use_deep_thinking": False}
        )

        results: dict[int, tuple[str, Optional[str]]] = {}
        try:
            from app.domain.context import llm_call_purpose
            llm_call_purpose.set("memory_reconciliation")
            response = await self.llm.generate(prompt)
            parsed = response.parsed or {}
            reconciliations = parsed.get("reconciliations", [])
            
            for r in reconciliations:
                if not isinstance(r, dict):
                    continue
                r_idx = r.get("index")
                action = str(r.get("action", "KEEP_BOTH")).upper()
                if action not in ["CONTRADICT", "DUPLICATE", "KEEP_BOTH"]:
                    action = "KEEP_BOTH"
                
                conflicting_id = None
                if action == "CONTRADICT" and r_idx is not None and r_idx in item_candidates_map:
                    cand_idx = r.get("conflicting_candidate_index")
                    candidates_list = item_candidates_map[r_idx]
                    if isinstance(cand_idx, int) and 0 <= cand_idx < len(candidates_list):
                        conflicting_id = candidates_list[cand_idx].get("id")
                    elif isinstance(r.get("conflicting_id"), str):
                        conflicting_id = r.get("conflicting_id")

                if r_idx is not None:
                    results[int(r_idx)] = (action, conflicting_id)
        except Exception as e:
            log.warning("Batched memory conflict reconciliation LLM call failed, falling back to safe KEEP_BOTH", error=str(e))

        # Fill any missing items with safe fallback KEEP_BOTH
        for item in items:
            idx = item.get("index", 0)
            if idx not in results:
                results[idx] = ("KEEP_BOTH", None)

        return results

    async def reconcile_memory_conflict(
        self,
        new_fact: str,
        candidates: list[dict[str, Any]],
    ) -> tuple[str, Optional[str]]:
        """
        Legacy single-fact reconciliation wrapper.
        """
        if not candidates:
            return "KEEP_BOTH", None
        results = await self.reconcile_memory_conflicts_batch([
            {"index": 0, "content": new_fact, "candidates": candidates}
        ])
        return results.get(0, ("KEEP_BOTH", None))

    def build_batch_transcript(
        self,
        history: list[dict[str, str]],
        current_user_message: str,
        current_assistant_reply: str
    ) -> str:
        """
        Builds a rich transcript covering:
        - 3 most recent conversation pairs (Senpai <-> Chisa)
        - Up to 2 preceding user questions before the 3-pair window for supplementary context
        """
        all_turns = []
        if history:
            all_turns.extend(history)
        all_turns.append({"role": "user", "content": current_user_message})
        all_turns.append({"role": "assistant", "content": current_assistant_reply})
        
        # Group into (user, assistant) pairs
        pairs = []
        i = 0
        while i < len(all_turns):
            if all_turns[i].get("role") == "user":
                user_msg = all_turns[i].get("content", "")
                asst_msg = ""
                if i + 1 < len(all_turns) and all_turns[i+1].get("role") == "assistant":
                    asst_msg = all_turns[i+1].get("content", "")
                    i += 2
                else:
                    i += 1
                pairs.append((user_msg, asst_msg))
            else:
                i += 1
                
        recent_3_pairs = pairs[-3:] if len(pairs) >= 3 else pairs
        earlier_pairs = pairs[:-3] if len(pairs) > 3 else []
        earlier_user_msgs = [p[0] for p in earlier_pairs[-2:] if p[0]]
        
        lines = []
        if earlier_user_msgs:
            lines.append("[BỐI CẢNH CÂU HỎI TRƯỚC ĐÓ CỦA SENPAI]:")
            for u in earlier_user_msgs:
                lines.append(f"- Senpai: \"{u}\"")
            lines.append("")
            
        lines.append("[3 CẶP HỘI THOẠI GẦN NHẤT CẦN TỔNG HỢP VÀ TRÍCH XUẤT]:")
        for idx, (u, a) in enumerate(recent_3_pairs, 1):
            lines.append(f"Cặp {idx}:")
            lines.append(f"  Senpai: \"{u}\"")
            if a:
                lines.append(f"  Chisa : \"{a}\"")
                
        return "\n".join(lines)

    async def extract_and_store_batch(
        self,
        user_id: str,
        conversation_id: str,
        history: list[dict[str, str]],
        current_user_message: str,
        current_assistant_reply: str,
        guild_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        speaker_name: Optional[str] = None,
        is_community: bool = False,
    ) -> None:
        """
        Batched background worker: Analyzes conversation window to extract multi-fact milestones,
        personal preferences, server-shared events, or guild culture, and stores them in Qdrant.
        """
        has_guild = bool(guild_id and not guild_id.startswith("CHANNEL_") and guild_id != "DM")
        
        system_prompt = (
            "You are a Precision Long-Term Memory Extractor for an AI Companion application (Kuchiba Chisa).\n"
            "Your mission is to extract persistent, meaningful facts from the conversation snippet.\n\n"
            "ALLOWED MEMORY TYPES:\n"
            "1. 'user_fact' (Personal information about the speaker):\n"
            "   - Real-world life: Job, career, studies, exams, city/location, family, pets, health.\n"
            "   - Personal tastes & habits: Favorite foods, drinks, music, games, hobbies, recurring routines.\n"
            "2. 'shared_story' (Milestones & Agreements between Speaker and Chisa):\n"
            "   - Custom nicknames assigned between Chisa and the speaker (NOT default 'Senpai - em').\n"
            "   - Actionable mutual promises and commitments for future events.\n"
            + (
                "3. 'guild_event' (Server-wide Schedules, Tournaments, Meetups, Gaming Sessions):\n"
                "   - Concrete events or schedules planned for members in this server (e.g. 'Tối thứ 7 lúc 20h server tổ chức giải Valorant').\n"
                "   - Optionally provide 'expires_at' (epoch timestamp) if a clear date/time is mentioned.\n"
                "4. 'guild_culture' (Server Inside Jokes, Member Nicknames, Server Customs):\n"
                "   - Inside jokes, group traditions, member reputations, or channel rules acknowledged by the group.\n\n"
                if has_guild else "\n"
            )
            + "STRICT REJECTION RULES (RETURN {\"facts\": []}):\n"
            "- ROLEPLAY JOKES & BANTER: Ignore fleeting teases or superficial sarcasm.\n"
            "- DEFAULT PERSONA TRAITS: DO NOT extract built-in persona habits ('Chisa xưng em', 'Chisa là AI companion').\n"
            "- SOCIAL PLEASANTRIES: DO NOT extract simple greetings or fleeting moods ('hôm nay đói bụng').\n\n"
            "FEW-SHOT EXAMPLES:\n"
            "Example 1 (User Fact):\n"
            "  Senpai: 'anh sắp apply Viettel Software rồi' | Chisa: 'Oa xịn quá! Chúc Senpai may mắn nha~'\n"
            "  -> Output: {\"facts\": [{\"type\": \"user_fact\", \"content\": \"Senpai đang chuẩn bị nộp hồ sơ (apply) vào Viettel Software\", \"importance_score\": 0.9}]}\n\n"
            + (
                "Example 2 (Guild Event):\n"
                "  Member: 'Tối thứ 7 tuần này 20h server mình làm giải custom Valorant nha anh em' | Chisa: 'Nghe hào hứng quá, Chisa sẽ cổ vũ cho mọi người nha~'\n"
                "  -> Output: {\"facts\": [{\"type\": \"guild_event\", \"content\": \"Server tổ chức giải đấu Custom Valorant vào tối thứ 7 lúc 20:00\", \"importance_score\": 0.85}]}\n\n"
                if has_guild else ""
            )
            + "Return valid JSON matching schema: {\"facts\": [{\"type\": \"...\", \"content\": \"...\", \"importance_score\": ...}]}"
        )

        transcript = self.build_batch_transcript(history, current_user_message, current_assistant_reply)

        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=transcript,
            response_schema=self.BATCH_RESPONSE_SCHEMA,
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={"use_deep_thinking": False}
        )

        try:
            from app.domain.context import llm_call_purpose
            llm_call_purpose.set("memory_extraction")
            response = await self.llm.generate(prompt)
            parsed = response.parsed or {}
            extracted_facts = parsed.get("facts", [])
            
            # Step 1: Filter and validate extracted facts with strict quality guards
            valid_facts = []
            allowed_types = ["user_fact", "shared_story"]
            if has_guild:
                allowed_types.extend(["guild_event", "guild_culture"])

            for fact in extracted_facts:
                if not isinstance(fact, dict):
                    continue
                fact_type = fact.get("type")
                if fact_type in ("important_facts", "preferences", "relationship", "fact", "core_facts"):
                    fact_type = "user_fact"
                content = (fact.get("content") or "").strip()
                importance = float(fact.get("importance_score", 0.7))
                expires_at = fact.get("expires_at")

                if fact_type not in allowed_types:
                    continue

                if len(content) < 8:
                    continue

                # Enforce minimum quality & importance threshold
                if importance < 0.65:
                    log.debug("Dropped low-importance memory fact", content=content, importance=importance)
                    continue

                # Filter out meta persona definitions
                content_lower = content.lower()
                if "xưng em" in content_lower or "chisa là companion" in content_lower or "chisa là ai" in content_lower:
                    log.info("Dropped meta-persona noise fact", content=content)
                    continue

                valid_facts.append({
                    "type": fact_type,
                    "content": content,
                    "importance_score": importance,
                    "expires_at": expires_at
                })

            if not valid_facts:
                log.info("No valid facts to store after batch extraction", user_id=user_id)
                self._record_pipeline_step(
                    status="skipped",
                    facts=[],
                    extracted_input_context=transcript,
                    raw_facts_count=len(extracted_facts)
                )
                return

            # Step 2: Concurrently / sequentially embed facts & search candidates in Qdrant
            fact_candidate_pairs = []
            reconcile_items = []

            for idx, fact in enumerate(valid_facts):
                content = fact["content"]
                fact_type = fact["type"]
                log.info("Batch extracted memory fact", type=fact_type, content=content, importance=fact["importance_score"], user_id=user_id)
                vector = await self.embedder.embed_text(content, prefix="passage: ")
                
                # Search candidates based on scope
                if fact_type in ["guild_event", "guild_culture"] and has_guild:
                    existing = await self.vector_store.search_guild_memories(
                        collection="guild_memories",
                        query_vector=vector,
                        guild_id=str(guild_id),
                        limit=3,
                        score_threshold=0.70
                    )
                else:
                    existing = await self.vector_store.search_by_user(
                        collection="memories",
                        query_vector=vector,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        limit=3,
                        score_threshold=0.70
                    )

                fact_candidate_pairs.append({
                    "fact": fact,
                    "vector": vector,
                    "existing": existing
                })
                if existing:
                    reconcile_items.append({
                        "index": idx,
                        "content": content,
                        "candidates": existing
                    })

            # Step 3: Run single batched reconciliation LLM call if any candidates exist
            reconcile_results = {}
            if reconcile_items:
                log.info("Triggering single batched memory reconciliation LLM call", items_count=len(reconcile_items))
                reconcile_results = await self.reconcile_memory_conflicts_batch(reconcile_items)

            # Step 4: Process and store facts
            stored_facts = []
            for idx, pair in enumerate(fact_candidate_pairs):
                fact = pair["fact"]
                vector = pair["vector"]
                existing = pair["existing"]
                content = fact["content"]
                fact_type = fact["type"]
                importance = fact["importance_score"]
                expires_at = fact.get("expires_at")

                reconciliation_action = "NONE"
                conflicting_memory_id = None
                target_collection = "guild_memories" if fact_type in ["guild_event", "guild_culture"] and has_guild else "memories"

                if existing and idx in reconcile_results:
                    action, conflicting_id = reconcile_results[idx]
                    reconciliation_action = action
                    conflicting_memory_id = conflicting_id

                    if action == "DUPLICATE":
                        log.info("Skipped duplicate memory", content=content, collection=target_collection)
                        stored_facts.append({
                            "type": fact_type,
                            "content": content,
                            "importance_score": importance,
                            "status": "duplicate",
                            "reconciliation_action": reconciliation_action,
                            "conflicting_id": conflicting_memory_id
                        })
                        continue
                    elif action == "CONTRADICT" and conflicting_id:
                        log.info("Memory conflict resolved — deleting superseded memory", old_id=conflicting_id, new_content=content, collection=target_collection)
                        try:
                            await self.vector_store.delete_points(collection=target_collection, ids=[conflicting_id])
                        except Exception as del_err:
                            log.warning("Failed to delete conflicting memory point", id=conflicting_id, error=str(del_err))

                point_id = str(uuid.uuid4())

                if target_collection == "guild_memories":
                    payload = GuildMemoryPayload(
                        guild_id=str(guild_id),
                        channel_id=str(channel_id) if channel_id else None,
                        memory_type=fact_type,
                        importance_score=importance,
                        created_at=int(time.time()),
                        expires_at=expires_at,
                        text_content=content,
                        recorded_by_speaker=speaker_name,
                    )
                else:
                    payload = MemoryPayload(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        memory_type=fact_type,
                        importance_score=importance,
                        created_at=int(time.time()),
                        text_content=content,
                    )

                await self.vector_store.upsert_memory(
                    collection=target_collection,
                    point_id=point_id,
                    vector=vector,
                    payload=payload
                )

                stored_facts.append({
                    "type": fact_type,
                    "content": content,
                    "importance_score": importance,
                    "status": "extracted",
                    "collection": target_collection,
                    "reconciliation_action": reconciliation_action,
                    "conflicting_id": conflicting_memory_id
                })

            # Record step to visualizer pipeline tracker
            self._record_pipeline_step(
                status="extracted" if stored_facts else "skipped",
                facts=stored_facts,
                extracted_input_context=transcript,
                raw_facts_count=len(extracted_facts)
            )
        except Exception as e:
            log.warning("Batch memory extraction failed", error=str(e))

    def _record_pipeline_step(
        self,
        status: str,
        facts: list[dict[str, Any]],
        extracted_input_context: str,
        raw_facts_count: int = 0
    ) -> None:
        try:
            from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
            pipeline_tracker.add_step(
                name="memory_extraction",
                stage_id="stage_10_bg",
                depth=1,
                category="task",
                title="10.1 [BG] Trích xuất Ký ức (Batch 3 lượt)",
                subtitle=f"{len(facts)} facts trích xuất",
                data={
                    "status": status,
                    "facts": facts,
                    "fact_count": len(facts),
                    "raw_facts_count": raw_facts_count,
                    "extracted_input_context": extracted_input_context,
                }
            )
        except Exception:
            pass
