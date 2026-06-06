import re


class RAGRouter:
    """
    Determines if a user message requires Vector Database Retrieval (RAG).
    
    Architecture (post-refactor):
    - Lore retrieval: Always performed via vector search + threshold filtering.
      RAGRouter no longer gates lore — ChatEngine handles it directly.
    - Memory retrieval: Still keyword-triggered (memory recall is intent-driven).
    - Small talk detection: Shared utility to skip embedding entirely for trivial messages.
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
    def is_small_talk(cls, message: str) -> bool:
        """
        Returns True if the message is trivial small talk that doesn't warrant
        any RAG retrieval (neither lore nor memory).
        Used by ChatEngine to skip embedding entirely for "ok", "haha", etc.
        """
        msg_lower = message.strip().lower()
        return len(msg_lower) < 8 or msg_lower in cls.SMALL_TALK_PHRASES

    @classmethod
    def should_retrieve(cls, message: str) -> dict[str, bool]:
        """
        Determines RAG retrieval needs for a message.
        
        Post-refactor:
        - use_lore: Always starts as True (actual filtering done by vector threshold in ChatEngine).
          Set to False only for small talk.
        - use_memory: Keyword-triggered (memory recall is intent-driven).
        """
        msg_lower = message.strip().lower()

        # Rule 1: Small talk — skip everything
        if cls.is_small_talk(message):
            return {"use_lore": False, "use_memory": False}

        # Rule 2: Explicit triggers for Memory recall
        memory_triggers = [
            "nhớ", "hôm trước", "đã nói", "tên anh", "tên tôi", "tên tớ", 
            "tên mình", "tên em", "sở thích", "đã kể", "kể em nghe", 
            "kể cho em", "kỷ niệm", "hứa", "nhớ không", "phải không", 
            "đúng không", "quên chưa", "quên không", "nhớ chứ", "có nhớ", 
            "biết ai không", "là ai nhỉ", "tên gì nhỉ", "tên là gì", 
            "sở thích là gì", "thích gì", "chúng ta đã"
        ]
        use_memory = any(cls._contains_word(msg_lower, trigger) for trigger in memory_triggers)

        # Lore is always searched via vector DB — ChatEngine handles threshold filtering
        # We set use_lore=True here as a signal that embedding should be computed.
        # ChatEngine will override this to False if no chunks pass the threshold.
        return {
            "use_lore": True,
            "use_memory": use_memory
        }
