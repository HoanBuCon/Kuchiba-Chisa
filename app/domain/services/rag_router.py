import re

class RAGRouter:
    """
    Determines if a user message requires Vector Database Retrieval (RAG).
    Conserves API latency and context usage for idle chit-chat.
    """
    # Extremely common 1-3 word small talk phrases
    SMALL_TALK_PHRASES = {
        "haha", "ok", "ừ", "hi", "vâng", "dạ", "chào", "đúng rồi", 
        "thế à", "vậy hả", "à", "ừm", "cảm ơn", "bye", "tạm biệt", 
        "hí hí", "hihi", "hehe", "ê", "hey", "alo"
    }

    @classmethod
    def should_retrieve(cls, message: str) -> dict[str, bool]:
        msg_lower = message.strip().lower()

        # Rule 1: Too short or exact small talk
        # Messages under 8 characters or exactly in the small talk set
        if len(msg_lower) < 8 or msg_lower in cls.SMALL_TALK_PHRASES:
            return {"use_lore": False, "use_memory": False}

        # Rule 2: Explicit triggers for Memory recall
        memory_triggers = [
            "nhớ", "hôm trước", "đã nói", "tên anh", "tên tôi", 
            "sở thích", "đã kể", "kể em nghe",
            "kỷ niệm", "hứa"
        ]
        use_memory = any(trigger in msg_lower for trigger in memory_triggers) or "?" in msg_lower

        # Rule 3: Explicit triggers for Lore/Persona context
        lore_triggers = [
            "honami", "sumika", "kéo", "quá khứ", "cộng hưởng", "học viện", "startorch", "overclock",
            "năng lực", "resonance", "senpai là ai", "cô đơn", "nhà", "sức mạnh",
            "chisa", "em là ai", "sợ", "cô độc", "mèo", "pha trà", "nấu ăn"
        ]
        use_lore = any(trigger in msg_lower for trigger in lore_triggers)

        # Default fallback: If it's a long, descriptive message, 
        # trigger both RAG pipelines to be safe and provide rich context.
        if not use_memory and not use_lore and len(msg_lower) > 30:
            return {"use_lore": True, "use_memory": True}

        return {
            "use_lore": use_lore,
            "use_memory": use_memory
        }
