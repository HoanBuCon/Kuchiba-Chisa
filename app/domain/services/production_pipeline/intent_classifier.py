import enum
import json
import re
from typing import Any, List, Optional
from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

class ChatIntent(str, enum.Enum):
    CHARACTER_LORE = "CHARACTER_LORE"
    WORLD_LORE = "WORLD_LORE"
    STORY_LORE = "STORY_LORE"
    MEMORY = "MEMORY"
    OTHER = "OTHER"
    SYSTEM_ACTION = "SYSTEM_ACTION"

class IntentClassifier:
    """
    Classifies the user query's intent using a fast local Semantic Router
    and high-confidence rule-based fast paths.
    """
    def __init__(self, llm: BaseLLMAdapter, embedder: Optional[IEmbeddingProvider] = None):
        self.llm = llm
        self.embedder = embedder
        self.semantic_router = None
        if embedder:
            from app.domain.services.production_pipeline.semantic_router import SemanticRouter
            self.semantic_router = SemanticRouter(embedder=embedder)
        
    async def classify(self, user_message: str, query_vector: Optional[List[float]] = None) -> List[ChatIntent]:
        # 1. Fast Path: Small talk detection
        from app.domain.services.rag_router import RAGRouter
        if RAGRouter.is_small_talk(user_message):
            log.debug("Intent fast-path: small talk detected", user_message=user_message)
            return [ChatIntent.OTHER]

        # 2. Fast Path: High-confidence keyword/phrase triggers
        msg_lower = user_message.strip().lower()
        
        def has_word(word: str) -> bool:
            return bool(re.search(rf"\b{re.escape(word)}\b", msg_lower))

        high_conf_intents = []

        # High confidence memory triggers
        memory_keywords = [
            "tên anh là gì", "tên tớ là gì", "tên mình là gì", "biệt danh của anh", 
            "sở thích của anh", "ngày mai anh làm gì", "ngày mai anh đi", 
            "hôm trước anh bảo", "hôm qua anh nói", "ngày mai anh phỏng vấn",
            "nhớ biệt danh của anh", "tên anh là", "tên tớ là", "tên mình là"
        ]
        if any(keyword in msg_lower for keyword in memory_keywords):
            high_conf_intents.append(ChatIntent.MEMORY)

        # High confidence character lore triggers
        character_keywords = [
            "vũ khí của em", "vũ khí của chisa", "vòng ở cổ em", "vòng cổ của em", 
            "cái vòng ở cổ", "vòng cổ của chisa", "em thích ăn gì", "sở thích của em", 
            "em thích ăn vặt", "món tủ của em", "chisa thích", "chía thích", 
            "chía tròn", "cây kéo của em", "chiếc kéo của em"
        ]
        if any(keyword in msg_lower for keyword in character_keywords):
            high_conf_intents.append(ChatIntent.CHARACTER_LORE)

        # High confidence world lore triggers
        world_keywords = [
            "sonoro sphere", "tacet discord", "solaris-3", "solaris 3", 
            "lahai-roi", "lahai roi", "spacetrek", "mutant resonator", "resonator là gì"
        ]
        if any(has_word(kw) or kw in msg_lower for kw in world_keywords):
            high_conf_intents.append(ChatIntent.WORLD_LORE)

        # High confidence story lore triggers
        story_keywords = [
            "vòng lặp honami", "vòng lặp của honami", "lễ hội startorch", 
            "học viện startorch", "companion quest", "chapter 3", "chương 3", "cốt truyện chapter"
        ]
        if any(keyword in msg_lower for keyword in story_keywords):
            high_conf_intents.append(ChatIntent.STORY_LORE)

        if high_conf_intents:
            log.info("Intent fast-path: high confidence rules matched", intents=[i.value for i in high_conf_intents], user_message=user_message)
            return high_conf_intents

        # 3. Slow Path: Semantic Router (replacing LLM Fallback)
        if self.semantic_router:
            try:
                matched_intents = await self.semantic_router.classify(user_message, query_vector)
                if matched_intents:
                    log.info("Semantic router matched intents", intents=[i.value for i in matched_intents], user_message=user_message)
                    return matched_intents
            except Exception as e:
                log.warning("Semantic Router classification failed, falling back to keyword list", error=str(e))

        # 4. Fallback: Basic keyword matching
        log.info("Using basic keyword matching fallback for intent", user_message=user_message)
        matched_intents = []
        if any(k in msg_lower for k in ["tên anh là", "biệt danh", "tên của anh", "anh là ai", "nhớ anh", "anh học", "phỏng vấn", "anh chuẩn bị"]):
            matched_intents.append(ChatIntent.MEMORY)
        if any(k in msg_lower for k in ["chisa là", "kuchiba", "em là ai", "em thích", "em ghét", "sở thích", "tuổi", "vũ khí", "vòng cổ", "cái vòng ở cổ", "kéo đó", "học viện nào", "ăn vặt", "đút ớt", "ăn ớt"]):
            matched_intents.append(ChatIntent.CHARACTER_LORE)
        if any(k in msg_lower for k in ["sonoro", "sphere", "tacet", "discord", "solaris", "lahai", "resonator"]):
            matched_intents.append(ChatIntent.WORLD_LORE)
        if any(k in msg_lower for k in ["chapter", "chương", "cốt truyện", "quest", "sự kiện", "vòng lặp", "sống sót"]):
            matched_intents.append(ChatIntent.STORY_LORE)
        if any(k in msg_lower for k in ["xóa", "clear", "reset", "đổi biệt danh", "gọi anh là"]):
            matched_intents.append(ChatIntent.SYSTEM_ACTION)
        
        if not matched_intents:
            matched_intents.append(ChatIntent.OTHER)
        return matched_intents

