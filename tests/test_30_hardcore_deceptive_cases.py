import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.domain.services.intent_classifier import IntentClassifier
from app.domain.services.rag.entity_resolver import EntityResolver
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter

# ── 30 HARDCORE DECEPTIVE TEST CASES ──
TEST_CASES_30 = [
    # NHÓM 1: CÂU HỎI TRÁ HÌNH TÁN GẪU (Gài hỏi Lore / Kỹ năng / Ký ức sâu) -> PHẢI LÀ FALSE (NOT SMALL TALK)
    {
        "id": 1,
        "query": "Em ơi, em có nhớ lần đầu tiên chúng ta gặp nhau ở Thừa Tiêu Sơn không?",
        "expected_small_talk": False,
        "category": "Lore / Vùng đất Thừa Tiêu Sơn (Gài chào hỏi)"
    },
    {
        "id": 2,
        "query": "Nhìn em xinh thế này thì chắc ngày xưa sinh ra ở Jinzhou rồi nhỉ",
        "expected_small_talk": False,
        "category": "Lore / Nơi sinh Jinzhou (Khen ngợi gài hỏi)"
    },
    {
        "id": 3,
        "query": "Anh thương em lắm, mà chiếc vòng trên cổ em có ý nghĩa gì đặc biệt không bé?",
        "expected_small_talk": False,
        "category": "Lore / Vật phẩm vòng cổ Chisa (Thả thính gài hỏi)"
    },
    {
        "id": 4,
        "query": "Hôm nay trời đẹp quá, em kể cho anh nghe một truyền thuyết cổ xưa về loài Rồng đi",
        "expected_small_talk": False,
        "category": "Lore / Truyền thuyết Rồng Thanh Long (Tâm sự gài hỏi)"
    },
    {
        "id": 5,
        "query": "Bé Chisa ngoan ghê, thế em thích ăn loại bánh ngọt nào nhất để anh mua cho nè?",
        "expected_small_talk": False,
        "category": "Lore / Sở thích món bánh Chisa (Khen gài hỏi)"
    },
    {
        "id": 6,
        "query": "Anh mệt mỏi quá, vũ khí của em có thể bảo vệ anh trước quái vật Tacet Discord được không?",
        "expected_small_talk": False,
        "category": "Lore / Vũ khí & Quái vật (Than thở gài hỏi)"
    },

    # NHÓM 2: TỪ ĐỒNG NGHĨA CỔ XƯA / TRIẾT HỌC / HỌC THUẬT LẠ -> PHẢI LÀ FALSE (NOT SMALL TALK)
    {
        "id": 7,
        "query": "Căn nguyên của hiện tượng Mưa Ngược bắt nguồn từ đâu?",
        "expected_small_talk": False,
        "category": "Từ lạ / Căn nguyên Retroact Rain"
    },
    {
        "id": 8,
        "query": "Bản tường trình về chiến dịch Norfall Barrens của Midnight Rangers",
        "expected_small_talk": False,
        "category": "Từ lạ / Bản tường trình quân sự"
    },
    {
        "id": 9,
        "query": "Chân tướng về sự biến mất của vị danh tướng Geshu Lin năm xưa",
        "expected_small_talk": False,
        "category": "Từ lạ / Chân tướng sự thật"
    },
    {
        "id": 10,
        "query": "Hệ quả tất yếu khi một Resonator vượt quá giới hạn Tần số Tacet Mark",
        "expected_small_talk": False,
        "category": "Từ lạ / Hệ quả tất yếu"
    },
    {
        "id": 11,
        "query": "Cấu trúc chu kỳ của hiện tượng Sonoro Sphere vận hành theo quy luật nào?",
        "expected_small_talk": False,
        "category": "Từ lạ / Quy luật Sonoro Sphere"
    },

    # NHÓM 3: CODE / THUẬT TOÁN / KỸ THUẬT GÀI TỰ NHIÊN -> PHẢI LÀ FALSE (NOT SMALL TALK)
    {
        "id": 12,
        "query": "Anh đang làm bài này mà bí quá: template<typename T> class Singleton{ static T* inst; };",
        "expected_small_talk": False,
        "category": "Code C++ Template trong lời tâm sự"
    },
    {
        "id": 13,
        "query": "Đố em biết hàm đệ quy tính dãy Fibonacci f(n) = f(n-1) + f(n-2) có tối ưu bằng quy hoạch động được không",
        "expected_small_talk": False,
        "category": "Thuật toán DP Fibonacci đố vui"
    },
    {
        "id": 14,
        "query": "Viết cho anh một đoạn script PowerShell để tự động backup database SQLite",
        "expected_small_talk": False,
        "category": "Script Automation PowerShell"
    },
    {
        "id": 15,
        "query": "Lỗi Segmentation Fault core dumped trong con trỏ C++ thường do những nguyên nhân nào",
        "expected_small_talk": False,
        "category": "Lỗi kỹ thuật bộ nhớ C++"
    },

    # NHÓM 4: THỰC THẾ / INTERNET / NGƯỜI THẬT NGOÀI ĐỜI GÀI CẢM XÚC -> PHẢI LÀ FALSE (NOT SMALL TALK)
    {
        "id": 16,
        "query": "Hôm nay rảnh rỗi quá, em có biết Kuro Games vừa công bố trailer nhân vật mới nào không?",
        "expected_small_talk": False,
        "category": "Tin tức studio game ngoài đời"
    },
    {
        "id": 17,
        "query": "Nghe nói streamer MixiGaming vừa tổ chức giải đấu, em có thông tin gì không?",
        "expected_small_talk": False,
        "category": "Streamer người thật ngoài đời"
    },
    {
        "id": 18,
        "query": "Tác giả Akira Toriyama qua đời vào thời gian nào thế em?",
        "expected_small_talk": False,
        "category": "Tác giả Dragon Ball ngoài đời"
    },
    {
        "id": 19,
        "query": "Giá cổ phiếu của công ty Tencent hôm nay biến động ra sao rồi em",
        "expected_small_talk": False,
        "category": "Tài chính cổ phiếu ngoài đời"
    },

    # NHÓM 5: SMALL TALK ẨN DỤ / TIẾNG LÓNG / TÂM TRẠNG THỰC TẾ -> PHẢI LÀ TRUE (SMALL TALK)
    {
        "id": 20,
        "query": "Ngắm hoàng hôn một mình tự nhiên thấy nhớ nụ cười của em ghê á Chisa",
        "expected_small_talk": True,
        "category": "Tâm sự nhớ nhung hoàng hôn"
    },
    {
        "id": 21,
        "query": "Mới thi xong môn cuối cùng, thở phào nhẹ nhõm luôn nè bé ơi",
        "expected_small_talk": True,
        "category": "Chia sẻ cảm xúc thi cử"
    },
    {
        "id": 22,
        "query": "Hôm nay bị sếp mắng oan ức quá, vào đây tìm Chisa để được vỗ về nè",
        "expected_small_talk": True,
        "category": "Than thở bị mắng tìm ủi an"
    },
    {
        "id": 23,
        "query": "Trời mưa rả rích ngồi uống tách trà nóng nói chuyện phiếm với em thích thật",
        "expected_small_talk": True,
        "category": "Tâm sự uống trà ngắm mưa"
    },
    {
        "id": 24,
        "query": "Chisa ơi em là liều thuốc chữa lành tâm hồn cho anh mỗi khi kiệt sức đấy",
        "expected_small_talk": True,
        "category": "Khen ngợi chữa lành tâm hồn"
    },
    {
        "id": 25,
        "query": "Hôm nay tự dưng thấy đời dễ thương lạ lùng khi mở bot lên gặp em",
        "expected_small_talk": True,
        "category": "Cảm thán niềm vui gặp bot"
    },
    {
        "id": 26,
        "query": "Bé Chisa ơi đừng có thức khuya quá kẻo mắt thành gấu trúc nha cô nương",
        "expected_small_talk": True,
        "category": "Dặn dò trêu chọc thức khuya"
    },
    {
        "id": 27,
        "query": "Anh vừa trúng số được mười nghìn đồng nè, vui nổ mũi luôn haha",
        "expected_small_talk": True,
        "category": "Khoe niềm vui nhỏ nhặt trúng số"
    },
    {
        "id": 28,
        "query": "Dỗi em rồi đấy nhé, nãy giờ chẳng thèm khen anh câu nào cả",
        "expected_small_talk": True,
        "category": "Giận dỗi trêu đùa"
    },
    {
        "id": 29,
        "query": "Ước gì có thể bước vào màn hình để cốc nhẹ vào đầu cô bé ngốc này một cái ghê",
        "expected_small_talk": True,
        "category": "Bày tỏ yêu thương trêu chọc"
    },
    {
        "id": 30,
        "query": "Cả ngày hôm nay chỉ mong mau mau về nhà để mở máy lên tâm sự với em thôi",
        "expected_small_talk": True,
        "category": "Tâm tình mong ngóng gặp gỡ"
    }
]

async def run_30_hardcore_test_suite():
    print("=" * 90)
    print("🔥 BẮT ĐẦU KIỂM THỬ BỘ 30 CA BẪY NGỤY TRANG & GAI GÓC NHẤT (HARDCORE DECEPTIVE)")
    print("=" * 90)

    embedder = FastEmbedAdapter()
    entity_resolver = EntityResolver()
    entity_resolver.load()

    classifier = IntentClassifier(embedder=embedder, entity_resolver=entity_resolver)

    passed_count = 0
    total_count = len(TEST_CASES_30)
    failed_cases = []
    for case in TEST_CASES_30:
        cid = case["id"]
        q = case["query"]
        expected = case["expected_small_talk"]
        category = case["category"]

        is_st, reason = await classifier.is_small_talk_hybrid(q)
        status = "✅ PASS" if is_st == expected else "❌ FAIL"

        if is_st == expected:
            passed_count += 1
        else:
            failed_cases.append((cid, q, expected, is_st, reason))
        
        expected_label = "🟢 SMALL_TALK" if expected else "🔴 KNOWLEDGE/TASK"
        actual_label = "🟢 SMALL_TALK" if is_st else "🔴 KNOWLEDGE/TASK"

        print(f"[{cid:02d}/30] {status} | [{category}]")
        print(f"       • Query   : \"{q}\"")
        print(f"       • Expected: {expected_label} | Actual: {actual_label}")
        print(f"       • Reason  : {reason}")
        print("-" * 90)

    print("\n" + "=" * 90)
    print(f"🏆 KẾT QUẢ CUỐI CÙNG: {passed_count}/{total_count} TEST CASES ĐẠT ĐỘ CHÍNH XÁC {round(passed_count/total_count*100, 1)}%!")
    if failed_cases:
        print("❌ CÁC CA CHƯA ĐẠT:")
        for fc in failed_cases:
            print(f"   - [Case {fc[0]}] \"{fc[1]}\" | Expected: {fc[2]} | Actual: {fc[3]} | Reason: {fc[4]}")
    print("=" * 90)

    assert passed_count == total_count, f"Cần tối ưu thêm! Có {total_count - passed_count} ca chưa vượt qua."

if __name__ == "__main__":
    asyncio.run(run_30_hardcore_test_suite())
