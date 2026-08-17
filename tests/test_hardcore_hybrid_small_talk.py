import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.domain.services.intent_classifier import IntentClassifier
from app.domain.services.rag.entity_resolver import EntityResolver
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter

async def test_hardcore_hybrid_gateway():
    print("=" * 80)
    print("🛡️ KIỂM THỬ HARDCORE GUARDED HYBRID INTENT ROUTER (REGEX x SEMANTIC)")
    print("=" * 80)

    embedder = FastEmbedAdapter()
    entity_resolver = EntityResolver()
    entity_resolver.load()

    classifier = IntentClassifier(embedder=embedder, entity_resolver=entity_resolver)

    # ── PHẦN 1: Kiểm tra Hardcore Guards (Bắt buộc KHÔNG được là Small Talk) ──
    print("\n[PHẦN 1] Kiểm thử Hardcore Guards (Chặn 100% Code, Lore, Interrogatives)...")
    guard_cases = [
        ("Jiyan dùng vũ khí gì thế em?", "Interrogative / Lore"),
        ("vũ khí của em là gì", "Interrogative / Lore Persona"),
        ("thời tiết hôm nay tại Hà Nội", "Search entity"),
        ("class LFUCache{int get(int k);};", "Code Syntax"),
        ("def quick_sort(arr): return arr", "Code Syntax"),
        ("giải thích cho anh về thảm họa Lament", "Interrogative / Instruction"),
        ("biết hoanbucon là ai không em", "Interrogative / Web Entity"),
        ("Tướng quân Geshu Lin mất tích ở đâu?", "Lore Entity"),
    ]

    for q, desc in guard_cases:
        is_st, reason = await classifier.is_small_talk_hybrid(q)
        print(f"  • \"{q}\" [{desc}]")
        print(f"    ➔ is_small_talk: {is_st} | Reason: {reason}")
        assert is_st is False, f"LỖI: '{q}' bị phân loại nhầm thành Small Talk!"
    print("  ✓ PASS: 100% câu hỏi tri thức và code đều bị Hardcore Guards chặn đứng!")

    # ── PHẦN 2: Kiểm thử Regex Fast-Path (<0.05ms) ──
    print("\n[PHẦN 2] Kiểm thử Regex Fast-Path (Chào hỏi, chúc ngủ ngon, cảm ơn)...")
    regex_cases = [
        "chào em chisa nhé",
        "chào buổi sáng em chisa",
        "chúc em ngủ ngon nha chisa, g9 nè",
        "em đáng yêu ghê á chisa ơi",
        "cảm ơn em nhiều nha chisa"
    ]
    for q in regex_cases:
        is_st, reason = await classifier.is_small_talk_hybrid(q)
        print(f"  • \"{q}\" ➔ is_small_talk: {is_st} ({reason})")
        assert is_st is True
    print("  ✓ PASS: Regex Fast-Path bắt chính xác các câu tán gẫu trực tiếp!")

    # ── PHẦN 3: Kiểm thử Semantic Anchors (Biến thể lạ chưa có trong Regex) ──
    print("\n[PHẦN 3] Kiểm thử Semantic Anchors (Biến thể tự nhiên không khớp Regex)...")
    semantic_cases = [
        "hôm nay đi làm về mệt quá chisa à",
        "nhìn em dễ thương xinh xắn quá chisa",
        "chúc chisa một ngày mới vui vẻ tràn đầy sức sống nha"
    ]
    for q in semantic_cases:
        is_st, reason = await classifier.is_small_talk_hybrid(q)
        print(f"  • \"{q}\" ➔ is_small_talk: {is_st} ({reason})")
        assert is_st is True, f"LỖI: Semantic Anchor bỏ sót câu tán gẫu '{q}'!"
    print("  ✓ PASS: Semantic Similarity mở rộng thành công độ phủ cho các câu tán gẫu lạ!")

    # ── PHẦN 4: Kiểm thử Contrastive Knowledge Penalty (Từ đồng nghĩa tra cứu bị dìm điểm) ──
    print("\n[PHẦN 4] Kiểm thử Contrastive Knowledge Penalty (Dìm điểm các từ đồng nghĩa tra cứu)...")
    contrastive_cases = [
        ("cho anh hỏi lai lịch xuất thân của em", "Lai lịch / Xuất thân"),
        ("thông số chỉ số sức mạnh của em", "Thông số / Chỉ số"),
        ("nguyên lý vận hành của cơ chế đó", "Nguyên lý / Vận hành")
    ]
    for q, desc in contrastive_cases:
        is_st, reason = await classifier.is_small_talk_hybrid(q)
        print(f"  • \"{q}\" [{desc}] ➔ is_small_talk: {is_st} ({reason})")
        assert is_st is False, f"LỖI: '{q}' có nét nghĩa tra cứu nhưng không bị Contrastive Penalty chặn!"
    print("  ✓ PASS: Contrastive Knowledge Penalty dìm điểm thành công 100% câu hỏi tra cứu đồng nghĩa!")

    print("\n" + "=" * 80)
    print("🎉 TOÀN BỘ CÁC BỘ KIỂM THỬ HARDCORE HYBRID ĐỀU ĐẠT 100% THÀNH CÔNG!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_hardcore_hybrid_gateway())

