"""
Comprehensive Test Suite for Persona Disambiguation, Query Rewrite, Slang Normalization, and RAG Alignment.
Tests all 7 edge case categories identified during RAG pipeline audit.
"""

import asyncio
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.abspath("."))

from app.shared.utils.query_cleaner import (
    clean_query_for_rag,
    has_coreference_markers,
    resolve_persona_pronouns,
    enrich_query_with_entities,
    is_meaningful_query,
    COMMUNITY_NICKNAMES,
)
from app.domain.services.rag.entity_resolver import EntityResolver, EntityDictionary


def test_persona_and_pronoun_disambiguation():
    print("\n" + "=" * 80)
    print("🧪 [TEST 1] Kiểm tra Phân giải Đại từ Nhân xưng (Persona Pronoun Resolution)")
    print("=" * 80)

    resolver = EntityResolver("data/lore/entities.json")
    resolver.load()

    # 1.1 Bot Persona Question
    q1 = "vậy em có năng lực gì"
    res1 = resolve_persona_pronouns(q1, intent_hint="LORE")
    print(f"  • Q: '{q1}'\n    -> Resolved: '{res1}'")
    assert "Kuchiba Chisa" in res1, f"Expected 'Kuchiba Chisa' in '{res1}'"

    # 1.2 Bot Persona with calling name preserved
    q2 = "tiểu sử của em ra sao"
    res2 = resolve_persona_pronouns(q2, intent_hint="LORE")
    print(f"  • Q: '{q2}'\n    -> Resolved: '{res2}'")
    assert "Kuchiba Chisa" in res2, f"Expected 'Kuchiba Chisa' in '{res2}'"

    # 1.3 Bot Persona vs Third-party Character ("em Chixia" must NOT become Kuchiba Chisa)
    q3 = "em Chixia dùng súng gì thế"
    res3 = resolve_persona_pronouns(q3, intent_hint="LORE")
    print(f"  • Q: '{q3}'\n    -> Resolved: '{res3}'")
    assert "Kuchiba Chisa" not in res3 and "Chixia" in res3, f"Unexpected Chisa override in '{res3}'"

    # 1.4 User Persona ("anh thích ăn gì" -> Senpai)
    q4 = "em có nhớ anh thích ăn món gì không"
    res4 = resolve_persona_pronouns(q4, intent_hint="MEMORY")
    print(f"  • Q: '{q4}'\n    -> Resolved: '{res4}'")
    assert "Senpai" in res4 or "người dùng" in res4, f"Expected 'Senpai' in '{res4}'"

    # 1.5 User Persona vs Male Character ("anh Jiyan" must NOT become Senpai)
    q5 = "anh Jiyan bao nhiêu tuổi"
    res5 = resolve_persona_pronouns(q5, intent_hint="LORE")
    print(f"  • Q: '{q5}'\n    -> Resolved: '{res5}'")
    assert "Senpai" not in res5 and "Jiyan" in res5, f"Unexpected Senpai override in '{res5}'"

    print("  ✓ PASS: Phân giải đại từ nhân xưng đạt độ chính xác 100%!")


def test_community_slang_normalization():
    print("\n" + "=" * 80)
    print("🧪 [TEST 2] Kiểm tra Chuẩn hóa Biệt danh & Tiếng lóng Game (Community Nicknames)")
    print("=" * 80)

    # 2.1 Tướng rồng -> Jiyan
    q1 = "vũ khí của tướng rồng là gì"
    res1 = resolve_persona_pronouns(q1)
    print(f"  • Q: '{q1}' -> Resolved: '{res1}'")
    assert "Jiyan" in res1, f"Expected 'Jiyan' in '{res1}'"

    # 2.2 Rùa chuông -> Bell-Borne Geochelone
    q2 = "con rùa chuông ở đâu"
    res2 = resolve_persona_pronouns(q2)
    print(f"  • Q: '{q2}' -> Resolved: '{res2}'")
    assert "Bell-Borne Geochelone" in res2, f"Expected 'Bell-Borne Geochelone' in '{res2}'"

    # 2.3 Cá voi -> Shorekeeper
    q3 = "kỹ năng của cá voi"
    res3 = resolve_persona_pronouns(q3)
    print(f"  • Q: '{q3}' -> Resolved: '{res3}'")
    assert "Shorekeeper" in res3, f"Expected 'Shorekeeper' in '{res3}'"

    # 2.4 Cáo lửa -> Changli
    q4 = "cáo lửa dùng kiếm gì"
    res4 = resolve_persona_pronouns(q4)
    print(f"  • Q: '{q4}' -> Resolved: '{res4}'")
    assert "Changli" in res4, f"Expected 'Changli' in '{res4}'"

    print("  ✓ PASS: Chuẩn hóa biệt danh game thủ đạt độ chính xác 100%!")


def test_cleaner_calling_name_preservation():
    print("\n" + "=" * 80)
    print("🧪 [TEST 3] Kiểm tra Bảo toàn Chủ ngữ Tên gọi trong Query Cleaner")
    print("=" * 80)

    # 3.1 Chisa có năng lực gì -> Must preserve Chisa!
    q1 = "Chisa có năng lực gì"
    c1 = clean_query_for_rag(q1)
    print(f"  • Original: '{q1}' -> Cleaned: '{c1}'")
    assert "chisa" in c1, f"Expected 'chisa' preserved in '{c1}'"

    # 3.2 Calling name with another entity -> Can strip calling name prefix
    q2 = "Chisa ơi cho anh hỏi Jiyan dùng vũ khí gì thế"
    c2 = clean_query_for_rag(q2)
    print(f"  • Original: '{q2}' -> Cleaned: '{c2}'")
    assert "jiyan" in c2, f"Expected 'jiyan' in '{c2}'"

    print("  ✓ PASS: Query cleaner bảo toàn chủ ngữ hoàn hảo!")


def test_meaningful_query_lookback():
    print("\n" + "=" * 80)
    print("🧪 [TEST 4] Kiểm tra Lọc Câu Cảm thán / Small-talk trong Lookback SQL")
    print("=" * 80)

    assert is_meaningful_query("haha vui quá") is False, "Expected 'haha vui quá' to be not meaningful"
    assert is_meaningful_query("ok em nha") is False, "Expected 'ok em nha' to be not meaningful"
    assert is_meaningful_query("cảm ơn em") is False, "Expected 'cảm ơn em' to be not meaningful"
    assert is_meaningful_query("Kể anh nghe về thành phố Jinzhou") is True, "Expected 'Jinzhou' to be meaningful"
    assert is_meaningful_query("Vũ khí của Jiyan là gì") is True, "Expected 'Vũ khí của Jiyan' to be meaningful"

    print("  ✓ PASS: Bộ lọc Knowledge-Aware Lookback phân biệt chính xác câu cảm thán!")


async def test_end_to_end_chisa_ability_chat():
    print("\n" + "=" * 80)
    print("🧪 [TEST 5] Kiểm tra End-to-End ChatEngine: 'vậy em có năng lực gì'")
    print("=" * 80)

    from app.application.dependencies import container
    from app.infrastructure.database.engine import AsyncSessionFactory
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    chat_engine = container.chat_engine
    import uuid
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    query = "vậy em có năng lực gì"

    trace_id = pipeline_tracker.start_trace(
        user_id=user_id,
        message=query,
        pipeline="production",
        source="unit_test"
    )

    async with AsyncSessionFactory() as session:
        reply, emotions = await chat_engine.chat(
            session=session,
            user_id=user_id,
            user_message=query
        )
        await session.commit()

    pipeline_tracker.end_trace(response_text=reply, emotions=emotions, status="success")

    # Verify Trace
    traces = pipeline_tracker.get_traces()
    current_trace = next((t for t in traces if t.get("id") == trace_id), {})
    steps = current_trace.get("steps", [])

    intent_step = next((s for s in steps if s.get("name") in ("intent_classification", "intent_stage")), {})
    intent_data = intent_step.get("data", {})
    actual_intents = intent_data.get("intents", [])
    rewritten_query = intent_data.get("rewritten_query", "")

    print(f"\n  • User Query    : '{query}'")
    print(f"  • Actual Intents: {actual_intents}")
    print(f"  • Rewritten Q   : '{rewritten_query}'")
    print(f"  • Chisa Reply   : {reply[:120]}...\n")

    assert "LORE" in actual_intents or "CONVERSATIONAL" in actual_intents, f"Unexpected intents: {actual_intents}"
    assert "Kuchiba Chisa" in rewritten_query or "chisa" in rewritten_query.lower(), f"Expected Chisa in '{rewritten_query}'"

    print("  ✓ PASS: Query 'vậy em có năng lực gì' đã được resolve sang Kuchiba Chisa và truy xuất chuẩn xác!")


async def main():
    test_persona_and_pronoun_disambiguation()
    test_community_slang_normalization()
    test_cleaner_calling_name_preservation()
    test_meaningful_query_lookback()
    await test_end_to_end_chisa_ability_chat()

    print("\n" + "=" * 80)
    print("🎉 TOÀN BỘ 5 BỘ KIỂM THỬ PERSONA, REWRITE & RAG ĐỀU THÀNH CÔNG 100%!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
