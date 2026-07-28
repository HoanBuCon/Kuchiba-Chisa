import json
import uuid
import time
from typing import Any, Optional
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.entities.memory import MemoryPayload
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.tuning.memory import MemoryTuning
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

    async def reconcile_memory_conflict(
        self,
        new_fact: str,
        candidates: list[dict[str, Any]],
    ) -> tuple[str, Optional[str]]:
        """
        Uses LLM to evaluate logic relationship between a new fact and candidate existing memories.
        Returns (action, conflicting_id) where action is 'CONTRADICT', 'DUPLICATE', or 'KEEP_BOTH'.
        """
        if not candidates:
            return "KEEP_BOTH", None

        # Format candidates for LLM prompt
        candidates_formatted = []
        for c in candidates:
            c_id = c.get("id")
            c_text = c.get("payload", {}).get("text_content") or c.get("text_content") or ""
            candidates_formatted.append(f"- ID: {c_id} | Content: \"{c_text}\"")

        candidates_str = "\n".join(candidates_formatted)

        schema = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["CONTRADICT", "DUPLICATE", "KEEP_BOTH"]
                },
                "conflicting_id": {"type": "string"},
                "reasoning": {"type": "string"}
            },
            "required": ["action"]
        }

        system_prompt = (
            "You are a Memory Reconciliation AI.\n"
            "Your job is to compare a NEW extracted fact about the user against EXISTING stored memories.\n\n"
            "Determine the logical relationship:\n"
            "1. 'CONTRADICT': The NEW fact directly contradicts, updates, or supersedes an existing memory "
            "(e.g. user changed preference, job, location, opinion, or status). Set 'conflicting_id' to the ID of the old memory to delete.\n"
            "2. 'DUPLICATE': The NEW fact is exact same or semantically identical to an existing memory. No need to store again.\n"
            "3. 'KEEP_BOTH': Both facts are true, distinct, and complementary (they do NOT contradict each other).\n\n"
            "Output JSON format:\n"
            "{\"action\": \"CONTRADICT\" | \"DUPLICATE\" | \"KEEP_BOTH\", \"conflicting_id\": \"...\", \"reasoning\": \"...\"}"
        )

        user_prompt = (
            f"NEW FACT: \"{new_fact}\"\n\n"
            f"EXISTING CANDIDATE MEMORIES:\n{candidates_str}"
        )

        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=user_prompt,
            response_schema=schema,
        )

        try:
            response = await self.llm.generate(prompt)
            parsed = response.parsed or {}
            action = str(parsed.get("action", "KEEP_BOTH")).upper()
            conflicting_id = parsed.get("conflicting_id")
            
            if action not in ["CONTRADICT", "DUPLICATE", "KEEP_BOTH"]:
                action = "KEEP_BOTH"

            return action, conflicting_id
        except Exception as e:
            log.warning("Memory conflict reconciliation LLM call failed, falling back to safe KEEP_BOTH", error=str(e))
            return "KEEP_BOTH", None

    async def extract_and_store(self, user_id: str, conversation_id: str, user_message: str) -> None:
        system_prompt = (
            "You are an information extraction assistant.\n"
            "Your job is to extract important, persistent facts or preferences about the user or their relationship "
            "from their message.\n\n"
            "Examples:\n"
            "- User: 'Anh sắp phỏng vấn Viettel.' -> Output: {\"type\": \"important_facts\", \"content\": \"Senpai sắp phỏng vấn Viettel\", \"importance_score\": 0.9}\n"
            "- User: 'Anh thích ăn bánh ngọt lắm.' -> Output: {\"type\": \"preferences\", \"content\": \"Senpai thích ăn bánh ngọt\", \"importance_score\": 0.6}\n"
            "- User: 'Hãy nhớ là biệt danh anh đặt cho em là Chía tròn nhé.' -> Output: {\"type\": \"relationship\", \"content\": \"Senpai đặt biệt danh cho em là Chía tròn\", \"importance_score\": 1.0}\n\n"
            "Supported Types: 'preferences', 'shared_memories', 'relationship', 'important_facts'.\n"
            "If no new important facts, preferences or relationship details are mentioned in the message, set type to 'none'.\n"
            "Also provide an 'importance_score' between 0.1 and 1.0 indicating how critical this fact is to remember long-term.\n"
            "Only extract facts about the user/relationship. Do not extract random chit-chat, questions, or statements that are not persistent.\n"
            "Output JSON ONLY in this format:\n"
            "{\"type\": \"...\", \"content\": \"...\", \"importance_score\": ...}"
        )
        
        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=user_message,
            response_schema=self.RESPONSE_SCHEMA,
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={}
        )
        
        try:
            response = await self.llm.generate(prompt)
            parsed = response.parsed or {}
            fact_type = parsed.get("type", "none")
            content = parsed.get("content", "").strip()
            importance = float(parsed.get("importance_score", 0.5))

            if fact_type != "none" and content:
                log.info("Extracted memory fact from user message", type=fact_type, content=content, importance=importance, user_id=user_id)
                
                # Embed and search candidate memories (Tier 1: Fast Vector Search @ threshold 0.70)
                vector = await self.embedder.embed_text(content, prefix="passage: ")
                
                existing = await self.vector_store.search_by_user(
                    collection="memories",
                    query_vector=vector,
                    user_id=user_id,
                    limit=3,
                    score_threshold=0.70
                )
                
                if existing:
                    # Tier 2: Precise LLM Reconciliation
                    action, conflicting_id = await self.reconcile_memory_conflict(content, existing)
                    
                    if action == "DUPLICATE":
                        log.info("Skipped memory insertion — duplicate fact detected", content=content)
                        return
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
        except Exception as e:
            log.warning("Memory extraction failed", error=str(e))
