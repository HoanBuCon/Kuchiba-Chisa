import asyncio
import os
import sys

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from app.domain.services.context_budget_manager import ContextBudgetManager

def make_long_string(word: str, length_in_chars: int) -> str:
    # 2 characters = 1 token
    # Generates a string of specified character length
    repeats = length_in_chars // len(word)
    return (word * repeats)[:length_in_chars]

def main():
    print("=" * 70)
    print("       TESTING DYNAMIC CONTEXT BUDGET ENFORCEMENT & TRIMMING")
    print("=" * 70)

    # 1. Prepare Mock Data
    # 5 Lore chunks, each 500 chars (250 tokens). Total 1250 tokens
    lore_chunks = [
        make_long_string(f"Lore{i} ", 500) for i in range(1, 6)
    ]
    
    # 5 Memory chunks, each 400 chars (200 tokens). Total 1000 tokens
    memories = [
        make_long_string(f"Memory{i} ", 400) for i in range(1, 6)
    ]
    
    # 20 History messages, alternating user/assistant.
    # Each message is 300 chars (150 tokens) + 10 token overhead = 160 tokens each.
    # Total history: 20 * 160 = 3200 tokens.
    history = []
    for i in range(1, 21):
        role = "user" if i % 2 == 1 else "assistant"
        content = make_long_string(f"Message{i}_content_long_and_detailed_conversation_turn ", 300)
        history.append({"role": role, "content": content})

    # Print input sizes
    total_input_tokens = (
        sum(len(l) // 2 for l in lore_chunks) +
        sum(len(m) // 2 for m in memories) +
        sum((len(h["content"]) // 2 + 10) for h in history)
    )
    print(f"\n[Raw Input Sizes]:")
    print(f"  - Lore: {len(lore_chunks)} chunks, approx {sum(len(l) // 2 for l in lore_chunks)} tokens")
    print(f"  - Memories: {len(memories)} chunks, approx {sum(len(m) // 2 for m in memories)} tokens")
    print(f"  - History: {len(history)} messages, approx {sum((len(h['content']) // 2 + 10) for h in history)} tokens")
    print(f"  - Total Input: approx {total_input_tokens} tokens (excluding system prompt)")

    # ----------------------------------------------------
    # TEST CASE 1: Small Talk (Budget = 5000 tokens)
    # ----------------------------------------------------
    print("\n" + "-" * 60)
    print("[*] Test Case 1: Small Talk (Budget = 5000 tokens, System Reserve = 800)")
    print("-" * 60)
    t_lore, t_memories, t_history = ContextBudgetManager.enforce_budget(
        lore_chunks=lore_chunks,
        memories=memories,
        history=history,
        total_budget=5000
    )
    
    lore_tokens = sum(len(l) // 2 for l in t_lore)
    mem_tokens = sum(len(m) // 2 for m in t_memories)
    hist_tokens = sum((len(h["content"]) // 2 + 10) for h in t_history)
    
    print(f"[+] Output Lore: {len(t_lore)} chunks ({lore_tokens} tokens)")
    print(f"[+] Output Memories: {len(t_memories)} chunks ({mem_tokens} tokens)")
    print(f"[+] Output History: {len(t_history)} messages ({hist_tokens} tokens)")
    print(f"[+] Total Output Context: {lore_tokens + mem_tokens + hist_tokens} tokens")
    
    # Assertions
    assert len(t_lore) == 0, "Small Talk should have 0 lore chunks"
    assert len(t_memories) == 0, "Small Talk should have 0 memories"
    assert lore_tokens + mem_tokens + hist_tokens <= 4200, "Output context must be <= 4200 (5000 - 800)"
    assert t_history[-1]["content"].startswith("Message20"), "Should keep the newest messages (Message20)"
    print("  [✓] Pass: Small Talk budget correctly enforced (RAG excluded, newest history preserved).")

    # ----------------------------------------------------
    # TEST CASE 2: RAG Talk (Budget = 8000 tokens)
    # ----------------------------------------------------
    print("\n" + "-" * 60)
    print("[*] Test Case 2: RAG Talk (Budget = 8000 tokens, System Reserve = 800)")
    print("-" * 60)
    # Scale up history to exceed budget (Add 15 more messages)
    large_history = history.copy()
    for i in range(21, 71):
        role = "user" if i % 2 == 1 else "assistant"
        content = make_long_string(f"LargeMsg{i}_content_long_and_detailed_conversation_turn ", 300)
        large_history.append({"role": role, "content": content})
        
    t_lore, t_memories, t_history = ContextBudgetManager.enforce_budget(
        lore_chunks=lore_chunks,
        memories=memories,
        history=large_history,
        total_budget=8000
    )
    
    lore_tokens = sum(len(l) // 2 for l in t_lore)
    mem_tokens = sum(len(m) // 2 for m in t_memories)
    hist_tokens = sum((len(h["content"]) // 2 + 10) for h in t_history)
    
    print(f"[+] Output Lore: {len(t_lore)} chunks ({lore_tokens} tokens / limit 1200)")
    print(f"[+] Output Memories: {len(t_memories)} chunks ({mem_tokens} tokens / limit 800)")
    print(f"[+] Output History: {len(t_history)} messages ({hist_tokens} tokens)")
    print(f"[+] Total Output Context: {lore_tokens + mem_tokens + hist_tokens} tokens")
    
    assert lore_tokens <= 1200, "Lore tokens must be <= 1200"
    assert mem_tokens <= 800, "Memory tokens must be <= 800"
    assert lore_tokens + mem_tokens + hist_tokens <= 7200, "Total context must be <= 7200 (8000 - 800)"
    assert t_history[-1]["content"].startswith("LargeMsg70"), "Should preserve the newest history (LargeMsg70)"
    print("  [✓] Pass: RAG Talk budget correctly enforced (Lore <= 1200, Memory <= 800, newest history kept).")

    # ----------------------------------------------------
    # TEST CASE 3: Loop Thinking (Budget = 12000 tokens)
    # ----------------------------------------------------
    print("\n" + "-" * 60)
    print("[*] Test Case 3: Loop Thinking (Budget = 12000 tokens, System Reserve = 800)")
    print("-" * 60)
    t_lore_lt, t_memories_lt, t_history_lt = ContextBudgetManager.enforce_budget(
        lore_chunks=lore_chunks,
        memories=memories,
        history=large_history,
        total_budget=12000
    )
    
    lore_tokens_lt = sum(len(l) // 2 for l in t_lore_lt)
    mem_tokens_lt = sum(len(m) // 2 for m in t_memories_lt)
    hist_tokens_lt = sum((len(h["content"]) // 2 + 10) for h in t_history_lt)
    
    print(f"[+] Output Lore: {len(t_lore_lt)} chunks ({lore_tokens_lt} tokens / limit 1500)")
    print(f"[+] Output Memories: {len(t_memories_lt)} chunks ({mem_tokens_lt} tokens / limit 1000)")
    print(f"[+] Output History: {len(t_history_lt)} messages ({hist_tokens_lt} tokens)")
    print(f"[+] Total Output Context: {lore_tokens_lt + mem_tokens_lt + hist_tokens_lt} tokens")
    
    assert lore_tokens_lt <= 1500, "Lore tokens must be <= 1500"
    assert mem_tokens_lt <= 1000, "Memory tokens must be <= 1000"
    assert lore_tokens_lt + mem_tokens_lt + hist_tokens_lt <= 11200, "Total context must be <= 11200 (12000 - 800)"
    assert len(t_history_lt) > len(t_history), "Loop thinking must retain more history messages due to larger budget"
    print(f"  [✓] Pass: Loop Thinking budget correctly enforced (Retained {len(t_history_lt)} messages vs {len(t_history)} in RAG mode).")

    print("\n" + "=" * 70)
    print("      ALL BUDGET ENFORCEMENT TEST CASES PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    main()
