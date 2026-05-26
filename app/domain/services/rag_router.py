import re

class RAGRouter:
    """
    Determines if a user message requires Vector Database Retrieval (RAG).
    Conserves API latency and context usage for idle chit-chat.
    """
    # Extremely common 1-3 word small talk phrases, greetings, emojis, and particles.
    SMALL_TALK_PHRASES = {
        "haha", "ok", "ừ", "hi", "vâng", "dạ", "chào", "đúng rồi", 
        "thế à", "vậy hả", "à", "ừm", "cảm ơn", "bye", "tạm biệt", 
        "hí hí", "hihi", "hehe", "ê", "hey", "alo", "lô", "lô lô",
        "dạ vâng", "dạ đúng rồi", "chuẩn", "chuẩn luôn", "chính xác",
        "uầy", "chà", "wow", "oh", "ô", "ôi", "haiz", "hầy", "hic",
        "huhu", "ahihi", "kaka", "kkk", "lol", "lmao", "hello", "halo",
        "bye bye", "g9", "ngủ ngon", "thế á", "vậy á", "thế hả", "thế nhở",
        "thank", "thanks", "tks", "ty", "thx", "được thôi", "được", "ừm hửm",
        "hửm", "hử", "gì cơ", "sao cơ", "sao thế", "ừ thế", "thế thôi",
        "okay", "nha", "nhé", "nè", "nhen", "hén", "đấy", "đó", "thế", "vậy"
    }

    @staticmethod
    def _contains_word(text: str, trigger: str) -> bool:
        """
        Checks if the trigger is present in the text as a whole word/phrase
        using word boundaries. Handles Vietnamese accents correctly in Python 3.
        """
        pattern = rf"\b{re.escape(trigger)}\b"
        return bool(re.search(pattern, text))

    @classmethod
    def should_retrieve(cls, message: str) -> dict[str, bool]:
        msg_lower = message.strip().lower()

        # Rule 1: Too short or exact small talk
        # Messages under 8 characters or exactly in the small talk set
        if len(msg_lower) < 8 or msg_lower in cls.SMALL_TALK_PHRASES:
            return {"use_lore": False, "use_memory": False}

        # Rule 2: Explicit triggers for Memory recall
        # Removes aggressive "?" matching, substituting with exact query boundaries.
        memory_triggers = [
            "nhớ", "hôm trước", "đã nói", "tên anh", "tên tôi", "tên tớ", 
            "tên mình", "tên em", "sở thích", "đã kể", "kể em nghe", 
            "kể cho em", "kỷ niệm", "hứa", "nhớ không", "phải không", 
            "đúng không", "quên chưa", "quên không", "nhớ chứ", "có nhớ", 
            "biết ai không", "là ai nhỉ", "tên gì nhỉ", "tên là gì", 
            "sở thích là gì", "thích gì", "chúng ta đã"
        ]
        use_memory = any(cls._contains_word(msg_lower, trigger) for trigger in memory_triggers)

        # Rule 3: Explicit triggers for Lore/Persona context
        # Prevents false positive substring collisions (e.g., 'kéo' in 'kéo dài', 'nhà' in 'nhàn nhã')
        # by checking boundaries and using specific multi-word tokens.
        lore_triggers = [
            "honami", "sumika", "cây kéo", "chiếc kéo", "kéo khổng lồ", 
            "quá khứ", "cộng hưởng", "học viện", "startorch", "overclock", 
            "overclocking", "năng lực", "resonance", "senpai là ai", 
            "cô đơn", "cô độc", "gia đình", "quê hương", "sức mạnh", 
            "chisa", "em là ai", "nỗi sợ", "sợ hãi", "lo sợ", "mèo", 
            "mèo con", "chú mèo", "pha trà", "nấu ăn", "broadblade", 
            "lahai-roi", "solaris-3", "ashinohara", "tacet", "sonoro", 
            "forte", "nhật ký", "di vật", "vòng lặp"
        ]
        use_lore = any(cls._contains_word(msg_lower, trigger) for trigger in lore_triggers)

        # Default fallback: If it's a long, descriptive message, 
        # trigger both RAG pipelines to be safe and provide rich context.
        # Threshold increased from 30 to 65 for optimal token conservation.
        if not use_memory and not use_lore and len(msg_lower) > 65:
            return {"use_lore": True, "use_memory": True}

        return {
            "use_lore": use_lore,
            "use_memory": use_memory
        }
