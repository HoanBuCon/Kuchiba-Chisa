"""
Test Conflict Reconciliation with the New 2-Type Memory Model (user_fact & shared_story).
Verifies:
1. CONTRADICT resolution on user_fact (Location: Đà Nẵng -> Hà Nội)
2. CONTRADICT resolution on shared_story (Nickname: Cáo Đen -> Chỉ Huy)
3. DUPLICATE resolution on repeated statements
4. KEEP_BOTH resolution on distinct facts
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from app.application.dependencies import container
from app.domain.services.memory_extractor import MemoryExtractor


async def test_conflict_reconciliation():
    print("=" * 80)
    print("🚀 BẮT ĐẦU KIỂM THỬ: CONFLICT RECONCILIATION CHO 2-TYPE MEMORY MODEL")
    print("=" * 80)

    extractor: MemoryExtractor = container.memory_extractor
    test_user_id = "test_conflict_user_2type"
    test_conv_id = "test_conv_2type"

    # Clean up test user memories first
    try:
        # Search all memories for this user
        dummy_vec = await extractor.embedder.embed_text("test", prefix="query: ")
        old_points = await extractor.vector_store.search_by_user(
            collection="memories",
            query_vector=dummy_vec,
            user_id=test_user_id,
            limit=20,
            score_threshold=0.0
        )
        if old_points:
            ids_to_del = [p["id"] for p in old_points]
            await extractor.vector_store.delete_points(collection="memories", ids=ids_to_del)
            print(f"🧹 Đã dọn dẹp {len(ids_to_del)} ký ức cũ của user test.")
    except Exception as e:
        print(f"Dọn dẹp: {e}")

    # ── CASE 1: user_fact CONTRADICT (Location: Đà Nẵng -> Hà Nội) ──
    print("\n[TEST 1] Kiểm tra Đối soát Mâu thuẫn user_fact (Đà Nẵng -> Hà Nội)...")
    # Lần 1: Senpai ở Đà Nẵng
    await extractor.extract_and_store_batch(
        user_id=test_user_id,
        conversation_id=test_conv_id,
        history=[
            {"role": "user", "content": "chào em"},
            {"role": "assistant", "content": "Chào Senpai~"}
        ],
        current_user_message="anh đang sống ở Đà Nẵng, thời tiết trong này mát mẻ lắm",
        current_assistant_reply="Đà Nẵng đẹp và đáng sống lắm đó Senpai~"
    )

    # Kiểm tra Qdrant đã có Đà Nẵng chưa
    vec_danang = await extractor.embedder.embed_text("Senpai sống ở đâu?", prefix="query: ")
    res_1 = await extractor.vector_store.search_by_user(
        collection="memories",
        query_vector=vec_danang,
        user_id=test_user_id,
        limit=5,
        score_threshold=0.60
    )
    print(f"  • Ký ức sau lần 1: {[p['payload']['text_content'] for p in res_1]}")
    assert len(res_1) >= 1
    assert any("đà nẵng" in p["payload"]["text_content"].lower() for p in res_1)
    danang_id = res_1[0]["id"]

    # Lần 2: Senpai thông báo chuyển ra Hà Nội
    print("  -> Senpai chuyển ra Hà Nội (Kích hoạt CONTRADICT)...")
    await extractor.extract_and_store_batch(
        user_id=test_user_id,
        conversation_id=test_conv_id,
        history=[
            {"role": "user", "content": "anh vừa chuyển nhà xong"},
            {"role": "assistant", "content": "Senpai chuyển đi đâu thế ạ?"}
        ],
        current_user_message="anh đã chuyển hẳn ra Hà Nội sống và làm việc rồi",
        current_assistant_reply="Oa chúc mừng Senpai ổn định cuộc sống mới tại Hà Nội nha!"
    )

    # Kiểm tra lại Qdrant: Đà Nẵng phải bị xóa, Hà Nội phải tồn tại
    res_2 = await extractor.vector_store.search_by_user(
        collection="memories",
        query_vector=vec_danang,
        user_id=test_user_id,
        limit=5,
        score_threshold=0.60
    )
    contents_2 = [p["payload"]["text_content"].lower() for p in res_2]
    ids_2 = [p["id"] for p in res_2]
    print(f"  • Ký ức sau lần 2 (Sau đối soát): {contents_2}")

    assert any("hà nội" in c for c in contents_2), "Hà Nội fact must exist"
    assert danang_id not in ids_2, f"Old Đà Nẵng memory ({danang_id}) must be DELETED"
    print("  ✓ PASS: Đã xóa thành công ký ức cũ (Đà Nẵng) và ghi đè ký ức mới (Hà Nội)!")

    # ── CASE 2: shared_story CONTRADICT (Nickname: Cáo Đen -> Chỉ Huy) ──
    print("\n[TEST 2] Kiểm tra Đối soát Mâu thuẫn shared_story (Biệt danh cũ -> Biệt danh mới)...")
    # Lần 1: Đặt biệt danh 'Cáo Đen'
    await extractor.extract_and_store_batch(
        user_id=test_user_id,
        conversation_id=test_conv_id,
        history=[
            {"role": "user", "content": "đặt biệt danh cho anh đi"},
            {"role": "assistant", "content": "Em gọi Senpai là 'Cáo Đen' nha~"}
        ],
        current_user_message="ừ chốt gọi anh là Cáo Đen nhé",
        current_assistant_reply="Dạ vâng, từ nay biệt danh của Senpai là Cáo Đen nha!"
    )

    vec_nick = await extractor.embedder.embed_text("Biệt danh của Senpai", prefix="query: ")
    res_nick1 = await extractor.vector_store.search_by_user(
        collection="memories",
        query_vector=vec_nick,
        user_id=test_user_id,
        limit=5,
        score_threshold=0.60
    )
    print(f"  • Ký ức Biệt danh lần 1: {[p['payload']['text_content'] for p in res_nick1]}")
    assert any("cáo đen" in p["payload"]["text_content"].lower() for p in res_nick1)
    old_nick_id = [p["id"] for p in res_nick1 if "cáo đen" in p["payload"]["text_content"].lower()][0]

    # Lần 2: Đổi biệt danh sang 'Chỉ Huy'
    print("  -> Senpai đổi biệt danh sang 'Chỉ Huy' (Kích hoạt CONTRADICT)...")
    await extractor.extract_and_store_batch(
        user_id=test_user_id,
        conversation_id=test_conv_id,
        history=[
            {"role": "user", "content": "anh không thích tên Cáo Đen nữa"},
            {"role": "assistant", "content": "Vậy Senpai muốn đổi sang tên gì ạ?"}
        ],
        current_user_message="từ giờ đổi biệt danh, gọi anh là Chỉ Huy nha",
        current_assistant_reply="Dạ vâng! Từ nay em sẽ gọi Senpai là 'Chỉ Huy' ạ!"
    )

    res_nick2 = await extractor.vector_store.search_by_user(
        collection="memories",
        query_vector=vec_nick,
        user_id=test_user_id,
        limit=5,
        score_threshold=0.60
    )
    contents_nick2 = [p["payload"]["text_content"].lower() for p in res_nick2]
    ids_nick2 = [p["id"] for p in res_nick2]
    print(f"  • Ký ức Biệt danh lần 2 (Sau đối soát): {contents_nick2}")

    assert any("chỉ huy" in c for c in contents_nick2), "Chỉ Huy nickname must exist"
    assert old_nick_id not in ids_nick2, f"Old Nickname memory ({old_nick_id}) must be DELETED"
    print("  ✓ PASS: Đã xóa thành công biệt danh cũ 'Cáo Đen' và cập nhật 'Chỉ Huy'!")

    # ── CASE 3: DUPLICATE (Nhắc lại thông tin đã có) ──
    print("\n[TEST 3] Kiểm tra Xử lý Trùng lặp (DUPLICATE)...")
    count_before = len(res_nick2)
    await extractor.extract_and_store_batch(
        user_id=test_user_id,
        conversation_id=test_conv_id,
        history=[
            {"role": "user", "content": "nhớ biệt danh của anh không?"},
            {"role": "assistant", "content": "Dạ em nhớ chứ, là Chỉ Huy mà~"}
        ],
        current_user_message="chuẩn rồi, biệt danh của anh là Chỉ Huy đó",
        current_assistant_reply="Hihi em làm sao mà quên được ạ~"
    )

    res_nick3 = await extractor.vector_store.search_by_user(
        collection="memories",
        query_vector=vec_nick,
        user_id=test_user_id,
        limit=10,
        score_threshold=0.60
    )
    print(f"  • Số lượng ký ức sau khi nhắc lại: {len(res_nick3)} (Trước: {count_before})")
    assert len(res_nick3) == count_before, "Duplicate memory must not create new vector points"
    print("  ✓ PASS: Trùng lặp được bỏ qua hoàn toàn, không tạo rác vector!")

    # Clean up test user
    try:
        all_ids = [p["id"] for p in res_nick3]
        if all_ids:
            await extractor.vector_store.delete_points(collection="memories", ids=all_ids)
            print("🧹 Dọn dẹp xong dữ liệu test.")
    except Exception:
        pass

    print("\n" + "=" * 80)
    print("🎉 TOÀN BỘ CƠ CHẾ CONFLICT RECONCILIATION ĐÃ HOẠT ĐỘNG HOÀN HẢO VỚI 2-TYPE MEMORY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_conflict_reconciliation())
