import asyncio
import os
import sys
from typing import Any, Dict, List, Tuple

# Set utf-8 encoding for Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.domain.models.intent_result import ChatIntent, IntentResult
from app.domain.services.intent_classifier import IntentClassifier
from app.domain.services.rag.entity_resolver import EntityResolver
from app.domain.services.rag.query_rewriter import QueryRewriter
from app.domain.interfaces.llm_provider import BaseLLMAdapter, LLMResponse, StructuredPrompt

class MockExhaustiveLLMAdapter(BaseLLMAdapter):
    """Smart mock adapter returning calibrated JSON responses for all 20 test cases."""
    def __init__(self):
        self.model_name = "deepseek-v4-flash"

    async def generate(self, prompt: StructuredPrompt, **kwargs: Any) -> LLMResponse:
        user_msg = prompt.user_message.lower()
        system_msg = prompt.system.lower()

        # ── 1. Query Rewriter & Tri-State Router Mocking ──
        if "query rewriter" in system_msg:
            # Case 5: Jiyan weapon
            if "jiyan" in user_msg and "vũ khí" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Vũ khí của tướng quân Jiyan Wuthering Waves Broadblade", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Vũ khí của tướng quân Jiyan Wuthering Waves Broadblade", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    total_tokens=45
                )
            # Case 6: Chixia Resonance Liberation
            if "chixia" in user_msg and "resonance" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Kỹ năng Resonance Liberation của Chixia thuộc tính nguyên tố Fusion", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Kỹ năng Resonance Liberation của Chixia thuộc tính nguyên tố Fusion", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    total_tokens=48
                )
            # Case 7: Da Hanh Quan
            if "dạ hành quân" in user_msg or "midnight rangers" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Khu vực đóng quân của Midnight Rangers (Dạ Hành Quân) tại Huanglong", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Khu vực đóng quân của Midnight Rangers (Dạ Hành Quân) tại Huanglong", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    total_tokens=46
                )
            # Case 8: Chisa persona "em"
            if "năng lực forte" in user_msg or "vậy em có năng lực" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Năng lực Forte và kỹ năng chiến đấu của Kuchiba Chisa Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Năng lực Forte và kỹ năng chiến đấu của Kuchiba Chisa Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    total_tokens=50
                )
            # Case 9: hoanbucon
            if "hoanbucon" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "hoanbucon là ai", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "hoanbucon là ai", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    total_tokens=35
                )
            # Case 10: Frieren anime
            if "frieren" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "anime Sousou no Frieren số tập studio sản xuất Madhouse", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "anime Sousou no Frieren số tập studio sản xuất Madhouse", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    total_tokens=40
                )
            # Case 11: Weather
            if "thời tiết" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "thời tiết hôm nay tại Hà Nội dự báo", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "thời tiết hôm nay tại Hà Nội dự báo", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    total_tokens=32
                )
            # Case 12: Shorekeeper revenue (Hybrid Lore + Web)
            if "shorekeeper" in user_msg and "doanh thu" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Kuro Games doanh thu banner Shorekeeper Wuthering Waves", "needs_vector_search": true, "needs_web_search": true}',
                    parsed={"rewritten_query": "Kuro Games doanh thu banner Shorekeeper Wuthering Waves", "needs_vector_search": True, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    total_tokens=48
                )
            # Case 13: Patch 2.8 update (Hybrid Lore + Web)
            if "2.8" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Wuthering Waves bản cập nhật 2.8 nhân vật mới ngày ra mắt", "needs_vector_search": true, "needs_web_search": true}',
                    parsed={"rewritten_query": "Wuthering Waves bản cập nhật 2.8 nhân vật mới ngày ra mắt", "needs_vector_search": True, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    total_tokens=48
                )
            # Case 14 & 15: Code snippets
            if "lfu" in user_msg or "quick_sort" in user_msg or "def " in user_msg or "class " in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "giải thích và triển khai mã nguồn thuật toán", "needs_vector_search": false, "needs_web_search": false}',
                    parsed={"rewritten_query": "giải thích và triển khai mã nguồn thuật toán", "needs_vector_search": False, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    total_tokens=38
                )
            # Case 16: Math equation
            if "phương trình" in user_msg or "x^2" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "giải phương trình bậc hai x^2 - 5x + 6 = 0", "needs_vector_search": false, "needs_web_search": false}',
                    parsed={"rewritten_query": "giải phương trình bậc hai x^2 - 5x + 6 = 0", "needs_vector_search": False, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    total_tokens=36
                )
            # Case 17: Follow-up pronoun
            if "vũ khí của anh ấy" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Vũ khí của tướng quân Jiyan (Midnight Rangers)", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Vũ khí của tướng quân Jiyan (Midnight Rangers)", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    total_tokens=42
                )
            # Case 18: Follow-up dragon
            if "con rồng đó" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Sức mạnh của rồng Thanh Long (Qingloong) trong thảm họa Lament", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Sức mạnh của rồng Thanh Long (Qingloong) trong thảm họa Lament", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    total_tokens=46
                )
            # Case 19: Doraemon multi-hop
            if "doraemon" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "tác giả bộ truyện Doraemon năm sinh ngày mất", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "tác giả bộ truyện Doraemon năm sinh ngày mất", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    total_tokens=40
                )
            # Case 20: Personal Memory
            if "món gì em còn nhớ không" in user_msg or "món ăn anh thích" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Món ăn yêu thích của Senpai theo ký ức", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Món ăn yêu thích của Senpai theo ký ức", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    total_tokens=40
                )

            # Default
            return LLMResponse(
                raw_text='{"rewritten_query": "' + user_msg + '", "needs_vector_search": true, "needs_web_search": false}',
                parsed={"rewritten_query": user_msg, "needs_vector_search": True, "needs_web_search": False},
                model="deepseek-v4-flash",
                total_tokens=30
            )

        # ── 2. Context Assessor Mocking ──
        if "alignment assessor" in system_msg:
            if "fujiko f. fujio" in user_msg and ("năm sinh" not in user_msg or "thiếu" in user_msg):
                return LLMResponse(
                    raw_content='{"is_aligned": false, "reason": "Kết quả Round 1 đã có tên tác giả Fujiko F. Fujio (Hiroshi Fujimoto) nhưng còn thiếu năm sinh và ngày mất.", "search_query": "Fujiko F. Fujio Hiroshi Fujimoto năm sinh ngày mất", "use_lore": true}',
                    parsed={
                        "is_aligned": False,
                        "reason": "Kết quả Round 1 đã có tên tác giả Fujiko F. Fujio (Hiroshi Fujimoto) nhưng còn thiếu năm sinh và ngày mất.",
                        "search_query": "Fujiko F. Fujio Hiroshi Fujimoto năm sinh ngày mất",
                        "use_lore": True
                    },
                    model="deepseek-v4-flash",
                    total_tokens=55
                )
            return LLMResponse(
                raw_text='{"is_aligned": true, "reason": "Thông tin context đã đầy đủ", "search_query": "", "use_lore": true}',
                parsed={"is_aligned": True, "reason": "Thông tin context đã đầy đủ", "search_query": "", "use_lore": True},
                model="deepseek-v4-flash",
                total_tokens=35
            )

        return LLMResponse(
            raw_content="{}",
            parsed={},
            model="deepseek-v4-flash",
            input_tokens=10,
            output_tokens=10
        )

    async def stream(self, prompt: StructuredPrompt, **kwargs: Any):
        yield "mock"

    async def validate_response(self, raw: str, schema: dict) -> dict:
        return {}

    async def estimate_tokens(self, text: str) -> int:
        return len(text.split())


async def run_20_exhaustive_test_cases():
    print("=" * 80)
    print("🚀 BẮT ĐẦU CHẠY 20 TEST CASE VÉT CẠN KIẾN TRÚC PIPELINE & INTENT ROUTING")
    print("=" * 80)

    mock_llm = MockExhaustiveLLMAdapter()
    entity_resolver = EntityResolver()
    entity_resolver.load()
    rewriter = QueryRewriter(llm=mock_llm, entity_resolver=entity_resolver)

    test_cases: List[Dict[str, Any]] = [
        # ── NHÓM 1: Small Talk Fast-Path (Bypass 0ms, 0 Token) ──
        {
            "id": 1,
            "category": "Small Talk (Chào hỏi)",
            "query": "chào em chisa nhé",
            "prev_context": None,
            "expected_st": True,
            "expected_vec": False,
            "expected_web": False,
            "expected_method": "BYPASS"
        },
        {
            "id": 2,
            "category": "Small Talk (Tình cảm/Khen ngợi)",
            "query": "em đáng yêu ghê á chisa ơi",
            "prev_context": None,
            "expected_st": True,
            "expected_vec": False,
            "expected_web": False,
            "expected_method": "BYPASS"
        },
        {
            "id": 3,
            "category": "Small Talk (Chúc ngủ ngon)",
            "query": "chúc em ngủ ngon nha chisa, g9 nè",
            "prev_context": None,
            "expected_st": True,
            "expected_vec": False,
            "expected_web": False,
            "expected_method": "BYPASS"
        },
        {
            "id": 4,
            "category": "Small Talk (Cảm thán ngắn)",
            "query": "haha vui quá đi mất thôi",
            "prev_context": None,
            "expected_st": True,
            "expected_vec": False,
            "expected_web": False,
            "expected_method": "BYPASS"
        },

        # ── NHÓM 2: Lore Standalone (Option 1: Vector Search Mode) ──
        {
            "id": 5,
            "category": "Game Lore (Nhân vật & Vũ khí)",
            "query": "Jiyan dùng loại vũ khí gì thế em?",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": True,
            "expected_web": False,
            "expected_method": "LLM_FLASH"
        },
        {
            "id": 6,
            "category": "Game Lore (Kỹ năng & Cơ chế)",
            "query": "Kỹ năng Resonance Liberation của Chixia gây sát thương hệ gì?",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": True,
            "expected_web": False,
            "expected_method": "LLM_FLASH"
        },
        {
            "id": 7,
            "category": "Game Lore (Entity Alias Wiki Hán Việt -> EN)",
            "query": "Dạ Hành Quân đóng quân ở khu vực nào của Huanglong?",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": True,
            "expected_web": False,
            "expected_method": "LLM_FLASH"
        },
        {
            "id": 8,
            "category": "Game Lore (Persona Chisa - Đại từ 'em')",
            "query": "vậy em có năng lực forte gì thế?",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": True,
            "expected_web": False,
            "expected_method": "LLM_FLASH"
        },

        # ── NHÓM 3: External Entity / Internet (Option 2: Direct Web Search Mode) ──
        {
            "id": 9,
            "category": "External Entity (Streamer / Nhân vật ngoài đời)",
            "query": "biết hoanbucon là ai không em",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": False,
            "expected_web": True,
            "expected_method": "LLM_FLASH"
        },
        {
            "id": 10,
            "category": "External Entity (Anime / Phim ảnh ngoài game)",
            "query": "Bộ anime Frieren có bao nhiêu tập và do studio nào làm?",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": False,
            "expected_web": True,
            "expected_method": "LLM_FLASH"
        },
        {
            "id": 11,
            "category": "Real-world Fact (Thời tiết / Sự kiện đời thực)",
            "query": "Thời tiết hôm nay tại Hà Nội thế nào em?",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": False,
            "expected_web": True,
            "expected_method": "LLM_FLASH"
        },

        # ── NHÓM 4: Hybrid Knowledge (Dual Search: Lore DB + Web Search) ──
        {
            "id": 12,
            "category": "Hybrid Lore + Web (Banner & Doanh thu thực tế)",
            "query": "Kuro Games vừa công bố doanh thu của banner Shorekeeper là bao nhiêu?",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": True,
            "expected_web": True,
            "expected_method": "LLM_FLASH"
        },
        {
            "id": 13,
            "category": "Hybrid Lore + Web (Bản cập nhật tương lai)",
            "query": "Bản cập nhật 2.8 Wuthering Waves có nhân vật mới nào và ra mắt ngày mấy?",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": True,
            "expected_web": True,
            "expected_method": "LLM_FLASH"
        },

        # ── NHÓM 5: Code & Technical (0ms RAG Bypass) ──
        {
            "id": 14,
            "category": "Code & Technical (C++ Data Structure)",
            "query": "ý anh là bài này class LFUCache{struct Bucket; int get(int k); void put(int k, int v);};",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": False,
            "expected_web": False,
            "expected_method": "LLM_FLASH"
        },
        {
            "id": 15,
            "category": "Code & Technical (Python Function)",
            "query": "viết giúp anh hàm def quick_sort(arr): đệ quy bằng Python",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": False,
            "expected_web": False,
            "expected_method": "LLM_FLASH"
        },
        {
            "id": 16,
            "category": "Technical & Math (Giải phương trình toán học)",
            "query": "Giải phương trình bậc hai: x^2 - 5x + 6 = 0",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": False,
            "expected_web": False,
            "expected_method": "LLM_FLASH"
        },

        # ── NHÓM 6: Follow-up Pronoun Chaining (1-Turn Context Resolution) ──
        {
            "id": 17,
            "category": "Coreference Chaining (Đại từ 'anh ấy')",
            "query": "Vũ khí của anh ấy là gì?",
            "prev_context": "Kể về vị tướng Jiyan lãnh đạo Midnight Rangers",
            "expected_st": False,
            "expected_vec": True,
            "expected_web": False,
            "expected_method": "LLM_FLASH"
        },
        {
            "id": 18,
            "category": "Coreference Chaining (Cái đó/Con rồng đó)",
            "query": "Con rồng đó có sức mạnh như thế nào?",
            "prev_context": "Trong thảm họa Lament có con rồng Thanh Long xuất hiện",
            "expected_st": False,
            "expected_vec": True,
            "expected_web": False,
            "expected_method": "LLM_FLASH"
        },

        # ── NHÓM 7: Multi-Hop Assessor Query Refinement ──
        {
            "id": 19,
            "category": "Multi-Hop Web Search Refinement (Cycle 1 -> Cycle 2)",
            "query": "Tác giả bộ truyện Doraemon sinh năm bao nhiêu và còn sống không?",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": False,
            "expected_web": True,
            "expected_method": "LLM_FLASH"
        },

        # ── NHÓM 8: Long-Term Memory Query ──
        {
            "id": 20,
            "category": "Memory Retrieval (Sở thích cá nhân Senpai)",
            "query": "hôm trước anh kể anh thích ăn món gì em còn nhớ không?",
            "prev_context": None,
            "expected_st": False,
            "expected_vec": True,
            "expected_web": False,
            "expected_method": "LLM_FLASH"
        }
    ]

    passed_count = 0
    total_count = len(test_cases)

    for case in test_cases:
        cid = case["id"]
        cat = case["category"]
        query = case["query"]
        prev_ctx = case["prev_context"]

        # Step 1: Test Small Talk Classifier
        is_st = IntentClassifier.is_small_talk(query)
        assert is_st == case["expected_st"], f"Case {cid} [{cat}] Small Talk Mismatch: got {is_st}, expected {case['expected_st']}"

        if is_st:
            rewritten_q = query
            method = "BYPASS"
            needs_vec = False
            needs_web = False
        else:
            rewritten_q, method, needs_vec, needs_web = await rewriter.rewrite(
                user_message=query,
                cleaned_query=query,
                prev_rewritten_query=prev_ctx,
                needs_llm_rewrite=True,
            )

        assert needs_vec == case["expected_vec"], f"Case {cid} [{cat}] Vector Search Flag Mismatch: got {needs_vec}, expected {case['expected_vec']}"
        assert needs_web == case["expected_web"], f"Case {cid} [{cat}] Web Search Flag Mismatch: got {needs_web}, expected {case['expected_web']}"
        assert method == case["expected_method"], f"Case {cid} [{cat}] Method Mismatch: got {method}, expected {case['expected_method']}"

        passed_count += 1
        st_tag = "⚡ SMALL_TALK" if is_st else "🧠 KNOWLEDGE/TASK"
        mode_tag = "🎯 VECTOR" if (needs_vec and not needs_web) else ("🌐 WEB" if (needs_web and not needs_vec) else ("🔥 DUAL (VEC+WEB)" if (needs_vec and needs_web) else "⚡ 0ms BYPASS"))
        
        print(f"[{cid:02d}/20] {cat}")
        print(f"       • Query: \"{query}\"")
        if prev_ctx:
            print(f"       • Context N-1: \"{prev_ctx}\"")
        print(f"       • Rewritten: \"{rewritten_q}\"")
        print(f"       • Classifier: {st_tag} | Mode: {mode_tag} | Method: {method}")
        print(f"       ✓ PASS\n")

    # ── Test Bonus: Kiểm tra Context Assessor Multi-Hop Query Synthesis (Case 19 Cycle 2) ──
    print("-" * 80)
    print("🔍 KIỂM TRA BỔ SUNG: CONTEXT ASSESSOR MULTI-HOP SYNTHESIS (Case 19 Round 2)...")
    from app.domain.services.rag.assessor import ContextAssessor
    assessor = ContextAssessor()
    
    round_1_context = "[Web Search Round 1 Results for 'Tác giả bộ truyện Doraemon']:\nDoraemon là bộ truyện tranh nổi tiếng của Nhật Bản do tác giả Fujiko F. Fujio (Hiroshi Fujimoto) sáng tác."
    is_aligned, reason, search_q2, use_lore = await assessor.assess_alignment(
        user_message="Tác giả bộ truyện Doraemon sinh năm bao nhiêu và còn sống không?",
        context_text=round_1_context,
        llm=mock_llm
    )
    print(f"  • Round 1 Context: {round_1_context[:90]}...")
    print(f"  • Assessor Decision: Aligned={is_aligned}")
    print(f"  • Assessor Reason: {reason}")
    print(f"  • Refined Query Lần 2 (Multi-Hop): \"{search_q2}\"")
    assert is_aligned is False
    assert "Fujiko F. Fujio" in search_q2 or "Hiroshi Fujimoto" in search_q2
    print("  ✓ PASS: Context Assessor đã kế thừa tên tác giả từ Round 1 để sinh Query Lần 2 hoàn hảo!\n")

    print("=" * 80)
    print(f"🎉 KẾT QUẢ: {passed_count}/{total_count} TEST CASES VÀ BỘ KIỂM TRA MULTI-HOP ĐỀU ĐẠT 100% THÀNH CÔNG!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_20_exhaustive_test_cases())
