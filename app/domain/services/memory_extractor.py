import uuid
import time
from typing import Any, Optional
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.entities.memory import MemoryPayload
from app.domain.interfaces.vector_store import IVectorStore
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class MemoryExtractor:
    """
    Background worker that extracts long-term facts/preferences from user messages and stores them.
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
                    "enum": ["preferences", "shared_memories", "relationship", "important_facts", "none"]
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
                                "enum": ["preferences", "shared_memories", "relationship", "important_facts"]
                            },
                            "content": {"type": "string"},
                            "importance_score": {
                                "type": "number",
                                "minimum": 0.1,
                                "maximum": 1.0
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
    ) -> None:
        """
        Batched background worker: Analyzes a 3-pair conversation window (+ 2 preceding user messages)
        to extract multi-fact milestones, preferences, or nicknames, and saves them to Vector DB.
        """
        system_prompt = (
            "Extract persistent facts, preferences, milestones, nicknames, or mutual commitments from the 3-turn conversation snippet between Senpai (User) and Chisa (AI Companion).\n\n"
            "EXTRACTION RULES:\n"
            "1. Bidirectional: Capture facts stated by Senpai (career, habits, preferences, life events) OR mutual agreements/nicknames established by Chisa/Senpai.\n"
            "2. Strict Roleplay Filter: Ignore Chisa's emotional roleplay filler, poetic descriptions ('phân tích cấu trúc', sweet compliments), and daily small-talk. Only extract concrete, persistent information.\n"
            "3. Types:\n"
            "   - 'preferences': Senpai's lasting tastes, habits, likes/dislikes.\n"
            "   - 'important_facts': Real-world info (jobs, events, locations, exams, achievements).\n"
            "   - 'relationship': Nicknames, terms of endearment, special relationship dynamic.\n"
            "   - 'shared_memories': Concrete mutual promises, plans, or shared milestones.\n"
            "4. Multiple Facts Allowed: Return all persistent facts found across the turns in the 'facts' array. If no persistent facts exist, return {\"facts\": []}.\n"
            "5. Importance: Float (0.1 - 1.0) reflecting longevity and significance.\n\n"
            "FEW-SHOT EXAMPLES:\n"
            "- Snippet:\n"
            "  [BỐI CẢNH]: Senpai: 'anh đang nộp hồ sơ xin việc'\n"
            "  Cặp 1: Senpai: 'anh nộp Viettel rồi' | Chisa: 'Chúc Senpai may mắn nha!'\n"
            "  Cặp 2: Senpai: 'anh thích uống matcha để tập trung' | Chisa: 'Dạ matcha thanh mát lắm nè~'\n"
            "  Cặp 3: Senpai: 'anh vừa nhận offer Viettel!' | Chisa: 'Oa chúc mừng Senpai nha!'\n"
            "  -> Output: {\"facts\": [\n"
            "       {\"type\": \"important_facts\", \"content\": \"Senpai đã nhận được offer làm việc tại Viettel\", \"importance_score\": 0.95},\n"
            "       {\"type\": \"preferences\", \"content\": \"Senpai thích uống matcha để tập trung\", \"importance_score\": 0.7}\n"
            "     ]}\n"
            "- Snippet:\n"
            "  Cặp 1: Senpai: 'hôm nay em vui không' | Chisa: 'Em đang phân tích niềm vui nè~'\n"
            "  Cặp 2: Senpai: 'thời tiết đẹp ghê' | Chisa: 'Dạ trời trong xanh lắm ạ.'\n"
            "  Cặp 3: Senpai: 'tối nay ăn gì nhỉ' | Chisa: 'Senpai ăn món gì nhẹ nhàng nhé~'\n"
            "  -> Output: {\"facts\": []}\n\n"
            "Return JSON matching schema: {\"facts\": [{\"type\": \"...\", \"content\": \"...\", \"importance_score\": ...}]}"
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
            
            # Step 1: Filter and validate extracted facts
            valid_facts = []
            for fact in extracted_facts:
                if not isinstance(fact, dict):
                    continue
                fact_type = fact.get("type")
                content = (fact.get("content") or "").strip()
                importance = float(fact.get("importance_score", 0.7))

                if not fact_type or len(content) < 5:
                    continue

                valid_facts.append({
                    "type": fact_type,
                    "content": content,
                    "importance_score": importance,
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
                log.info("Batch extracted memory fact", type=fact["type"], content=content, importance=fact["importance_score"], user_id=user_id)
                vector = await self.embedder.embed_text(content, prefix="passage: ")
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

                reconciliation_action = "NONE"
                conflicting_memory_id = None

                if existing and idx in reconcile_results:
                    action, conflicting_id = reconcile_results[idx]
                    reconciliation_action = action
                    conflicting_memory_id = conflicting_id

                    if action == "DUPLICATE":
                        log.info("Skipped duplicate memory", content=content)
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
                        log.info("Memory conflict resolved — deleting superseded memory", old_id=conflicting_id, new_content=content)
                        try:
                            await self.vector_store.delete_points(collection="memories", ids=[conflicting_id])
                        except Exception as del_err:
                            log.warning("Failed to delete conflicting memory point", id=conflicting_id, error=str(del_err))

                point_id = str(uuid.uuid4())
                payload = MemoryPayload(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    memory_type=fact_type,
                    importance_score=importance,
                    created_at=int(time.time()),
                    text_content=content,
                )

                await self.vector_store.upsert_memory(
                    collection="memories",
                    point_id=point_id,
                    vector=vector,
                    payload=payload
                )

                stored_facts.append({
                    "type": fact_type,
                    "content": content,
                    "importance_score": importance,
                    "status": "extracted",
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
            pipeline_tracker.add_step("memory_extraction", {
                "status": status,
                "facts": facts,
                "fact_count": len(facts),
                "raw_facts_count": raw_facts_count,
                "extracted_input_context": extracted_input_context,
            })
        except Exception:
            pass
