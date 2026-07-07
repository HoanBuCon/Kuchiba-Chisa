import asyncio
import os
import sys

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from app.domain.services.rag import (
    rag_pipeline,
    memory_retriever,
    lore_retriever,
    ScoredMemory
)
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from scratch.test_summarize import FastEmbedAdapter
from app.domain.services.tools.web_search import WebSearchAgentTool

async def main():
    print("=" * 70)
    print("           TESTING MODULAR RAG PIPELINE & RETRIEVERS")
    print("=" * 70)

    # Initialize dependencies
    embedder = FastEmbedAdapter()
    llm = DeepSeekAdapter()
    web_search = WebSearchAgentTool()

    user_id = "00000000-0000-0000-0000-000000000000"
    query_text = "Em có thích pocky socola không Chisa?"
    print(f"\n[*] Query: '{query_text}'")
    query_vector = await embedder.embed_text(query_text)

    # Test Case 1: Test MemoryRetriever trực tiếp
    print("\n[*] 1. Test MemoryRetriever trực tiếp...")
    try:
        memories = await memory_retriever.retrieve_memories(
            collection="memories",
            query_vector=query_vector,
            user_id=user_id,
            current_emotion={"joy": 0.5, "trust": 0.5},
            limit=5,
            top_k=2
        )
        print(f"[+] Lấy thành công {len(memories)} memories")
        for m in memories:
            print(f"  - [{m.memory_tier}] Score: {m.final_score:.4f} | Text: {m.text_content[:60]}...")
        print("  [✓] Pass: MemoryRetriever hoạt động tốt!")
    except Exception as e:
        print(f"  [❌] Fail: Lỗi khi chạy MemoryRetriever: {str(e)}")

    # Test Case 2: Parent-child Lore Retrieval mới
    print("\n[*] 2. Test Parent-Child Lore Retrieval chuyên biệt...")
    try:
        lore_pc = await lore_retriever.retrieve_lore_parent_child(
            collection="character_lore",
            query_vector=query_vector,
            query_text=query_text,
            top_k=2,
            score_threshold=0.25
        )
        print(f"[+] Lấy thành công {len(lore_pc)} parent chunks:")
        for l in lore_pc:
            print(f"  - {l[:100]}...")
        print("  [✓] Pass: Lore Parent-Child hoạt động tốt!")
    except Exception as e:
        print(f"  [❌] Fail: Lỗi parent-child lore: {str(e)}")

    # Test Case 3: E2E retrieve_and_align (Bypass thinking loop)
    print("\n[*] 3. Test RAG Pipeline: retrieve_and_align (Bypass: small talk)...")
    try:
        context_st = await rag_pipeline.retrieve_and_align(
            session=None,
            user_id=user_id,
            user_message="hi em",
            query_vector=query_vector,
            cleaned_query="hi em",
            intents=["OTHER"],
            current_emotions={"joy": 0.5},
            history=[],
            llm=llm,
            embedder=embedder,
            web_search_tool=web_search,
            is_small_talk=True
        )
        print(f"[+] Is aligned: {context_st.is_aligned} | Reason: '{context_st.alignment_reason}'")
        print(f"[+] Thinking loops count: {len(context_st.thinking_steps)}")
        if context_st.is_aligned and len(context_st.thinking_steps) == 0:
            print("  [✓] Pass: Small talk bỏ qua alignment check & thinking loop thành công!")
        else:
            print("  [❌] Fail: Small talk không được bypass đúng cách!")
    except Exception as e:
        print(f"  [❌] Fail: Lỗi chạy small talk E2E: {str(e)}")

    # Test Case 4: E2E retrieve_and_align (Kích hoạt thinking loop - Loop Thinking)
    print("\n[*] 4. Test RAG Pipeline: retrieve_and_align (Kích hoạt Loop Thinking)...")
    unaligned_query = "Wuthering Waves update 1.4 có nhân vật nào mới ra mắt thế em?"
    print(f"[+] User query: '{unaligned_query}'")
    unaligned_vector = await embedder.embed_text(unaligned_query)
    
    try:
        context_loop = await rag_pipeline.retrieve_and_align(
            session=None,
            user_id=user_id,
            user_message=unaligned_query,
            query_vector=unaligned_vector,
            cleaned_query=unaligned_query,
            intents=["WORLD_LORE"],
            current_emotions={"joy": 0.5},
            history=[],
            llm=llm,
            embedder=embedder,
            web_search_tool=web_search,
            is_small_talk=False
        )
        print(f"[+] Is aligned: {context_loop.is_aligned} | Reason: '{context_loop.alignment_reason}'")
        print(f"[+] Thinking steps logged: {len(context_loop.thinking_steps)}")
        for step in context_loop.thinking_steps:
            print(f"  - Cycle {step['cycle']}:")
            print(f"    Reasoning: '{step['thinking']}'")
            print(f"    Search Query: '{step['search_query']}'")
            print(f"    Results Snippet: {step['search_result'][:80]}...")
        
        if len(context_loop.thinking_steps) > 0:
            print("  [✓] Pass: Loop Thinking (Iterative Web Search) được kích hoạt và chạy thành công!")
        else:
            print("  [❌] Fail: Lỗi, không kích hoạt Loop Thinking khi thiếu thông tin!")
    except Exception as e:
        print(f"  [❌] Fail: Lỗi chạy E2E loop thinking: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
