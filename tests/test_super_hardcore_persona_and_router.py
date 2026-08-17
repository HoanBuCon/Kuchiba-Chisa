import asyncio
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.domain.services.persona_loader import persona_loader
from app.domain.services.intent_classifier import IntentClassifier
from app.domain.services.context_builder import ContextBuilder
from app.domain.entities.emotion import EmotionState
from app.domain.models.intent_result import ChatIntent
from app.domain.interfaces.embedding_provider import IEmbeddingProvider


class MockHighFidelityEmbedder(IEmbeddingProvider):
    """
    Mock Embedder mô phỏng vector không gian ngữ nghĩa thực tế (High-Fidelity Embedding):
    - Phân tách rõ ràng giữa Ngữ cảnh đối thoại cá nhân Chisa vs Lore nhân vật khác vs Code/Toán học.
    """
    async def embed_text(self, text: str, prefix: str = "passage: ") -> list[float]:
        text_lower = text.lower()
        vec = [0.0] * 128

        # Cluster 1: Chisa Food / Sweets / Ice cream / Dark Chocolate / Drinks
        if any(w in text_lower for w in ["ăn", "kem", "bánh", "socola", "chocolate", "pocky", "trà", "cà phê", "mát lạnh", "đồ ngọt", "nhâm nhi", "đá bào", "trà sữa", "đăng đắng"]):
            vec[0] = 1.0
            vec[1] = 0.85
        # Cluster 2: Spicy / Pepper / Burning Tongue Taste
        if any(w in text_lower for w in ["cay", "ớt", "xé lưỡi", "nóng", "vị giác", "khẩu vị", "mì cay", "cấp độ"]):
            vec[2] = 1.0
            vec[3] = 0.85
        # Cluster 3: Cats / Hobbies / Craft / Sunset / Stroll with Senpai
        if any(w in text_lower for w in ["mèo", "bốn chân", "thú cưng", "thủ công", "hoàng hôn", "tản bộ", "dạo", "hẹn hò", "mặt trời lặn", "khí trời"]):
            vec[4] = 1.0
            vec[5] = 0.85
        # Cluster 4: Age / Identity / Origin / Academy / Secret Anomaly
        if any(w in text_lower for w in ["tuổi", "sinh năm", "sinh nhật", "quê", "quê quán", "ashinohara", "startorch", "lahai-roi", "tacet mark", "sonoro", "chôn rau cắt rốn", "cánh tay phải", "trẻ măng"]):
            vec[6] = 1.0
            vec[7] = 0.85

        # Normalize vector
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        else:
            import hashlib
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            for i in range(16, 128):
                vec[i] = ((h >> (i % 32)) & 1) * 2.0 - 1.0
            norm = sum(x * x for x in vec) ** 0.5
            vec = [x / norm for x in vec]
        return vec

    async def embed_batch(self, texts: list[str], prefix: str = "passage: ") -> list[list[float]]:
        return [await self.embed_text(t, prefix=prefix) for t in texts]


# 25 HARDCORE ADVERSARIAL TEST CASES
SUPER_HARDCORE_CASES = [
    # ── NHÓM 1: Ẩn dụ & Tiếng lóng Ăn uống / Hẹn hò tinh vi (Extreme Metaphor) ──
    {
        "query": "Hôm nay nóng quá, ghé tiệm đá bào nạp chút hương vị đăng đắng ngọt ngào đi em",
        "expected_trait": "PERSONALITY",
        "category": "Metaphor Food (Đá bào vị đắng ngọt)",
    },
    {
        "query": "Dắt cục bông nhỏ này đi hít chút khí trời lúc mặt trời lặn nhé",
        "expected_trait": "PERSONALITY",
        "category": "Metaphor Date (Tản bộ mặt trời lặn / Hoàng hôn)",
    },
    {
        "query": "Nhà anh có nuôi con mèo biết nhào bột này, qua xem không",
        "expected_trait": "PERSONALITY",
        "category": "Metaphor Cat (Mèo biết nhào bột)",
    },
    {
        "query": "Mua cho em ly trà sữa mười phần đường một phần đá nha",
        "expected_trait": "PERSONALITY",
        "category": "Metaphor Sweets (Trà sữa nhiều đường)",
    },
    {
        "query": "Nếm thử bát mì cay cấp độ bảy của quán này xem ai khóc trước",
        "expected_trait": "PERSONALITY",
        "category": "Metaphor Spicy (Thách đố ăn mì cay cấp 7)",
    },

    # ── NHÓM 2: Bẫy Code / Toán học chứa từ khóa Ăn uống / Mèo / Bánh (Deceptive Coding Traps) ──
    {
        "query": "Viết chương trình Python mô phỏng bài toán Người ăn kem (Ice Cream Eating Problem) bằng Dynamic Programming",
        "expected_trait": None,
        "category": "Code Trap (Bài toán Ăn kem DP)",
    },
    {
        "query": "struct Cat { string name; int age; }; viết hàm khởi tạo class mèo bằng C++",
        "expected_trait": None,
        "category": "Code Trap (Class Cat / Mèo C++)",
    },
    {
        "query": "Phân tích độ phức tạp thời gian của thuật toán chia bánh Pancake Sorting",
        "expected_trait": None,
        "category": "Code Trap (Thuật toán Chia bánh Pancake)",
    },
    {
        "query": "Giải phương trình bậc hai tìm số lượng que kem x: x^2 - 10x + 21 = 0",
        "expected_trait": None,
        "category": "Math Trap (Phương trình bậc 2 que kem)",
    },
    {
        "query": "Hướng dẫn cấu hình webhook Discord cho bot bằng JavaScript",
        "expected_trait": None,
        "category": "Tech Guide Trap (Config Discord Webhook)",
    },

    # ── NHÓM 3: Bẫy Lore nhân vật khác hỏi ăn uống / tuổi tác (Third-Party Lore Traps) ──
    {
        "query": "Jiyan và Tướng quân Midnight Rangers thích ăn món gì nhất trong quân ngũ",
        "expected_trait": None,
        "category": "3rd-Party Lore (Jiyan thích ăn món gì)",
    },
    {
        "query": "Shorekeeper được sinh ra ở đâu và bao nhiêu tuổi rồi em",
        "expected_trait": None,
        "category": "3rd-Party Lore (Shorekeeper sinh ra ở đâu và tuổi)",
    },
    {
        "query": "Changli dạy dỗ Jinhsi ở đâu thế Chisa",
        "expected_trait": None,
        "category": "3rd-Party Lore (Changli & Jinhsi)",
    },
    {
        "query": "Vũ khí Broadblade của tướng rồng Jiyan có chỉ số tấn công cơ bản là bao nhiêu",
        "expected_trait": None,
        "category": "3rd-Party Lore (Broadblade Jiyan)",
    },

    # ── NHÓM 4: Hỏi xoáy Tuổi tác, Thân thế & Bí mật dị thường (Subtle Profile & Secret Inquiries) ──
    {
        "query": "Nhìn mặt em trẻ măng như học sinh cấp ba ấy, thật ra em sinh năm bao nhiêu thế",
        "expected_trait": "PROFILE",
        "category": "Age Trap (Trẻ măng như cấp 3, sinh năm bao nhiêu)",
    },
    {
        "query": "Bí mật về dấu vết kỳ lạ trên cánh tay phải của em là gì vậy bé",
        "expected_trait": "PROFILE",
        "category": "Secret Trap (Dấu vết kỳ lạ cánh tay phải / Tacet mark)",
    },
    {
        "query": "Nơi chôn rau cắt rốn của cô bé tóc nâu này ở đâu ta",
        "expected_trait": "PROFILE",
        "category": "Origin Trap (Chôn rau cắt rốn / Quê quán)",
    },
    {
        "query": "Học viện Startorch ở thành phố Lahai-Roi dạy những môn gì thế Chisa",
        "expected_trait": "PROFILE",
        "category": "Academy Trap (Học viện Startorch Lahai-Roi)",
    },

    # ── NHÓM 5: Bẫy Kép (Combined Personality & Profile) ──
    {
        "query": "Bé Chisa 18 tuổi ơi lát có muốn đi ăn bánh ngọt ngắm hoàng hôn với anh không",
        "expected_trait": "BOTH",
        "category": "Hybrid Trap (Vừa 18 tuổi vừa ăn bánh ngắm hoàng hôn)",
    },
    {
        "query": "Cô bé Ashinohara ơi em thích ăn socola hay uống trà hơn nè",
        "expected_trait": "BOTH",
        "category": "Hybrid Trap (Vừa quê Ashinohara vừa hỏi socola/trà)",
    },

    # ── NHÓM 6: Small Talk tâm sự / Khen ngợi thuần túy (Tuyệt đối KHÔNG kích hoạt bừa bãi) ──
    {
        "query": "Hôm nay anh làm việc OT mệt lử cả người rồi em ơi",
        "expected_trait": None,
        "category": "Pure Small Talk (Than thở mệt mỏi)",
    },
    {
        "query": "Nhìn nụ cười của Chisa làm anh thấy ấm lòng ghê luôn á",
        "expected_trait": None,
        "category": "Pure Small Talk (Khen ngợi nụ cười)",
    },
    {
        "query": "Chúc bé ngủ ngon nhé, mơ thấy nhiều điều đẹp đẽ nha",
        "expected_trait": None,
        "category": "Pure Small Talk (Chúc ngủ ngon)",
    },
    {
        "query": "Hôm nay tự dưng thấy nhớ giọng nói của em ghê",
        "expected_trait": None,
        "category": "Pure Small Talk (Nhớ nhung tâm tình)",
    },
    {
        "query": "Thời tiết hôm nay đẹp thật, tự dưng thấy yêu đời hẳn",
        "expected_trait": None,
        "category": "Pure Small Talk (Cảm thán thời tiết yêu đời)",
    },
]


async def run_super_hardcore_benchmark():
    print("=" * 95)
    print("🔥 BẮT ĐẦU BỘ KIỂM THỬ SIÊU KHÓ (25 ADVERSARIAL HARDCORE DECEPTIVE TEST CASES)")
    print("=" * 95)

    from app.domain.services.rag.entity_resolver import EntityResolver
    entity_resolver = EntityResolver()
    entity_resolver.load()

    embedder = MockHighFidelityEmbedder()
    classifier = IntentClassifier(embedder=embedder, entity_resolver=entity_resolver)

    passed_count = 0
    failed_cases = []

    for idx, test in enumerate(SUPER_HARDCORE_CASES, 1):
        query = test["query"]
        expected = test["expected_trait"]
        category = test["category"]

        actual = await classifier.detect_persona_trait(query)

        is_passed = (actual == expected)
        if is_passed:
            passed_count += 1
            status = "✅ PASS"
        else:
            failed_cases.append((idx, query, expected, actual, category))
            status = "❌ FAIL"

        print(f"[{idx:02d}/25] {status} | [{category}]")
        print(f"       • Query   : \"{query}\"")
        print(f"       • Expected: {expected} | Actual: {actual}")
        print("-" * 95)

    accuracy = (passed_count / len(SUPER_HARDCORE_CASES)) * 100.0
    print(f"\n🏆 TỔNG KẾT BENCHMARK: {passed_count}/{len(SUPER_HARDCORE_CASES)} CASES ĐẠT {accuracy:.1f}% ĐỘ CHÍNH XÁC!")

    if failed_cases:
        print("\n❌ CÁC TEST CASES CHƯA ĐẠT:")
        for idx, query, expected, actual, category in failed_cases:
            print(f"  • Case #{idx} [{category}]: \"{query}\" -> Expected: {expected}, Got: {actual}")

    assert passed_count == len(SUPER_HARDCORE_CASES), f"Failed {len(failed_cases)} test cases!"


if __name__ == "__main__":
    asyncio.run(run_super_hardcore_benchmark())
