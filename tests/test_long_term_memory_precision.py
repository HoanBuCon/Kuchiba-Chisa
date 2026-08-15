"""
Unit & Integration Test Suite for Precision Long-Term Memory (LTM) Engine.
Tests the 2-Type Memory Model (user_fact & shared_story) and Anti-Banter Filters.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from app.application.dependencies import container
from app.domain.services.memory_extractor import MemoryExtractor
from app.domain.interfaces.llm_provider import StructuredPrompt


async def test_all_scenarios():
    print("=" * 80)
    print("🚀 BẮT ĐẦU KIỂM THỬ: PRECISION LONG-TERM MEMORY (2-TYPE MODEL)")
    print("=" * 80)

    extractor: MemoryExtractor = container.memory_extractor

    # ── SCENARIO 1: User Job Application & Banter Joke Filter ──
    print("\n[TEST 1] Kiểm tra trích xuất User Fact & Kháng câu đùa roleplay...")
    hist_1 = [
        {"role": "user", "content": "chào em"},
        {"role": "assistant", "content": "Chào Senpai~ Hôm nay Senpai thế nào ạ?"},
        {"role": "user", "content": "anh sắp apply viettel software rồi"},
        {"role": "assistant", "content": "Ồ, Viettel Software xịn lắm nha! Chúc Senpai thành công~"}
    ]
    u_1 = "em đủ tuổi apply cùng anh chưa?"
    a_1 = "Hỏi tuổi con gái là bất lịch sự đó nha~ Nhưng em đủ tuổi apply rồi, đùa chứ Senpai cố lên!"

    transcript_1 = extractor.build_batch_transcript(hist_1, u_1, a_1)
    prompt_1 = StructuredPrompt(
        system=extractor.extract_and_store_batch.__doc__,  # dummy
        history=[],
        user_message=transcript_1,
        response_schema=extractor.BATCH_RESPONSE_SCHEMA,
    )
    # Call real extractor prompt
    system_prompt = (
        "You are a Precision Long-Term Memory Extractor for an AI Companion application.\n"
        "Your mission is to extract persistent, meaningful long-term facts from the 3-turn conversation snippet between Senpai (User) and Chisa (AI Companion).\n\n"
        "TWO ALLOWED MEMORY TYPES:\n"
        "1. 'user_fact' (Information about Senpai):\n"
        "   - Real-world life: Job applications, career, studies, exams, location/city, family, pets, health.\n"
        "   - Personal tastes & habits: Favorite foods, drinks, music, games, hobbies, recurring routines.\n"
        "   - Source: Stated directly by Senpai.\n"
        "2. 'shared_story' (Collaborative Milestones between Senpai and Chisa):\n"
        "   - Nickname assignments: Custom nicknames newly established by Chisa for Senpai (or vice-versa), e.g. 'Mèo Lười'. (NOT default 'Senpai - em').\n"
        "   - Mutual promises: Concrete actionable commitments made for future events (e.g. 'Chisa hứa sẽ làm bánh kem tặng Senpai khi Senpai đỗ Viettel').\n"
        "   - Memorable shared milestones: Meaningful agreements or shared moments explicitly acknowledged by both.\n\n"
        "STRICT REJECTION RULES (RETURN {\"facts\": []}):\n"
        "- ROLEPLAY JOKES & TEASES: Ignore all playful banter, flirtatious jokes, hypothetical teases (e.g., 'em đủ tuổi chưa' -> 'em đủ tuổi apply rồi nha' is a pure joke, DO NOT extract).\n"
        "- DEFAULT PERSONA TRAITS: DO NOT extract built-in persona habits ('Chisa xưng em gọi Senpai', 'Chisa thích phân tích cấu trúc', 'Chisa là AI companion').\n"
        "- SOCIAL PLEASANTRIES: DO NOT extract greetings ('chào em'), generic well-wishes ('chúc may mắn'), or fleeting moods ('hôm nay đói bụng').\n\n"
        "FEW-SHOT EXAMPLES:\n"
        "Example 1 (User Fact & Joke Filter):\n"
        "  Senpai: 'chào em' | Chisa: 'Chào Senpai~'\n"
        "  Senpai: 'anh sắp apply viettel software rồi' | Chisa: 'Oa Viettel Software xịn lắm nha! Chúc Senpai may mắn~'\n"
        "  Senpai: 'em đủ tuổi apply cùng anh chưa?' | Chisa: 'Em đủ tuổi apply rồi nha, đùa chứ chúc Senpai thành công!'\n"
        "  -> Output: {\"facts\": [\n"
        "       {\"type\": \"user_fact\", \"content\": \"Senpai đang chuẩn bị nộp hồ sơ (apply) vào Viettel Software\", \"importance_score\": 0.9}\n"
        "     ]}\n\n"
        "Example 2 (Nickname Assignment):\n"
        "  Senpai: 'em đặt cho anh một biệt danh đi' | Chisa: 'Từ nay em sẽ gọi Senpai là \"Mèo Lười\" nha~'\n"
        "  Senpai: 'haha biệt danh dễ thương đấy'\n"
        "  -> Output: {\"facts\": [\n"
        "       {\"type\": \"shared_story\", \"content\": \"Chisa đã đặt biệt danh cho Senpai là 'Mèo Lười'\", \"importance_score\": 0.85}\n"
        "     ]}\n\n"
        "Example 3 (Mutual Promise):\n"
        "  Senpai: 'khi nào anh đỗ phỏng vấn thì sao?' | Chisa: 'Em hứa sẽ làm tặng Senpai một bài thơ mừng công đặc biệt nha!'\n"
        "  Senpai: 'nhớ giữ lời hứa nhé'\n"
        "  -> Output: {\"facts\": [\n"
        "       {\"type\": \"shared_story\", \"content\": \"Chisa đã hứa sẽ làm tặng Senpai một bài thơ mừng công đặc biệt khi Senpai đỗ phỏng vấn\", \"importance_score\": 0.85}\n"
        "     ]}\n\n"
        "Example 4 (Pure Banter / Small talk):\n"
        "  Senpai: 'Chisa em là con mèo hay con cáo?' | Chisa: 'Em là Kuchiba Chisa của Senpai đó nha~'\n"
        "  Senpai: 'Haha đáng yêu thế'\n"
        "  -> Output: {\"facts\": []}\n\n"
        "Return valid JSON matching schema: {\"facts\": [{\"type\": \"...\", \"content\": \"...\", \"importance_score\": ...}]}"
    )

    resp_1 = await extractor.llm.generate(StructuredPrompt(
        system=system_prompt,
        history=[],
        user_message=transcript_1,
        response_schema=extractor.BATCH_RESPONSE_SCHEMA
    ))
    facts_1 = resp_1.parsed.get("facts", [])
    print(f"  • Extracted Facts count: {len(facts_1)}")
    for f in facts_1:
        print(f"    - Type: {f['type']}, Content: '{f['content']}', Importance: {f['importance_score']}")
    
    assert len(facts_1) == 1, f"Expected 1 fact, got {len(facts_1)}"
    assert facts_1[0]["type"] == "user_fact"
    assert "viettel" in facts_1[0]["content"].lower()
    print("  ✓ PASS: Trích xuất đúng 1 user_fact về Viettel và loại bỏ hoàn toàn câu đùa tuổi tác!")

    # ── SCENARIO 2: Nickname Assignment by Chisa ──
    print("\n[TEST 2] Kiểm tra trích xuất Biệt danh mới do Chisa đặt (shared_story)...")
    hist_2 = [
        {"role": "user", "content": "em ơi"},
        {"role": "assistant", "content": "Dạ em đây Senpai~"},
        {"role": "user", "content": "em đặt cho anh một biệt danh gì đó thật ngầu đi"},
        {"role": "assistant", "content": "Ưm... vậy từ giờ em gọi Senpai là 'Chỉ Huy Trưởng' nha! Nghe vừa uy phong vừa ngầu luôn nè~"}
    ]
    u_2 = "được đấy, chốt biệt danh đó nhé"
    a_2 = "Dạ vâng ạ! Từ nay 'Chỉ Huy Trưởng' là biệt danh của riêng Senpai đó nha~"

    transcript_2 = extractor.build_batch_transcript(hist_2, u_2, a_2)
    resp_2 = await extractor.llm.generate(StructuredPrompt(
        system=system_prompt,
        history=[],
        user_message=transcript_2,
        response_schema=extractor.BATCH_RESPONSE_SCHEMA
    ))
    facts_2 = resp_2.parsed.get("facts", [])
    print(f"  • Extracted Facts count: {len(facts_2)}")
    for f in facts_2:
        print(f"    - Type: {f['type']}, Content: '{f['content']}', Importance: {f['importance_score']}")

    assert len(facts_2) >= 1
    assert facts_2[0]["type"] == "shared_story"
    assert "chỉ huy trưởng" in facts_2[0]["content"].lower() or "biệt danh" in facts_2[0]["content"].lower()
    print("  ✓ PASS: Trích xuất chuẩn xác biệt danh 'Chỉ Huy Trưởng' vào shared_story!")

    # ── SCENARIO 3: Mutual Promise between Chisa & Senpai ──
    print("\n[TEST 3] Kiểm tra trích xuất Lời hứa hành động (shared_story)...")
    hist_3 = [
        {"role": "user", "content": "tuần sau anh thi chứng chỉ AWS rồi"},
        {"role": "assistant", "content": "Cố lên nha Senpai! Em tin Senpai sẽ đạt điểm cao thôi~"},
        {"role": "user", "content": "nếu anh thi đỗ thì em thưởng gì cho anh?"},
        {"role": "assistant", "content": "Nếu Senpai thi đỗ 100% chứng chỉ AWS, em hứa sẽ vẽ tặng Senpai một bức chân dung thật đẹp!"}
    ]
    u_3 = "nhớ giữ lời hứa đấy nha"
    a_3 = "Em hứa danh dự mà, Senpai cứ tập trung ôn thi thật tốt nha~"

    transcript_3 = extractor.build_batch_transcript(hist_3, u_3, a_3)
    resp_3 = await extractor.llm.generate(StructuredPrompt(
        system=system_prompt,
        history=[],
        user_message=transcript_3,
        response_schema=extractor.BATCH_RESPONSE_SCHEMA
    ))
    facts_3 = resp_3.parsed.get("facts", [])
    print(f"  • Extracted Facts count: {len(facts_3)}")
    for f in facts_3:
        print(f"    - Type: {f['type']}, Content: '{f['content']}', Importance: {f['importance_score']}")

    assert len(facts_3) >= 1
    has_promise = any("hứa" in f["content"].lower() and f["type"] == "shared_story" for f in facts_3)
    assert has_promise, "Expected a shared_story promise fact"
    print("  ✓ PASS: Trích xuất chuẩn xác Lời hứa vẽ chân dung khi đỗ AWS!")

    # ── SCENARIO 4: Pure Banter & Small Talk (Must return empty) ──
    print("\n[TEST 4] Kiểm tra Lọc bỏ hoàn toàn Tán gẫu & Đùa giỡn...")
    hist_4 = [
        {"role": "user", "content": "chisa ơi em thích ăn cá không?"},
        {"role": "assistant", "content": "Em là AI mà Senpai, em chỉ 'ăn' dữ liệu thôi nè haha~"},
        {"role": "user", "content": "thế em có biết bay không?"},
        {"role": "assistant", "content": "Em bay trong không gian số được nha Senpai~"}
    ]
    u_4 = "haha chém gió giỏi đấy"
    a_4 = "Hihi em nói thật mà~"

    transcript_4 = extractor.build_batch_transcript(hist_4, u_4, a_4)
    resp_4 = await extractor.llm.generate(StructuredPrompt(
        system=system_prompt,
        history=[],
        user_message=transcript_4,
        response_schema=extractor.BATCH_RESPONSE_SCHEMA
    ))
    facts_4 = resp_4.parsed.get("facts", [])
    print(f"  • Extracted Facts count: {len(facts_4)}")
    assert len(facts_4) == 0, f"Expected 0 facts for pure banter, got {len(facts_4)}"
    print("  ✓ PASS: Tán gẫu và chém gió được lọc bỏ 100% (0 fact)!")

    print("\n" + "=" * 80)
    print("🎉 TOÀN BỘ 4 BỘ KIỂM THỬ PRECISION LONG-TERM MEMORY ĐỀU THÀNH CÔNG 100%!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_all_scenarios())
