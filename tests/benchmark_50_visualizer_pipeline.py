import sys, os
sys.path.insert(0, os.path.abspath('.'))
import asyncio
import json
import time
from datetime import datetime
from typing import List, Dict, Any

from app.application.dependencies import container
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

# ─────────────────────────────────────────────────────────────────────────────
# 50 PRODUCTION TESTCASES (EASY & HARD, L1/L2/L3, REWRITE, MEMORY, COMBAT)
# ─────────────────────────────────────────────────────────────────────────────
BENCHMARK_CASES: List[Dict[str, Any]] = [
    # ── NHÓM 1: Small Talk & Conversational Fast-Path (Dễ - 0 Token Bypass) ──
    {
        "id": 1,
        "category": "Small Talk (L1 Bypass)",
        "difficulty": "EASY",
        "query": "chào em chisa nhé",
        "expected_intent": "SMALL_TALK",
        "desc": "Chào hỏi thông thường có tên nhân vật"
    },
    {
        "id": 2,
        "category": "Small Talk (L1 Bypass)",
        "difficulty": "EASY",
        "query": "chào buổi sáng chisa nha",
        "expected_intent": "SMALL_TALK",
        "desc": "Chào buổi sáng tiếng Việt"
    },
    {
        "id": 3,
        "category": "Small Talk (L1 Bypass)",
        "difficulty": "EASY",
        "query": "haha vui quá đi",
        "expected_intent": "SMALL_TALK",
        "desc": "Cảm thán tiếng cười và vui vẻ"
    },
    {
        "id": 4,
        "category": "Small Talk (L1 Bypass)",
        "difficulty": "EASY",
        "query": "chuẩn luôn em",
        "expected_intent": "SMALL_TALK",
        "desc": "Đồng tình ngắn gọn"
    },
    {
        "id": 5,
        "category": "Small Talk (L1 Bypass)",
        "difficulty": "EASY",
        "query": "cảm ơn em nhiều nha",
        "expected_intent": "SMALL_TALK",
        "desc": "Cảm ơn lịch sự"
    },
    {
        "id": 6,
        "category": "Small Talk (L1 Bypass)",
        "difficulty": "EASY",
        "query": "tạm biệt em nhé, chúc em ngủ ngon",
        "expected_intent": "SMALL_TALK",
        "desc": "Lời chúc ngủ ngon và tạm biệt"
    },
    {
        "id": 7,
        "category": "Small Talk (L1 Bypass)",
        "difficulty": "EASY",
        "query": "hí hí chía chía",
        "expected_intent": "SMALL_TALK",
        "desc": "Biệt danh thân mật kết hợp tiếng cười"
    },
    {
        "id": 8,
        "category": "Small Talk (L1 Bypass)",
        "difficulty": "EASY",
        "query": "em ăn cơm chưa",
        "expected_intent": "SMALL_TALK",
        "desc": "Hỏi thăm sinh hoạt đời thường"
    },

    # ── NHÓM 2: Standalone Explicit Lore (Dễ - Fast-Path Entity Resolver) ──
    {
        "id": 9,
        "category": "Explicit Lore (L2 Fast-Path)",
        "difficulty": "EASY",
        "query": "Jiyan là ai và giữ chức vụ gì?",
        "expected_intent": "LORE",
        "desc": "Nhân vật Tướng quân Jiyan của Dạ Hành Quân"
    },
    {
        "id": 10,
        "category": "Explicit Lore (L2 Fast-Path)",
        "difficulty": "EASY",
        "query": "Vũ khí chính của Chixia là gì?",
        "expected_intent": "LORE",
        "desc": "Vũ khí súng lục của Chixia"
    },
    {
        "id": 11,
        "category": "Explicit Lore (L2 Fast-Path)",
        "difficulty": "EASY",
        "query": "Thành phố Jinzhou nằm ở khu vực nào của Huanglong?",
        "expected_intent": "LORE",
        "desc": "Địa danh thành phố Jinzhou"
    },
    {
        "id": 12,
        "category": "Explicit Lore (L2 Fast-Path)",
        "difficulty": "EASY",
        "query": "Tổ chức Black Shores có nhiệm vụ gì?",
        "expected_intent": "LORE",
        "desc": "Tổ chức Biển Đen Black Shores"
    },
    {
        "id": 13,
        "category": "Explicit Lore (L2 Fast-Path)",
        "difficulty": "EASY",
        "query": "Thảm họa The Lament là gì?",
        "expected_intent": "LORE",
        "desc": "Thảm họa diệt vong Lament"
    },
    {
        "id": 14,
        "category": "Explicit Lore (L2 Fast-Path)",
        "difficulty": "EASY",
        "query": "Sanhua có khả năng chiến đấu như thế nào?",
        "expected_intent": "LORE",
        "desc": "Khả năng chiến đấu của nữ kiếm sĩ Sanhua"
    },
    {
        "id": 15,
        "category": "Explicit Lore (L2 Fast-Path)",
        "difficulty": "EASY",
        "query": "Changli sử dụng loại vũ khí gì?",
        "expected_intent": "LORE",
        "desc": "Vũ khí kiếm đơn của mưu sĩ Changli"
    },
    {
        "id": 16,
        "category": "Explicit Lore (L2 Fast-Path)",
        "difficulty": "EASY",
        "query": "Bác sĩ Baizhi nghiên cứu về sinh vật gì?",
        "expected_intent": "LORE",
        "desc": "Sinh vật Remnant You'tan của Baizhi"
    },
    {
        "id": 17,
        "category": "Explicit Lore (L2 Fast-Path)",
        "difficulty": "EASY",
        "query": "Thừa Tiêu Sơn Mt. Firmament có bí mật gì?",
        "expected_intent": "LORE",
        "desc": "Địa danh núi Thừa Tiêu Mt. Firmament"
    },
    {
        "id": 18,
        "category": "Explicit Lore (L2 Fast-Path)",
        "difficulty": "EASY",
        "query": "Tướng quân Geshu Lin đã làm gì trong trận chiến Norfall Barrens?",
        "expected_intent": "LORE",
        "desc": "Tướng quân tiền nhiệm Geshu Lin"
    },

    # ── NHÓM 3: Zero-Entity Combat & Implicit World Lore (Khó - L3 Vector Classifier) ──
    {
        "id": 19,
        "category": "Combat & Zero-Entity Lore (L3 Vector)",
        "difficulty": "HARD",
        "query": "Làm sao để parry phản đòn khi quái vật sáng mắt đỏ?",
        "expected_intent": "LORE",
        "desc": "Cơ chế chiến đấu parry phản đòn không có tên riêng"
    },
    {
        "id": 20,
        "category": "Combat & Zero-Entity Lore (L3 Vector)",
        "difficulty": "HARD",
        "query": "Có bao nhiêu thuộc tính nguyên tố và cơ chế khắc chế ra sao?",
        "expected_intent": "LORE",
        "desc": "Cơ chế khắc chế 6 hệ nguyên tố"
    },
    {
        "id": 21,
        "category": "Combat & Zero-Entity Lore (L3 Vector)",
        "difficulty": "HARD",
        "query": "Hiện tượng mưa ngược có nguồn gốc và tác động thế nào?",
        "expected_intent": "LORE",
        "desc": "Hiện tượng Mưa ngược Retroact Rain không kèm tên tiếng Anh"
    },
    {
        "id": 22,
        "category": "Combat & Zero-Entity Lore (L3 Vector)",
        "difficulty": "HARD",
        "query": "Cơ chế nạp năng lượng Resonance Liberation hoạt động ra sao?",
        "expected_intent": "LORE",
        "desc": "Cơ chế nạp năng lượng nộ trong combat"
    },
    {
        "id": 23,
        "category": "Combat & Zero-Entity Lore (L3 Vector)",
        "difficulty": "HARD",
        "query": "Thiết bị điều khiển dòng thời gian trên hòn đảo cô lập là gì?",
        "expected_intent": "LORE",
        "desc": "Thiết bị Chronosorter (mô tả gián tiếp)"
    },
    {
        "id": 24,
        "category": "Combat & Zero-Entity Lore (L3 Vector)",
        "difficulty": "HARD",
        "query": "Dấu ấn trên cơ thể các chiến binh Resonator có ý nghĩa gì?",
        "expected_intent": "LORE",
        "desc": "Dấu ấn Tacet Mark trên cơ thể người biến dị"
    },
    {
        "id": 25,
        "category": "Combat & Zero-Entity Lore (L3 Vector)",
        "difficulty": "HARD",
        "query": "Sự khác biệt giữa Tacet Discord thông thường và Dị Loại Thần Ma là gì?",
        "expected_intent": "LORE",
        "desc": "Phân cấp quái vật và Threnodian"
    },
    {
        "id": 26,
        "category": "Combat & Zero-Entity Lore (L3 Vector)",
        "difficulty": "HARD",
        "query": "Loại khoáng sản phát sáng màu xanh băng ở mỏ sâu là gì?",
        "expected_intent": "LORE",
        "desc": "Khoáng sản Lampylumen ở mỏ Tiger's Maw"
    },
    {
        "id": 27,
        "category": "Combat & Zero-Entity Lore (L3 Vector)",
        "difficulty": "HARD",
        "query": "Bản chất của tàn dư Echo mà các chiến binh thu thập là gì?",
        "expected_intent": "LORE",
        "desc": "Cơ chế hấp thụ tần số Echo của quái vật"
    },
    {
        "id": 28,
        "category": "Combat & Zero-Entity Lore (L3 Vector)",
        "difficulty": "HARD",
        "query": "Tổ chức cuồng tín chủ trương đẩy nhanh thảm họa diệt vong là ai?",
        "expected_intent": "LORE",
        "desc": "Tổ chức Tàn Tinh Hội Fractsidus (mô tả gián tiếp)"
    },

    # ── NHÓM 4: Multi-Turn Context Chaining & Coreference (Khó - Micro LLM Flash Rewrite) ──
    {
        "id": 29,
        "category": "Multi-Turn Context (Pair 1 - Context N-1)",
        "difficulty": "EASY",
        "query": "Kể cho anh nghe về vị tướng Jiyan lãnh đạo Midnight Rangers",
        "expected_intent": "LORE",
        "desc": "Lượt 1: Tạo ngữ cảnh về Jiyan"
    },
    {
        "id": 30,
        "category": "Multi-Turn Coreference (Pair 1 - Rewrite N)",
        "difficulty": "HARD",
        "query": "Vũ khí của anh ấy là gì?",
        "expected_intent": "LORE",
        "desc": "Lượt 2: Kế thừa 'anh ấy' -> Tướng quân Jiyan"
    },
    {
        "id": 31,
        "category": "Multi-Turn Context (Pair 2 - Context N-1)",
        "difficulty": "EASY",
        "query": "Thánh Thú Jué là sinh vật như thế nào?",
        "expected_intent": "LORE",
        "desc": "Lượt 1: Tạo ngữ cảnh về Thánh Thú Jue"
    },
    {
        "id": 32,
        "category": "Multi-Turn Coreference (Pair 2 - Rewrite N)",
        "difficulty": "HARD",
        "query": "Con rồng đó xuất hiện khi nào?",
        "expected_intent": "LORE",
        "desc": "Lượt 2: Kế thừa 'con rồng đó' -> Thánh Thú Jue"
    },
    {
        "id": 33,
        "category": "Multi-Turn Context (Pair 3 - Context N-1)",
        "difficulty": "EASY",
        "query": "Kể về hòn đảo Black Shores bí ẩn",
        "expected_intent": "LORE",
        "desc": "Lượt 1: Tạo ngữ cảnh về Black Shores"
    },
    {
        "id": 34,
        "category": "Multi-Turn Coreference (Pair 3 - Rewrite N)",
        "difficulty": "HARD",
        "query": "Ở nơi đó có những ai cai quản?",
        "expected_intent": "LORE",
        "desc": "Lượt 2: Kế thừa 'nơi đó' -> Black Shores"
    },
    {
        "id": 35,
        "category": "Multi-Turn Context (Pair 4 - Context N-1)",
        "difficulty": "EASY",
        "query": "Thảm họa Lament đã tàn phá thế giới ra sao?",
        "expected_intent": "LORE",
        "desc": "Lượt 1: Tạo ngữ cảnh về Lament"
    },
    {
        "id": 36,
        "category": "Multi-Turn Coreference (Pair 4 - Rewrite N)",
        "difficulty": "HARD",
        "query": "Tại sao lại như vậy?",
        "expected_intent": "LORE",
        "desc": "Lượt 2: Kế thừa nguyên nhân thảm họa Lament"
    },
    {
        "id": 37,
        "category": "Multi-Turn Context (Pair 5 - Context N-1)",
        "difficulty": "EASY",
        "query": "Cô nàng cảnh vệ Chixia có tuyệt chiêu gì?",
        "expected_intent": "LORE",
        "desc": "Lượt 1: Tạo ngữ cảnh về Chixia"
    },
    {
        "id": 38,
        "category": "Multi-Turn Coreference (Pair 5 - Rewrite N)",
        "difficulty": "HARD",
        "query": "Thế còn kỹ năng nộ thì sao?",
        "expected_intent": "LORE",
        "desc": "Lượt 2: Kế thừa kỹ năng nộ của Chixia"
    },

    # ── NHÓM 5: Personal Memory & Fact Ingestion (Trung bình - Memory Storage & Query) ──
    {
        "id": 39,
        "category": "Memory Ingestion",
        "difficulty": "MEDIUM",
        "query": "Tên thật của anh là Minh, anh đang làm lập trình viên AI ở Hà Nội nhé em",
        "expected_intent": "MEMORY",
        "desc": "Cung cấp tên thật, nghề nghiệp, nơi sống"
    },
    {
        "id": 40,
        "category": "Memory Ingestion",
        "difficulty": "MEDIUM",
        "query": "Ngày mai anh có buổi phỏng vấn xin việc quan trọng lúc 9h sáng",
        "expected_intent": "MEMORY",
        "desc": "Lịch trình sự kiện quan trọng sắp tới"
    },
    {
        "id": 41,
        "category": "Memory Ingestion",
        "difficulty": "MEDIUM",
        "query": "Anh bị dị ứng với hải sản và không ăn được tôm cua đâu nhé",
        "expected_intent": "MEMORY",
        "desc": "Sở thích và kiêng kị ăn uống"
    },
    {
        "id": 42,
        "category": "Memory Retrieval",
        "difficulty": "MEDIUM",
        "query": "Hôm trước anh đã nói với em về kế hoạch cuối tuần chưa nhỉ?",
        "expected_intent": "MEMORY",
        "desc": "Truy vấn ký ức về cuộc trò chuyện trước"
    },
    {
        "id": 43,
        "category": "Memory Retrieval",
        "difficulty": "MEDIUM",
        "query": "Em có nhớ công việc hiện tại của anh là gì không?",
        "expected_intent": "MEMORY",
        "desc": "Kiểm tra ký ức về nghề nghiệp Senpai"
    },
    {
        "id": 44,
        "category": "Memory Ingestion",
        "difficulty": "MEDIUM",
        "query": "Anh rất thích nghe nhạc Lofi vào ban đêm khi làm việc",
        "expected_intent": "MEMORY",
        "desc": "Gu âm nhạc và thói quen sinh hoạt"
    },

    # ── NHÓM 6: Compound Multi-Intent & Deep Conversational (Khó - Phức hợp) ──
    {
        "id": 45,
        "category": "Compound Query (Greeting + Lore)",
        "difficulty": "HARD",
        "query": "Chào em Chisa nhé! Hôm nay trời lạnh thật đấy, à mà vị tướng Jiyan dùng vũ khí gì thế em?",
        "expected_intent": "LORE",
        "desc": "Câu ghép: Chào hỏi + Đệm thời tiết + Hỏi Lore Jiyan"
    },
    {
        "id": 46,
        "category": "Dual-Intent (Memory + Conversational)",
        "difficulty": "HARD",
        "query": "Anh đang chuẩn bị mở một quán trà nhỏ ở Hà Nội, vừa vui vừa lo không biết có thành công không em ạ",
        "expected_intent": "CONVERSATIONAL",
        "desc": "Vừa chia sẻ dự định kinh doanh vừa tâm sự cảm xúc lo lắng"
    },
    {
        "id": 47,
        "category": "Deep Conversational / Philosophy",
        "difficulty": "MEDIUM",
        "query": "Theo em thì trong cuộc sống này điều gì là quan trọng nhất giữa người với người?",
        "expected_intent": "CONVERSATIONAL",
        "desc": "Hỏi quan điểm triết lý sống và sự gắn kết"
    },
    {
        "id": 48,
        "category": "Conversational Empathy",
        "difficulty": "MEDIUM",
        "query": "Hôm nay anh đi làm về muộn và cảm thấy mệt mỏi quá, Chisa có thể động viên anh được không?",
        "expected_intent": "CONVERSATIONAL",
        "desc": "Tìm kiếm sự an ủi và động viên tinh thần"
    },
    {
        "id": 49,
        "category": "Compound Query (Transition + Lore)",
        "difficulty": "HARD",
        "query": "Tiện thể cho anh hỏi luôn là thung lũng Gorges of Spirits có nguy hiểm không em?",
        "expected_intent": "LORE",
        "desc": "Câu hỏi kèm từ nối chuyển tiếp 'Tiện thể cho anh hỏi'"
    },
    {
        "id": 50,
        "category": "System Action (Summary)",
        "difficulty": "MEDIUM",
        "query": "Tóm tắt lại những điều quan trọng mà chúng ta vừa trao đổi từ nãy đến giờ nhé",
        "expected_intent": "SYSTEM_ACTION",
        "desc": "Lệnh tóm tắt nội dung hội thoại"
    }
]

# ─────────────────────────────────────────────────────────────────────────────
# BENCHMARK RUNNER & VISUALIZER RECORDER
# ─────────────────────────────────────────────────────────────────────────────
async def run_visualizer_benchmark():
    os.makedirs("tests/logs", exist_ok=True)
    log_file_path = "tests/logs/benchmark_50_visualizer_pipeline.log"
    report_file_path = "tests/logs/benchmark_50_report.json"
    
    log_file = open(log_file_path, "w", encoding="utf-8")
    
    def log_print(msg: str):
        print(msg)
        log_file.write(msg + "\n")
        log_file.flush()

    log_print("=" * 95)
    log_print(f"🚀 BẮT ĐẦU CHẠY BENCHMARK 50 CÂU HỎI PRODUCTION TRACE VÀO VISUALIZER")
    log_print(f"⏰ Thời gian khởi chạy: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"🌐 Visualizer Dashboard: http://localhost:8000/visualizer")
    log_print("=" * 95)

    chat_engine = container.chat_engine
    user_id = f"benchmark_senpai_50_{int(time.time())}"
    username = "Senpai (Visualizer Benchmark)"

    results = []
    total_start_time = time.time()
    pass_count = 0

    for idx, case in enumerate(BENCHMARK_CASES, 1):
        q_id = case["id"]
        category = case["category"]
        diff = case["difficulty"]
        query = case["query"]
        expected_intent = case["expected_intent"]
        desc = case["desc"]

        log_print(f"\n[{idx:02d}/50] ──────────────────────────────────────────────────────────────────────────")
        log_print(f"  • Nhóm       : {category} [{diff}]")
        log_print(f"  • Mô tả      : {desc}")
        log_print(f"  • Câu hỏi    : \"{query}\"")

        start_t = time.time()
        
        # 1. Start pipeline trace (pushes to Visualizer & Redis)
        trace_id = pipeline_tracker.start_trace(
            user_id=user_id,
            message=query,
            pipeline="production",
            source="benchmark",
            username=username
        )

        try:
            async with AsyncSessionFactory() as session:
                reply, emotions = await chat_engine.chat(
                    session=session,
                    user_id=user_id,
                    user_message=query
                )
                await session.commit()
            
            elapsed_ms = (time.time() - start_t) * 1000

            # 2. Complete trace with reply
            pipeline_tracker.end_trace(
                response_text=reply,
                emotions=emotions,
                status="success"
            )

            # 3. Retrieve trace execution details from tracker
            traces = pipeline_tracker.get_traces()
            current_trace = next((t for t in traces if t.get("id") == trace_id), {})
            steps = current_trace.get("steps", [])

            # Extract Intent Stage details
            intent_step = next((s for s in steps if s.get("name") in ("intent_classification", "intent_stage")), {})
            intent_data = intent_step.get("data", {})
            actual_intents = intent_data.get("intents", [])
            routing_method = intent_data.get("routing_method", "UNKNOWN")
            rewrite_method = intent_data.get("rewrite_method", "FAST_PATH")
            rewritten_query = intent_data.get("rewritten_query", "")
            confidence = intent_data.get("confidence", 0.0)

            # Evaluate Intent Match
            is_intent_matched = (expected_intent in actual_intents)
            if is_intent_matched:
                pass_count += 1
                status_icon = "✅ PASS"
            else:
                status_icon = "⚠️ DIFF"

            log_print(f"  • Kết quả    : {status_icon} | Intents={actual_intents} (Kỳ vọng: {expected_intent})")
            log_print(f"  • Định tuyến : Method={routing_method} | Rewrite={rewrite_method} | Conf={confidence*100:.1f}%")
            if rewritten_query and rewritten_query != query:
                log_print(f"  • Rewrite Q  : \"{rewritten_query}\"")
            log_print(f"  • Chisa phản hồi ({elapsed_ms:.1f}ms): \"{reply[:75]}...\"")
            log_print(f"  • Trace ID   : {trace_id}")

            results.append({
                "id": q_id,
                "category": category,
                "difficulty": diff,
                "query": query,
                "expected_intent": expected_intent,
                "actual_intents": actual_intents,
                "is_match": is_intent_matched,
                "routing_method": routing_method,
                "rewrite_method": rewrite_method,
                "rewritten_query": rewritten_query,
                "latency_ms": round(elapsed_ms, 2),
                "reply_snippet": reply[:100],
                "trace_id": trace_id
            })

        except Exception as err:
            elapsed_ms = (time.time() - start_t) * 1000
            pipeline_tracker.end_trace(
                status="failed",
                error=str(err)
            )
            log_print(f"  ❌ ERROR ({elapsed_ms:.1f}ms): {err}")
            results.append({
                "id": q_id,
                "category": category,
                "difficulty": diff,
                "query": query,
                "expected_intent": expected_intent,
                "actual_intents": [],
                "is_match": False,
                "error": str(err),
                "latency_ms": round(elapsed_ms, 2),
                "trace_id": trace_id
            })

    total_elapsed = time.time() - total_start_time
    avg_latency = (total_elapsed / len(BENCHMARK_CASES)) * 1000

    log_print("\n" + "=" * 95)
    log_print("📊 TỔNG HỢP HIỆU NĂNG BENCHMARK 50 CÂU HỎI")
    log_print("=" * 95)
    log_print(f"  🎯 Độ chính xác Intent  : {pass_count}/{len(BENCHMARK_CASES)} ({pass_count/len(BENCHMARK_CASES)*100:.1f}%)")
    log_print(f"  ⏱️ Tổng thời gian chạy   : {total_elapsed:.2f}s ({total_elapsed/60:.1f} phút)")
    log_print(f"  ⚡ Độ trễ TB mỗi query  : {avg_latency:.1f}ms")
    log_print(f"  📁 File Log chi tiết    : {log_file_path}")
    log_print(f"  📁 File JSON Báo cáo   : {report_file_path}")
    log_print("=" * 95)
    log_print(f"🎉 ĐÃ PUSH TOÀN BỘ 50 TRACE LÊN REDIS VÀ IN-MEMORY TRACKER!")
    log_print(f"👉 Mở trình duyệt tại: http://localhost:8000/visualizer để xem cây Pipeline Tree của từng câu hỏi!")
    log_print("=" * 95)

    # Save JSON report
    with open(report_file_path, "w", encoding="utf-8") as rf:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_cases": len(BENCHMARK_CASES),
            "pass_count": pass_count,
            "accuracy_pct": round(pass_count / len(BENCHMARK_CASES) * 100, 2),
            "total_duration_sec": round(total_elapsed, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "results": results
        }, rf, ensure_ascii=False, indent=2)

    log_file.close()

if __name__ == "__main__":
    asyncio.run(run_visualizer_benchmark())
