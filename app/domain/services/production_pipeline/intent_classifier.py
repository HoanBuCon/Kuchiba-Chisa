import enum
import json
from typing import Any
from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

class ChatIntent(str, enum.Enum):
    CHARACTER_LORE = "CHARACTER_LORE"
    WORLD_LORE = "WORLD_LORE"
    STORY_LORE = "STORY_LORE"
    MEMORY = "MEMORY"
    OTHER = "OTHER"

class IntentClassifier:
    """
    Classifies the user query's intent using a fast LLM call.
    """
    def __init__(self, llm: BaseLLMAdapter):
        self.llm = llm
        self.RESPONSE_SCHEMA = {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [intent.value for intent in ChatIntent]
                }
            },
            "required": ["intent"]
        }
        
    async def classify(self, user_message: str) -> ChatIntent:
        system_prompt = (
            "You are a precise classifier that determines the intent of a user message "
            "in a chatbot conversation with Kuchiba Chisa (a character from Wuthering Waves).\n"
            "Classify the user message into one of the following intents:\n"
            "- CHARACTER_LORE: User is asking about Chisa herself (her profile, personality, past, "
            "Honami city, Sumika's diary, preferences, weaknesses, weapon, etc.).\n"
            "- WORLD_LORE: User is asking about game world concepts (resonators, tacet discords, "
            "sonoro spheres, Solaris-3, Lahai-Roi, Spacetrek, factions, etc.).\n"
            "- STORY_LORE: User is asking about story chapters, companion quests, or events "
            "(Chapter 1, Chapter 2, Chapter 3, companion quest line, school festival event).\n"
            "- MEMORY: User is asking about or referring to their personal memories, past chats, "
            "relationship details, promises, user details (e.g. 'what is my name?', 'what did we do yesterday?', "
            "'remember my nickname?', 'I am studying AI', 'anh chuẩn bị phỏng vấn').\n"
            "- OTHER: General chit-chat, greetings, small talk, coding, math, general questions, "
            "or anything else that doesn't fit the above categories.\n\n"
            "Output JSON ONLY in this format:\n"
            "{\"intent\": \"INTENT_NAME\"}"
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
            intent_str = parsed.get("intent", "OTHER").upper()
            return ChatIntent(intent_str)
        except Exception as e:
            log.warning("Intent classification failed, falling back to OTHER", error=str(e))
            # Rules fallback
            msg_lower = user_message.lower()
            if any(k in msg_lower for k in ["tên anh là", "biệt danh", "tên của anh", "anh là ai", "nhớ anh", "anh học", "phỏng vấn"]):
                return ChatIntent.MEMORY
            elif any(k in msg_lower for k in ["chisa là", "kuchiba", "em là ai", "em thích", "em ghét", "sở thích", "tuổi", "vũ khí"]):
                return ChatIntent.CHARACTER_LORE
            elif any(k in msg_lower for k in ["sonoro", "sphere", "tacet", "discord", "solaris", "lahai", "resonator"]):
                return ChatIntent.WORLD_LORE
            elif any(k in msg_lower for k in ["chapter", "chương", "cốt truyện", "quest", "sự kiện"]):
                return ChatIntent.STORY_LORE
            return ChatIntent.OTHER
