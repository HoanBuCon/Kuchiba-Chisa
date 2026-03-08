import logging

log = logging.getLogger(__name__)

class ContextBudgetManager:
    """
    Manages the token budget before sending the prompt to the LLM.
    Uses an approximation: 1 token ≈ 4 characters in Vietnamese BPE.
    """
    TOTAL_BUDGET = 6000
    SYSTEM_PROMPT_RESERVE = 800
    CHARS_PER_TOKEN = 4

    @classmethod
    def _estimate_tokens(cls, text: str) -> int:
        if not text:
            return 0
        return len(text) // cls.CHARS_PER_TOKEN

    @classmethod
    def enforce_budget(
        cls, 
        lore_chunks: list[str], 
        memories: list[str], 
        history: list[dict[str, str]]
    ) -> tuple[list[str], list[str], list[dict[str, str]]]:
        """
        Dynamically trims lore, memories, and history so they fit the safe budget.
        Allocations:
        - Lore max: 1500 tokens
        - Memory max: 1200 tokens
        - History max: 2500 tokens (or remaining)
        """
        remaining_budget = cls.TOTAL_BUDGET - cls.SYSTEM_PROMPT_RESERVE

        # 1. Budget Lore (Max 1500 tokens)
        trimmed_lore = []
        lore_tokens = 0
        for chunk in lore_chunks:
            chunk_tokens = cls._estimate_tokens(chunk)
            if lore_tokens + chunk_tokens <= 1500:
                trimmed_lore.append(chunk)
                lore_tokens += chunk_tokens
            else:
                log.debug(f"Lore context trimmed to {lore_tokens} tokens.")
                break
        remaining_budget -= lore_tokens

        # 2. Budget Memories (Max 1200 tokens)
        trimmed_memories = []
        memory_tokens = 0
        for mem in memories:
            # Handle both ScoredMemory objects and simple strings
            text_val = mem.text_content if hasattr(mem, "text_content") else str(mem)
            mem_tokens = cls._estimate_tokens(text_val)
            if memory_tokens + mem_tokens <= 1200:
                trimmed_memories.append(mem)
                memory_tokens += mem_tokens
            else:
                log.debug(f"Memory context trimmed to {memory_tokens} tokens.")
                break
        remaining_budget -= memory_tokens

        # 3. Budget History (Trim oldest messages first)
        trimmed_history = []
        history_tokens = 0
        
        # We iterate history in reverse (newest first) but it's usually 
        # already passed as newest-last or newest-first depending on caller.
        # ChatEngine passes history chronologically (newest is at end).
        # We need to iterate from end (newest) to start (oldest).
        for msg in reversed(history):
            content_tokens = cls._estimate_tokens(msg.get("content", ""))
            msg_tokens = content_tokens + 10  # Token overhead per message
            
            if history_tokens + msg_tokens <= remaining_budget:
                trimmed_history.insert(0, msg)  # Maintain chronological order
                history_tokens += msg_tokens
            else:
                log.info(f"Chat history trimmed. Discarded oldest messages. Used tokens: {history_tokens}")
                break

        return trimmed_lore, trimmed_memories, trimmed_history
