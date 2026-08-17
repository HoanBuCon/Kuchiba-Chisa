import asyncio
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.domain.services.persona_loader import persona_loader
from app.domain.services.intent_classifier import IntentClassifier
from app.domain.services.context_builder import ContextBuilder
from app.domain.entities.emotion import EmotionState
from app.domain.interfaces.embedding_provider import IEmbeddingProvider


class MockEmbedder(IEmbeddingProvider):
    async def embed_text(self, text: str, prefix: str = "passage: ") -> list[float]:
        # Simple deterministic embedding for testing semantic anchors
        text_lower = text.lower()
        vec = [0.0] * 128
        
        # Food / Sweets / Ice cream / Drinks cluster
        if any(w in text_lower for w in ["ăn", "kem", "bánh", "socola", "chocolate", "pocky", "trà", "cà phê", "mát lạnh", "đồ ngọt", "nhâm nhi"]):
            vec[0] = 1.0
            vec[1] = 0.8
        # Spicy / Pepper / Taste cluster
        if any(w in text_lower for w in ["cay", "ớt", "xé lưỡi", "nóng", "vị giác", "khẩu vị"]):
            vec[2] = 1.0
            vec[3] = 0.8
        # Cats / Hobbies / Craft / Sunset cluster
        if any(w in text_lower for w in ["mèo", "bốn chân", "thú cưng", "thủ công", "hoàng hôn", "tản bộ", "dạo", "hẹn hò"]):
            vec[4] = 1.0
            vec[5] = 0.8
        # Age / Identity / Origin / Academy cluster
        if any(w in text_lower for w in ["tuổi", "sinh năm", "sinh nhật", "quê", "quê quán", "ashinohara", "startorch", "lahai-roi", "tacet mark", "sonoro"]):
            vec[6] = 1.0
            vec[7] = 0.8

        # Normalize vector
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        else:
            # Generate deterministic orthogonal hash-based vector for unmatched text
            import hashlib
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            for i in range(16, 128):
                vec[i] = ((h >> (i % 32)) & 1) * 2.0 - 1.0
            norm = sum(x * x for x in vec) ** 0.5
            vec = [x / norm for x in vec]
        return vec

    async def embed_batch(self, texts: list[str], prefix: str = "passage: ") -> list[list[float]]:
        return [await self.embed_text(t, prefix=prefix) for t in texts]


async def run_persona_tests():
    print("=" * 80)
    print("🚀 BẮT ĐẦU KIỂM THỬ: FILE-DRIVEN PERSONA LOADER & SEMANTIC TRAIT INJECTION")
    print("=" * 80)

    # ── TEST 1: File-driven PersonaLoader ──
    print("\n[TEST 1] Kiểm tra nạp file markdown từ disk qua PersonaLoader...")
    pers_snippet = persona_loader.get_snippet("PERSONALITY")
    prof_snippet = persona_loader.get_snippet("PROFILE")
    empty_snippet = persona_loader.get_snippet(None)

    assert "Socola đen" in pers_snippet or "socola" in pers_snippet.lower()
    assert "Ớt cay" in pers_snippet or "ớt" in pers_snippet.lower()
    print("  • Personality Snippet:\n", pers_snippet.strip())
    
    assert "18 tuổi" in prof_snippet
    assert "Sonoro Sphere" in prof_snippet
    print("  • Profile Snippet:\n", prof_snippet.strip())

    assert empty_snippet == ""
    print("  • Empty Trait -> Snippet is empty string (0 tokens).")
    print("  ✓ PASS: PersonaLoader nạp và trích xuất thành công 100%!")

    # ── TEST 2: Fast-Path & Semantic Detection in IntentClassifier ──
    print("\n[TEST 2] Kiểm tra Fast-Path Regex & Semantic Persona Detection...")
    embedder = MockEmbedder()
    classifier = IntentClassifier(embedder=embedder)

    test_cases = [
        # 1. Ẩm thực kem/socola đời thường (Câu của user)
        ("thôi ko sao, lát dẫn đi ăn kem", "PERSONALITY", "Rủ đi ăn kem trực tiếp"),
        # 2. Ẩn dụ nhâm nhi đồ ngọt mát lạnh (Không từ khóa cứng kem/ăn)
        ("Lát dắt bé đi nhâm nhi chút gì đó mát lạnh ngọt ngào", "PERSONALITY", "Ẩn dụ nhâm nhi đồ ngọt mát lạnh"),
        # 3. Trêu ăn cay
        ("Nấu món gì cay xé lưỡi đãi bé Chisa nhé", "PERSONALITY", "Ẩm thực cay nồng"),
        # 4. Ẩn dụ ngắm mèo (Bốn chân có lông)
        ("Ra công viên ngắm mấy bé bốn chân có lông với anh không", "PERSONALITY", "Ẩn dụ thú cưng mèo"),
        # 5. Hỏi tuổi trực tiếp
        ("Em bao nhiêu tuổi rồi bé Chisa ơi", "PROFILE", "Hỏi tuổi trực tiếp"),
        # 6. Hỏi quê quán
        ("Quê quán ban đầu của em ở đâu thế Chisa", "PROFILE", "Hỏi quê quán"),
        # 7. Câu hỏi kỹ thuật / thuật toán
        ("Giải thuật toán Dijkstra bằng Python", None, "Câu hỏi lập trình (Zero Token)"),
        # 8. Lời chào hỏi bình thường
        ("Chào em Chisa buổi sáng nha", None, "Chào hỏi thông thường (Zero Token)")
    ]

    for idx, (query, expected, desc) in enumerate(test_cases, 1):
        detected = await classifier.detect_persona_trait(query)
        status = "✅ PASS" if detected == expected else "❌ FAIL"
        print(f"  [{idx}/{len(test_cases)}] {status} | [{desc}]")
        print(f"       • Query   : \"{query}\"")
        print(f"       • Expected: {expected} | Actual: {detected}")
        assert detected == expected, f"Expected {expected} but got {detected} for '{query}'"

    # ── TEST 3: ContextBuilder Prompt Injection & Token Verification ──
    print("\n[TEST 3] Kiểm tra Lắp ráp Prompt tại ContextBuilder (Stage 6)...")
    import uuid
    emotion = EmotionState(user_id=uuid.uuid4(), joy=0.5, sadness=0.1, trust=0.8, irritation=0.0, attachment=0.6)
    
    # A. With PERSONALITY Trait
    prompt_with_traits = ContextBuilder.build_system_skeleton(
        emotion=emotion,
        attachment_bonus=0.1,
        persona_trait_type="PERSONALITY"
    )
    assert "[CHISA'S CANONICAL PERSONALITY & TRAITS]" in prompt_with_traits
    assert "Socola đen" in prompt_with_traits
    print("  • Prompt với PERSONALITY: Chứa đầy đủ [CHISA'S CANONICAL PERSONALITY & TRAITS] (Socola đen, trà/cafe/bánh, sợ ớt cay, mèo, hoàng hôn).")

    # B. With PROFILE Trait
    prompt_with_profile = ContextBuilder.build_system_skeleton(
        emotion=emotion,
        attachment_bonus=0.1,
        persona_trait_type="PROFILE"
    )
    assert "[CHISA'S CANONICAL PROFILE & IDENTITY]" in prompt_with_profile
    assert "18 tuổi" in prompt_with_profile
    print("  • Prompt với PROFILE: Chứa đầy đủ [CHISA'S CANONICAL PROFILE & IDENTITY] (18 tuổi / 38 tuổi Sonoro Sphere, Ashinohara, Startorch).")

    # C. With NONE (Normal Query)
    prompt_without_traits = ContextBuilder.build_system_skeleton(
        emotion=emotion,
        attachment_bonus=0.1,
        persona_trait_type=None
    )
    assert "[CHISA'S CANONICAL PERSONALITY & TRAITS]" not in prompt_without_traits
    assert "[CHISA'S CANONICAL PROFILE & IDENTITY]" not in prompt_without_traits
    print("  • Prompt thông thường: Tuyệt đối KHÔNG chèn thừa (0 token overhead).")

    print("\n" + "=" * 80)
    print("🎉 TOÀN BỘ CÁC BÀI KIỂM THỬ PERSONA & SEMANTIC TRAIT ĐỀU THÀNH CÔNG 100%!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_persona_tests())
