"""
================================================================================
CHISA AI - 30-TURN COMPREHENSIVE END-TO-END TEST SUITE
Testing:
1. Batched 3-Turn Memory Extraction (interaction_count % 3 == 0)
2. Bidirectional Fact Extraction (User facts & Chisa-given Nicknames)
3. Memory Conflict Reconciliation (CONTRADICT, DUPLICATE, KEEP_BOTH)
4. Periodic Auto-Summarization (interaction_count % 10 == 0)
5. Full Recall & Intent Retrieval (Turns 28-30)
================================================================================
"""

import sys
import os

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import asyncio
import json
import time
import uuid
from typing import Dict, List, Any

from app.application.dependencies import container
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.repositories.conversation_repository import SqlAlchemyConversationRepository
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.shared.utils.user_identity import normalize_user_id
from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

# 30 Curated Conversational Test Cases
TEST_SCENARIO_TURNS = [
    # --- BATCH 1 (Turns 1-3): Identity & Initial Facts ---
    {"turn": 1, "msg": "Chào em Chisa, anh là kỹ sư phần mềm đang sống và làm việc ở Hà Nội nhé.", "expect_bg": None},
    {"turn": 2, "msg": "Hôm nay anh làm việc hơi mệt mỏi một chút, chỉ muốn nhắn tin tán gẫu với em thôi.", "expect_bg": None},
    {"turn": 3, "msg": "Anh hiện đang làm việc từ xa (remote) tại nhà suốt cả tuần nè.", "expect_bg": "Batch 1: Trích xuất nghề nghiệp kỹ sư phần mềm ở Hà Nội"},

    # --- BATCH 2 (Turns 4-6): Bidirectional Nickname Agreement ---
    {"turn": 4, "msg": "Ở nhà một mình buồn quá, em có thể đặt cho anh một biệt danh thân mật không?", "expect_bg": None},
    {"turn": 5, "msg": "Biệt danh nào nghe vừa ấm áp vừa gắn bó với Chisa ấy nha.", "expect_bg": None},
    {"turn": 6, "msg": "Biệt danh đó nghe đáng yêu và ấm áp ghê, từ nay em cứ gọi anh như thế nhé!", "expect_bg": "Batch 2: Trích xuất nickname Chisa đặt cho Senpai"},

    # --- BATCH 3 (Turns 7-9): Initial Preferences ---
    {"turn": 7, "msg": "Lúc làm việc căng thẳng anh hay uống trà sữa trân châu đường đen lắm.", "expect_bg": None},
    {"turn": 8, "msg": "Anh thích vị béo ngọt của sữa tươi trân châu đường đen nhất trần đời luôn á.", "expect_bg": None},
    {"turn": 9, "msg": "Mỗi ngày anh phải uống ít nhất 1 ly trà sữa trân châu thì mới code nổi.", "expect_bg": "Batch 3: Trích xuất sở thích uống trà sữa trân châu"},

    # --- BATCH 4 (Turns 10-12): Preference Conflict (CONTRADICT) + Auto-Summarize Turn 10 ---
    {"turn": 10, "msg": "Dạo này anh đi khám sức khỏe, bác sĩ bảo đường huyết hơi cao rồi em ơi.", "expect_bg": "Auto-Summarize #1 (Turn 10)"},
    {"turn": 11, "msg": "Anh quyết định cai hoàn toàn trà sữa rồi, từ nay chuyển sang uống matcha không đường.", "expect_bg": None},
    {"turn": 12, "msg": "Nhớ nhé, anh đã bỏ trà sữa rồi và giờ chỉ uống matcha nguyên chất thanh mát thôi.", "expect_bg": "Batch 4: CONTRADICT -> Xóa trà sữa, ghi matcha không đường"},

    # --- BATCH 5 (Turns 13-15): Duplicate Testing (DUPLICATE) ---
    {"turn": 13, "msg": "Hôm nay anh vừa tự pha một ly matcha không đường uống nè, thanh đạm dễ chịu thật.", "expect_bg": None},
    {"turn": 14, "msg": "Đúng là chuyển sang matcha không đường tốt cho cơ thể hơn hẳn trà sữa.", "expect_bg": None},
    {"turn": 15, "msg": "Anh mê vị đắng thanh của matcha nguyên chất này mất rồi em ạ.", "expect_bg": "Batch 5: DUPLICATE -> Bỏ qua không lưu trùng matcha"},

    # --- BATCH 6 (Turns 16-18): Shared Memories / Mutual Promises ---
    {"turn": 16, "msg": "Dạo này làm việc áp lực quá, anh muốn đi đâu đó thư giãn.", "expect_bg": None},
    {"turn": 17, "msg": "Sau này khi anh hoàn thành xong dự án lớn, Chisa đi ngắm biển Nha Trang cùng anh nhé?", "expect_bg": None},
    {"turn": 18, "msg": "Nhất trí nhé, đó là lời hứa của hai đứa mình đấy!", "expect_bg": "Batch 6: Trích xuất lời hứa cùng đi ngắm biển Nha Trang"},

    # --- BATCH 7 (Turns 19-21): Small Talk Filtering (None) + Auto-Summarize Turn 20 ---
    {"turn": 19, "msg": "Thời tiết chỗ em hôm nay thế nào rồi Chisa?", "expect_bg": None},
    {"turn": 20, "msg": "Em ăn tối chưa vậy?", "expect_bg": "Auto-Summarize #2 (Turn 20)"},
    {"turn": 21, "msg": "Chúc em một buổi tối thật vui vẻ và bình yên nhé Chía tròn.", "expect_bg": "Batch 7: Bỏ qua (None) vì chỉ là small-talk xã giao"},

    # --- BATCH 8 (Turns 22-24): Career Progression Conflict (CONTRADICT) ---
    {"turn": 22, "msg": "Anh đang chuẩn bị nộp CV ứng tuyển vào vị trí Senior AI Engineer bên Vingroup.", "expect_bg": None},
    {"turn": 23, "msg": "Anh vừa hoàn thành vòng phỏng vấn kỹ thuật hóc búa với CTO rồi nè.", "expect_bg": None},
    {"turn": 24, "msg": "Oa Chisa ơi, anh vừa nhận được thư chúc mừng trúng tuyển chính thức của Vingroup rồi!", "expect_bg": "Batch 8: CONTRADICT -> Cập nhật đỗ chính thức vào Vingroup"},

    # --- BATCH 9 (Turns 25-27): Independent Co-existing Preferences (KEEP_BOTH) ---
    {"turn": 25, "msg": "Ngoài lập trình AI ra, anh còn có sở thích tự làm bánh ngọt vào cuối tuần nữa.", "expect_bg": None},
    {"turn": 26, "msg": "Anh hay làm bánh kem dâu tây và bánh su kem cho gia đình ăn.", "expect_bg": None},
    {"turn": 27, "msg": "Hôm nào anh làm bánh mang cho Chisa nếm thử nha.", "expect_bg": "Batch 9: KEEP_BOTH -> Lưu thêm sở thích làm bánh ngọt song song với matcha"},

    # --- BATCH 10 (Turns 28-30): E2E Recall & Memory Retrieval + Auto-Summarize Turn 30 ---
    {"turn": 28, "msg": "Em có nhớ hiện tại anh thích uống gì và đã bỏ món gì rồi không?", "expect_bg": "Verify Recall Sở thích (Matcha / Đã bỏ trà sữa)"},
    {"turn": 29, "msg": "Thế còn tin vui công việc gần đây nhất của anh là gì, em còn nhớ không?", "expect_bg": "Verify Recall Công việc (Đỗ Senior AI Engineer Vingroup)"},
    {"turn": 30, "msg": "Hai đứa mình đã có lời hứa đi đâu cùng nhau nhỉ?", "expect_bg": "Verify Recall Lời hứa (Đi ngắm biển Nha Trang) + Auto-Summarize #3"},
]

async def run_30_turns_test():
    test_user_id = f"test_e2e_30turns_{uuid.uuid4().hex[:6]}"
    user_uuid = normalize_user_id(test_user_id)
    chat_engine = container.chat_engine
    memory_extractor = container.memory_extractor

    print("=" * 80)
    print("🚀 BẮT ĐẦU CHẠY TOÀN DIỆN 30 TEST CASES HỘI THOẠI CHO CHISA AI")
    print(f"👤 Test User ID : {test_user_id}")
    print(f"🔑 User UUID    : {user_uuid}")
    print("=" * 80)

    # Initialize user & conversation in PostgreSQL
    async with AsyncSessionFactory() as session:
        user_repo = SqlAlchemyUserRepository(session)
        conv_repo = SqlAlchemyConversationRepository(session)
        await user_repo.get_or_create_user(user_uuid)
        conv_id = await conv_repo.get_or_create_conversation(user_uuid)
        await session.commit()

    start_time = time.time()

    for idx, item in enumerate(TEST_SCENARIO_TURNS, 1):
        turn_num = item["turn"]
        user_msg = item["msg"]
        expect_bg = item["expect_bg"]

        print(f"\n💬 [LƯỢT {turn_num:02d}/30] ──────────────────────────────────────────────────")
        print(f"  👤 Senpai: \"{user_msg}\"")
        if expect_bg:
            print(f"  🎯 Mục tiêu nền: {expect_bg}")

        trace_id = pipeline_tracker.start_trace(
            user_id=test_user_id,
            message=user_msg,
            pipeline="ChatPipeline",
            source="web"
        )

        async with AsyncSessionFactory() as session:
            reply_text, emotions = await chat_engine.chat(
                session=session,
                user_id=test_user_id,
                user_message=user_msg
            )
            await session.commit()

        # Display Chisa response cleanly
        short_reply = reply_text.replace("\n", " ")
        if len(short_reply) > 120:
            short_reply = short_reply[:120] + "..."
        print(f"  🌸 Chisa : \"{short_reply}\"")

        # Give background tasks (3-turn batch extract / 10-turn auto summarize) time to complete
        if turn_num % 3 == 0 or turn_num % 10 == 0:
            print("  ⏳ Chờ 3.5s để tác vụ chạy ngầm hoàn tất...")
            await asyncio.sleep(3.5)
        else:
            await asyncio.sleep(0.5)

        pipeline_tracker.end_trace(
            response_text=reply_text,
            emotions=emotions,
            status="success"
        )

    total_time = round(time.time() - start_time, 2)
    print("\n" + "=" * 80)
    print(f"🎉 HOÀN THÀNH TOÀN BỘ 30 LƯỢT CHAT TRONG {total_time}s")
    print("=" * 80)

    # ──────────────────────────────────────────────────────────────────────────
    # VERIFICATION 1: CHECK QDRANT VECTOR DB STORED MEMORIES
    # ──────────────────────────────────────────────────────────────────────────
    print("\n🔍 1. KIỂM TRA TOÀN BỘ KÝ ỨC ĐÃ ĐƯỢC LƯU TRONG QDRANT VECTOR DB:")
    all_memories_query = await memory_extractor.embedder.embed_text("thông tin cá nhân và sở thích của senpai", prefix="query: ")
    qdrant_results = await memory_extractor.vector_store.search_by_user(
        collection="memories",
        query_vector=all_memories_query,
        user_id=test_user_id,
        limit=20,
        score_threshold=0.0
    )

    print(f"  👉 Tổng số Ký ức bền vững đang có trong Qdrant: {len(qdrant_results)} facts")
    for m in qdrant_results:
        p = m.get("payload", {})
        print(f"     • [{p.get('memory_type')}] (⭐ {p.get('importance_score', 0):.2f}) (Sim: {m.get('score', 0):.3f}): \"{p.get('text_content')}\"")

    # ──────────────────────────────────────────────────────────────────────────
    # VERIFICATION 2: CHECK AUTO-SUMMARIZE IN POSTGRESQL
    # ──────────────────────────────────────────────────────────────────────────
    print("\n🔍 2. KIỂM TRA BẢN AUTO-SUMMARIZE TRONG POSTGRESQL (CỘT SUMMARY):")
    async with AsyncSessionFactory() as session:
        conv_repo = SqlAlchemyConversationRepository(session)
        latest_summary = await conv_repo.get_latest_summary(user_uuid, conv_id)
        print(f"  👉 Bản tóm tắt cuộc trò chuyện hợp nhất:\n     \"{latest_summary}\"")

    print("\n" + "=" * 80)
    print("✅ TOÀN BỘ TEST CASE ĐÃ HOÀN TẤT VÀ SẴN SÀNG ĐỂ KIỂM TRA TRÊN VISUALIZER!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_30_turns_test())
