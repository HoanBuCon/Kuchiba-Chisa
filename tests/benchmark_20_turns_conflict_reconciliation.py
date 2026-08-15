"""
================================================================================
CHISA AI - 20-TURN MEMORY CONFLICT & BATCH RECONCILIATION BENCHMARK SUITE
================================================================================
Benchmark Objective:
1. Multi-domain Conflict Stress Testing (Career, Tech Stack, Habits, Pets, Travel).
2. Verification of Batched Reconciliation (Single LLM Call for multiple candidate checks).
3. Verification of Vector DB Consistency (Old points deleted on CONTRADICT, duplicates skipped).
4. End-to-End Recall Accuracy on Final Turns (19 & 20).
================================================================================
"""

import sys
import os

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

# 20 Curated Conflict Benchmark Test Cases
BENCHMARK_20_TURNS = [
    # ── BATCH 1 (Turns 1-3): Initial Identity & Career in Hanoi ──
    {
        "turn": 1,
        "msg": "Chào em Chisa, anh tên là Nam, hiện đang làm Backend Developer tại Hà Nội nhé.",
        "category": "Identity & Location",
        "expected_action": "Initial Insert"
    },
    {
        "turn": 2,
        "msg": "Công ty hiện tại của anh là FPT Software, anh chuyên lập trình Java Spring Boot.",
        "category": "Job & Tech Stack",
        "expected_action": "Initial Insert"
    },
    {
        "turn": 3,
        "msg": "Dạo này dự án Java ở FPT khá bận rộn nhưng anh vẫn thích nghiên cứu thêm kiến trúc hệ thống.",
        "category": "Batch 1 Summary",
        "expected_action": "Batch 1 Extraction -> Lưu: Nam, Backend Dev FPT Software Hà Nội, Java Spring Boot"
    },

    # ── BATCH 2 (Turns 4-6): Initial Habits & Pet ──
    {
        "turn": 4,
        "msg": "Mỗi buổi sáng thức dậy anh đều phải uống một ly cà phê đen đá thật đậm đặc không đường mới tỉnh táo được.",
        "category": "Beverage Habit",
        "expected_action": "Initial Insert"
    },
    {
        "turn": 5,
        "msg": "Ở nhà anh đang nuôi một bé mèo mướp rất ngoan tên là Miu.",
        "category": "Pet",
        "expected_action": "Initial Insert"
    },
    {
        "turn": 6,
        "msg": "Mỗi khi anh ngồi code ở bàn làm việc là bé mèo Miu lại chạy lại dụi đầu đòi cưng nựng.",
        "category": "Batch 2 Summary",
        "expected_action": "Batch 2 Extraction -> Lưu: Uống cà phê đen đá mỗi sáng, Nuôi mèo mướp tên Miu"
    },

    # ── BATCH 3 (Turns 7-9): CONFLICT 1 - Stomach Ache -> Stop Coffee, Switch to Chamomile Tea (CONTRADICT) + Adopt Dog (KEEP_BOTH) ──
    {
        "turn": 7,
        "msg": "Dạo này anh đi nội soi dạ dày, bác sĩ cảnh báo anh bị viêm loét dạ dày vì uống quá nhiều cà phê đen đậm đặc.",
        "category": "Health Condition",
        "expected_action": "Context Building"
    },
    {
        "turn": 8,
        "msg": "Bác sĩ cấm tiệt cà phê, nên anh đã bỏ hẳn cà phê đen rồi, từ nay mỗi sáng chuyển sang uống trà hoa cúc mật ong cho lành tính.",
        "category": "Beverage Habit CONTRADICT",
        "expected_action": "CONTRADICT -> Xóa ký ức cà phê đen đá, Lưu ký ức mới: Uống trà hoa cúc mật ong"
    },
    {
        "turn": 9,
        "msg": "Tuần này anh còn vừa nhận nuôi thêm một chú cún Poodle nhỏ rất lanh lợi tên là Lu nữa nè Chisa.",
        "category": "Pet KEEP_BOTH",
        "expected_action": "Batch 3 Extraction -> CONTRADICT (Trà hoa cúc > Cà phê) + KEEP_BOTH (Nuôi thêm cún Lu song song mèo Miu)"
    },

    # ── BATCH 4 (Turns 10-12): CONFLICT 2 - Chamomile Tea (DUPLICATE) + Move to HCMC & Join VNG (CONTRADICT) ──
    {
        "turn": 10,
        "msg": "Uống trà hoa cúc mật ong vào mỗi sáng thấy dạ dày êm hẳn và tinh thần thoải mái ghê.",
        "category": "Beverage DUPLICATE",
        "expected_action": "DUPLICATE -> Bỏ qua không lưu lặp lại trà hoa cúc"
    },
    {
        "turn": 11,
        "msg": "Anh vừa đưa ra một quyết định lớn trong đời: Anh đã nộp đơn xin nghỉ việc ở FPT Software Hà Nội rồi.",
        "category": "Career CONTRADICT",
        "expected_action": "Context Building"
    },
    {
        "turn": 12,
        "msg": "Anh quyết định chuyển hẳn vào TP.HCM sinh sống và chính thức nhận việc vị trí AI Engineer tại VNG!",
        "category": "Career & Location CONTRADICT",
        "expected_action": "Batch 4 Extraction -> CONTRADICT (Xóa FPT Hà Nội -> Lưu: AI Engineer tại VNG ở TP.HCM) + DUPLICATE (Trà hoa cúc)"
    },

    # ── BATCH 5 (Turns 13-15): CONFLICT 3 - Tech Stack Switch (CONTRADICT) + Send Cat to Mother (CONTRADICT) ──
    {
        "turn": 13,
        "msg": "Sang VNG làm mảng AI nên anh bỏ hẳn Java Spring Boot rồi, giờ anh chuyên tâm lập trình Python và Rust.",
        "category": "Tech Stack CONTRADICT",
        "expected_action": "CONTRADICT -> Xóa Java Spring Boot, Lưu: Chuyên Python và Rust"
    },
    {
        "turn": 14,
        "msg": "Vì chuyển nhà vào Sài Gòn xa xôi nên anh đã gửi bé mèo Miu về quê cho mẹ chăm sóc, giờ trong này anh chỉ nuôi mỗi chú cún Lu thôi.",
        "category": "Pet Status CONTRADICT",
        "expected_action": "CONTRADICT -> Cập nhật: Mèo Miu đã gửi về quê, hiện chỉ nuôi cún Lu ở Sài Gòn"
    },
    {
        "turn": 15,
        "msg": "Mỗi tối đi làm ở VNG về, có chú cún Lu đón ở cửa phòng trọ Sài Gòn thấy ấm áp hẳn.",
        "category": "Batch 5 Summary",
        "expected_action": "Batch 5 Extraction -> Batched 1 LLM Call giải quyết 2 CONTRADICT cùng lúc"
    },

    # ── BATCH 6 (Turns 16-18): CONFLICT 4 - Travel Plan Changed (CONTRADICT) + New Sport Habit (KEEP_BOTH) ──
    {
        "turn": 16,
        "msg": "Trước đây anh tính hè này đi du lịch Tokyo Nhật Bản, nhưng công việc mới bận quá nên anh hủy chuyến đi Nhật rồi.",
        "category": "Travel Plan CONTRADICT",
        "expected_action": "CONTRADICT -> Hủy kế hoạch đi Nhật Bản"
    },
    {
        "turn": 17,
        "msg": "Anh đổi kế hoạch sang tháng sau đi phượt Đà Lạt leo núi Langbiang vào cuối tuần cho gần và tiện.",
        "category": "Travel Plan Update",
        "expected_action": "Lưu kế hoạch mới: Phượt Đà Lạt leo núi Langbiang"
    },
    {
        "turn": 18,
        "msg": "Dạo này ở Sài Gòn anh còn hình thành thói quen chạy bộ 5km mỗi buổi chiều ở công viên để rèn luyện sức khỏe nữa.",
        "category": "Batch 6 Summary",
        "expected_action": "Batch 6 Extraction -> CONTRADICT (Đà Lạt thay vì Nhật) + KEEP_BOTH (Chạy bộ 5km chiều)"
    },

    # ── BATCH 7 (Turns 19-20): COMPREHENSIVE RECALL & RECONCILIATION ACCURACY BENCHMARK ──
    {
        "turn": 19,
        "msg": "Chisa ơi, em tổng hợp lại giúp anh: Hiện tại anh đang sống ở đâu, làm ở công ty nào với vị trí gì, viết ngôn ngữ gì và đang nuôi thú cưng nào ở cạnh anh nhé?",
        "category": "Accuracy Benchmark #1",
        "expected_action": "Verify Recall: TP.HCM (Không phải Hà Nội) | VNG AI Engineer (Không phải FPT Java) | Python & Rust (Không phải Java) | Cún Lu (Mèo Miu đã ở quê)"
    },
    {
        "turn": 20,
        "msg": "Thế còn buổi sáng anh đang duy trì uống món gì, và tháng sau anh có kế hoạch đi đâu em nhỉ?",
        "category": "Accuracy Benchmark #2",
        "expected_action": "Verify Recall: Trà hoa cúc mật ong (Đã bỏ cà phê) | Phượt Đà Lạt leo núi Langbiang (Đã hủy đi Nhật)"
    }
]


async def run_20_turns_benchmark():
    test_user_id = f"benchmark_conflict_{uuid.uuid4().hex[:6]}"
    user_uuid = normalize_user_id(test_user_id)
    chat_engine = container.chat_engine
    vector_store = container.vector_store

    print("=" * 85)
    print("🚀 BẮT ĐẦU BENCHMARK 20 CÂU HỎI ĐỐI SOÁT MÂU THUẪN KÝ ỨC (MEMORY CONFLICT RECONCILIATION)")
    print(f"👤 Test User ID : {test_user_id}")
    print(f"🔑 User UUID    : {user_uuid}")
    print("=" * 85)

    # Initialize user in PostgreSQL
    async with AsyncSessionFactory() as session:
        user_repo = SqlAlchemyUserRepository(session)
        conv_repo = SqlAlchemyConversationRepository(session)
        await user_repo.get_or_create_user(user_uuid)
        conv_id = await conv_repo.get_or_create_conversation(user_uuid)
        await session.commit()

    start_time_total = time.time()
    batch_timings = []

    for item in BENCHMARK_20_TURNS:
        turn = item["turn"]
        msg = item["msg"]
        category = item["category"]
        expected = item["expected_action"]

        print(f"\n─────────────────────────────────────────────────────────────────────────────")
        print(f"💬 [LƯỢT {turn:02d}/20] ({category})")
        print(f"👤 Senpai: {msg}")
        print(f"🎯 Kỳ vọng : {expected}")

        t0 = time.time()
        pipeline_tracker.start_trace(
            user_id=test_user_id,
            message=msg,
            pipeline="ChatPipeline",
            source="benchmark"
        )

        async with AsyncSessionFactory() as session:
            reply_text, emotions = await chat_engine.chat(
                session=session,
                user_id=test_user_id,
                user_message=msg
            )
            await session.commit()

        elapsed = time.time() - t0
        batch_timings.append(elapsed)

        print(f"🤖 Chisa : {reply_text}")
        print(f"⏱️ Thời gian phản hồi: {elapsed:.2f}s")

        # Give background asyncio tasks time to execute
        if turn % 3 == 0 or turn == 20:
            print(f"⏳ Đang đợi background batch extraction & reconciliation hoàn tất...")
            await asyncio.sleep(4.0)

    total_time = time.time() - start_time_total

    print("\n" + "=" * 85)
    print("📊 TỔNG KẾT BENCHMARK TOÀN DIỆN")
    print(f"⏱️ Tổng thời gian chạy 20 lượt: {total_time:.2f}s (Trung bình: {sum(batch_timings)/len(batch_timings):.2f}s/lượt)")
    print("=" * 85)

    # Inspect final Qdrant Vector DB memory points
    print("\n📦 KIỂM TRA DỮ LIỆU CUỐI CÙNG TRONG QDRANT VECTOR DB:")
    try:
        dummy_vector = [0.0] * 768
        stored_points = await vector_store.search_by_user(
            collection="memories",
            query_vector=dummy_vector,
            user_id=test_user_id,
            conversation_id=str(conv_id),
            limit=20,
            score_threshold=0.0
        )
        if not stored_points:
            stored_points = await vector_store.search_by_user(
                collection="memories",
                query_vector=dummy_vector,
                user_id=str(user_uuid),
                conversation_id=str(conv_id),
                limit=20,
                score_threshold=0.0
            )
        print(f"📌 Tổng số ký ức đang lưu trong Qdrant: {len(stored_points)}")
        for idx, pt in enumerate(stored_points, 1):
            txt = pt.get("payload", {}).get("text_content", "")
            mtype = pt.get("payload", {}).get("memory_type", "")
            score = pt.get("payload", {}).get("importance_score", 0)
            print(f"  [{idx:02d}] ({mtype} | ⭐{score}): \"{txt}\"")

    except Exception as e:
        print(f"⚠️ Không thể truy vấn Qdrant: {e}")

    print("\n" + "=" * 85)
    print("✅ BENCHMARK HOÀN TẤT!")
    print("=" * 85)


if __name__ == "__main__":
    asyncio.run(run_20_turns_benchmark())
