import asyncio
import os
import sys
import uuid

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from app.domain.services.production_pipeline.semantic_router import SemanticRouter
from app.domain.services.production_pipeline.tool_router import LLMToolRouter
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from scratch.test_summarize import FastEmbedAdapter
from app.domain.services.production_pipeline.intent_classifier import ChatIntent

async def main():
    print("=" * 60)
    print("        TESTING MODULAR AGENT-LLM TOOL ROUTER WITH TIER 1")
    print("=" * 60)

    # Initialize components
    embedder = FastEmbedAdapter()
    llm = DeepSeekAdapter()
    
    # Initialize the routers
    router_t1 = SemanticRouter(embedder=embedder)
    router_t2 = LLMToolRouter(llm=llm, embedder=embedder)
    
    print("[*] Initializing Tier 1 semantic router anchors...")
    await router_t1.initialize()
    print("[*] Initializing Tier 2 semantic tool router anchors...")
    await router_t2.semantic_tool_router.initialize()
    print("[+] Registered Tier 2 tools:", [t.name for t in router_t2.tools])
    
    # Test cases for Tier 1 -> Tier 2 routing
    test_cases = [
        ("tra mạng xem bản cập nhật wuthering waves 1.3 có gì mới", "web_search"),
        ("tóm tắt nội dung cuộc trò chuyện của chúng ta nãy giờ đi em", "summarize_conversation_memory"),
        ("hiển thị bảng đo chỉ số cảm xúc của em đi", "get_emotion_report"),
        ("hôm nay trời đẹp quá chisa ơi", "none"),
        ("Tìm kiếm thông tin về ICTU đi gái", "web_search")
    ]
    
    for query, expected_tool in test_cases:
        print(f"\nQuery: '{query}'")
        vector = await embedder.embed_text(query)
        
        # Tier 1 classification
        intents = await router_t1.classify(query, vector)
        intent_values = [i.value for i in intents]
        print(f"Tier 1 Intents: {intent_values}")
        
        # Tier 2 routing (only if SYSTEM_ACTION is in intents)
        if ChatIntent.SYSTEM_ACTION in intents:
            tool_name, score = await router_t2.semantic_tool_router.route(vector)
            print(f"Tier 2 Matched Tool: '{tool_name}' (Score: {score:.4f}) | Expected: '{expected_tool}'")
        else:
            tool_name = "none"
            print(f"Tier 2 Bypassed (Not SYSTEM_ACTION) | Expected: '{expected_tool}'")
            
        if tool_name == expected_tool:
            print("  [✓] Pass")
        else:
            print("  [❌] FAIL")

if __name__ == "__main__":
    asyncio.run(main())
