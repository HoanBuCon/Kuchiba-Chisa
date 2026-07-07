import json
import uuid
import time
from typing import Any, Optional
from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.vector.qdrant.qdrant_service import QdrantService, MemoryPayload
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

class MemoryExtractor:
    """
    Background worker that extracts long-term facts/preferences from user messages and stores them.
    """
    def __init__(self, llm: BaseLLMAdapter, embedder: IEmbeddingProvider, qdrant: QdrantService):
        self.llm = llm
        self.embedder = embedder
        self.qdrant = qdrant
        self.RESPONSE_SCHEMA = {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["preferences", "shared_memories", "relationship", "important_facts", "none"]
                },
                "content": {"type": "string"}
            },
            "required": ["type"]
        }

    async def extract_and_store(self, user_id: str, conversation_id: str, user_message: str) -> None:
        system_prompt = (
            "You are an information extraction assistant.\n"
            "Your job is to extract important, persistent facts or preferences about the user or their relationship "
            "from their message.\n\n"
            "Examples:\n"
            "- User: 'Anh sắp phỏng vấn Viettel.' -> Output: {\"type\": \"important_facts\", \"content\": \"Senpai sắp phỏng vấn Viettel\"}\n"
            "- User: 'Anh thích ăn bánh ngọt lắm.' -> Output: {\"type\": \"preferences\", \"content\": \"Senpai thích ăn bánh ngọt\"}\n"
            "- User: 'Hãy nhớ là biệt danh anh đặt cho em là Chía tròn nhé.' -> Output: {\"type\": \"relationship\", \"content\": \"Senpai đặt biệt danh cho em là Chía tròn\"}\n\n"
            "Supported Types: 'preferences', 'shared_memories', 'relationship', 'important_facts'.\n"
            "If no new important facts, preferences or relationship details are mentioned in the message, set type to 'none'.\n"
            "Only extract facts about the user/relationship. Do not extract random chit-chat, questions, or statements that are not persistent.\n"
            "Output JSON ONLY in this format:\n"
            "{\"type\": \"...\", \"content\": \"...\"}"
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
            
            if fact_type != "none" and content:
                log.info("Extracted memory fact from user message", type=fact_type, content=content, user_id=user_id)
                
                # Embed and save
                vector = await self.embedder.embed_text(content)
                point_id = str(uuid.uuid4())
                
                payload = MemoryPayload(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    memory_type=fact_type,
                    importance_score=0.8,
                    created_at=int(time.time()),
                    text_content=content,
                )
                
                await self.qdrant.upsert_memory(
                    collection="memories",
                    point_id=point_id,
                    vector=vector,
                    payload=payload
                )
        except Exception as e:
            log.warning("Memory extraction failed", error=str(e))
