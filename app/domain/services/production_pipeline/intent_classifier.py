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
                "intents": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [intent.value for intent in ChatIntent]
                    }
                }
            },
            "required": ["intents"]
        }
        
    async def classify(self, user_message: str) -> list[ChatIntent]:
        system_prompt = (
            "You are a precise classifier that determines the intent of a user message "
            "in a chatbot conversation with Kuchiba Chisa (a character from Wuthering Waves).\n\n"
            "Classify the user message into one or MORE of the following intents. "
            "If the message has implications for multiple categories (e.g. asking about both Chisa's weapon "
            "and user memory), list all of them. If only one applies, list that one. If it is only general small talk, output [\"OTHER\"].\n\n"
            "Intents:\n"
            "- CHARACTER_LORE: User is asking about Chisa herself (her profile, personality, past, "
            "how she survived the loop, her neck ring, her weapon, her preferences, food/snack likes/dislikes, "
            "e.g. 'em thích ăn vặt gì', 'cái vòng ở cổ em là sao', 'chisa là ai', 'vũ khí của em là gì').\n"
            "- WORLD_LORE: User is asking about game world concepts (resonators, tacet discords, "
            "sonoro spheres, Solaris-3, Lahai-Roi, Spacetrek, factions, etc., "
            "e.g. 'sonoro sphere là gì', 'resonator là gì', 'lahai-roi ở đâu').\n"
            "- STORY_LORE: User is asking about story chapters, companion quests, or events "
            "(Chapter 1, Chapter 2, Chapter 3, companion quest line, school festival event, "
            "e.g. 'cốt truyện chapter 3', 'lễ hội học viện startorch', 'làm sao sống sót qua vòng lặp').\n"
            "- MEMORY: User is asking about the USER'S personal details, user's schedule, user's nickname, "
            "or shared memories between User and Chisa (e.g. 'tên anh là gì', 'ngày mai anh làm gì', "
            "'nhớ biệt danh của anh không', 'anh vừa bảo gì'). It must concern the USER, not Chisa's backstory.\n"
            "- OTHER: General greetings, chit-chat, small talk, general questions that do not require game lore "
            "(e.g. 'hi em', 'hôm nay trời đẹp nhỉ', 'chúc ngủ ngon', '1+1 bằng mấy').\n\n"
            "Few-shot Examples:\n"
            "1. User: 'Học viện nào vậy em?' -> {\"intents\": [\"CHARACTER_LORE\"]}\n"
            "2. User: 'Cây kéo đó để làm gì?' -> {\"intents\": [\"CHARACTER_LORE\"]}\n"
            "3. User: 'Cái vòng ở cổ em là sao?' -> {\"intents\": [\"CHARACTER_LORE\"]}\n"
            "4. User: 'Làm sao em sống sót qua vòng lặp?' -> {\"intents\": [\"STORY_LORE\"]}\n"
            "5. User: 'Em thích ăn vặt gì nhất?' -> {\"intents\": [\"CHARACTER_LORE\"]}\n"
            "6. User: 'Anh đút ớt cho em ăn nhé?' -> {\"intents\": [\"CHARACTER_LORE\"]}\n"
            "7. User: 'Ngày mai anh làm gì em nhớ không?' -> {\"intents\": [\"MEMORY\"]}\n"
            "8. User: 'Chào em, hôm nay trời đẹp thế!' -> {\"intents\": [\"OTHER\"]}\n"
            "9. User: 'Em thích ăn vặt gì và hôm qua anh đã hứa gì với em?' -> {\"intents\": [\"CHARACTER_LORE\", \"MEMORY\"]}\n"
            "10. User: 'Kể cho anh nghe về vòng lặp Honami và ngày mai anh phỏng vấn ở đâu ấy nhỉ?' -> {\"intents\": [\"STORY_LORE\", \"MEMORY\"]}\n\n"
            "Output JSON ONLY in this format:\n"
            "{\"intents\": [\"INTENT_NAME_1\", \"INTENT_NAME_2\"]}"
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
            intent_strs = parsed.get("intents", ["OTHER"])
            if isinstance(intent_strs, str):
                intent_strs = [intent_strs]
            intents = []
            for s in intent_strs:
                try:
                    intents.append(ChatIntent(s.upper()))
                except ValueError:
                    continue
            if not intents:
                intents = [ChatIntent.OTHER]
            return intents
        except Exception as e:
            log.warning("Intent classification failed, falling back to rule-based list", error=str(e))
            # Rules fallback
            msg_lower = user_message.lower()
            matched_intents = []
            if any(k in msg_lower for k in ["tên anh là", "biệt danh", "tên của anh", "anh là ai", "nhớ anh", "anh học", "phỏng vấn", "anh chuẩn bị"]):
                matched_intents.append(ChatIntent.MEMORY)
            if any(k in msg_lower for k in ["chisa là", "kuchiba", "em là ai", "em thích", "em ghét", "sở thích", "tuổi", "vũ khí", "vòng cổ", "cái vòng ở cổ", "kéo đó", "học viện nào", "ăn vặt", "đút ớt", "ăn ớt"]):
                matched_intents.append(ChatIntent.CHARACTER_LORE)
            if any(k in msg_lower for k in ["sonoro", "sphere", "tacet", "discord", "solaris", "lahai", "resonator"]):
                matched_intents.append(ChatIntent.WORLD_LORE)
            if any(k in msg_lower for k in ["chapter", "chương", "cốt truyện", "quest", "sự kiện", "vòng lặp", "sống sót"]):
                matched_intents.append(ChatIntent.STORY_LORE)
            
            if not matched_intents:
                matched_intents.append(ChatIntent.OTHER)
            return matched_intents
