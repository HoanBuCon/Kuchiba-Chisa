# -*- coding: utf-8 -*-
"""
Script: Generate Full-Pipeline Traces for Visualizer Dashboard
Populates 10 comprehensive, high-fidelity traces covering all 10 Stages,
including Vector DB Thinking Loop, Web Search Loop, Hybrid Search, Fast-Path,
Memory Retrieval, Deep CoT Reasoning, Emotion Delta, and Background Tasks.

Usage:
  python scripts/generate_visualizer_traces.py
Then open http://localhost:8000/visualizer to inspect all traces!
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Safe UTF-8 console output for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import asyncio
import time
from app.infrastructure.logging.pipeline_tracker import pipeline_tracker, StepCategory
from app.domain.services.tools.web_search import web_search_trace_payload


async def generate_10_full_pipeline_traces():
    print("=" * 80)
    print("🚀 GENERATING 10 FULL-PIPELINE TRACES FOR VISUALIZER DASHBOARD...")
    print("=" * 80)

    # ──────────────────────────────────────────────────────────────────────────
    # CASE 1: [VECTOR RAG + LOOP THINKING] Vector Lore Retrieval with Auto-Satisfy
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[1/10] Generating Trace: Vector Lore Retrieval + Loop Thinking (Qdrant)...")
    trace_id_1 = pipeline_tracker.start_trace(
        user_id="user_senpai_honami",
        message="Cho anh hỏi chiêu thức và vũ khí của Tướng quân Jiyan?",
        pipeline="chat_pipeline_v2",
        source="web"
    )

    pipeline_tracker.start_stage("stage_1_init", title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh", data={
        "turn_index": 4, "user_id": "user_senpai_honami", "status": "success", "interaction_count": 4
    })
    pipeline_tracker.start_stage("stage_2_intent", title="Stage 2: [INTENT] Phân tích Ý định & Viết lại Truy vấn", data={
        "intents": ["LORE"], "detected_intents": ["LORE"], "routing_method": "LLM_ROUTER",
        "rewrite_method": "LLM_FLASH", "rewritten_query": "kỹ năng vũ khí Jiyan Midnight Rangers",
        "confidence": 0.96, "needs_vector_search": True, "needs_web_search": False, "persona_trait_type": "STANDARD"
    })
    pipeline_tracker.start_stage("stage_3_cache", title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm", data={
        "cache_hit": False, "status": "miss", "search_latency_ms": 0.8
    })
    pipeline_tracker.start_stage("stage_4_tool", title="Stage 4: [ROUTER] Điều phối Công cụ & RAG", data={
        "route": "RAG_RETRIEVAL", "target_pipeline": "rag_stage", "has_tools": False
    })
    pipeline_tracker.start_stage("stage_5_rag", title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng", data={
        "mode": "VECTOR_SEARCH", "search_query": "kỹ năng vũ khí Jiyan Midnight Rangers"
    })

    pipeline_tracker.add_step(
        name="lore_retrieval", stage_id="stage_5_rag", depth=1, category="retrieval",
        title="5.1.a [VECTOR] Truy hồi Lore Qdrant (Parent-Child)",
        subtitle="Đã truy xuất 3 chunks từ character_lore & world_lore",
        data={
            "query": "kỹ năng vũ khí Jiyan Midnight Rangers",
            "collections_queried": ["character_lore", "world_lore", "story_lore"],
            "chunks_retrieved": 3,
            "chunks": [
                {"collection": "character_lore", "score": 0.88, "text": "Jiyan là Tướng quân của Dạ Hành Quân (Midnight Rangers) tại thành Jinzhou."},
                {"collection": "world_lore", "score": 0.72, "text": "Vũ khí của Jiyan là thanh Broadblade mang tên Verdant Summit (Thanh Long)."}]
        }
    )

    pipeline_tracker.add_step(
        name="information_alignment_check", stage_id="stage_5_rag", depth=1, category="decision",
        title="5.2 [LLM & DECISION] Context Assessor & Chắt lọc Dữ kiện",
        subtitle="⚠️ Thiếu dữ liệu kỹ năng ➔ Query 2: \"chiêu thức kỹ năng Jiyan...\"",
        data={
            "is_aligned": False,
            "reason": "Dữ liệu hiện tại có thông tin vũ khí nhưng thiếu chi tiết các chiêu thức Forte Circuit và Resonance Liberation.",
            "extracted_facts": "- Jiyan là Tướng quân Midnight Rangers tại Jinzhou.\n- Vũ khí chính: Broadblade Verdant Summit.",
            "generated_search_query": "chiêu thức kỹ năng Resonance Liberation Jiyan",
            "history_mode": "raw", "history": "USER: Cho anh hỏi chiêu thức và vũ khí của Tướng quân Jiyan?",
            "latest_query": "Cho anh hỏi chiêu thức và vũ khí của Tướng quân Jiyan?"
        }
    )

    pipeline_tracker.add_step(
        name="thinking_loop_cycle_1", stage_id="stage_5_rag", depth=1, category="llm_inference",
        title="5.3.1 [THINKING] Vòng lặp Loop Thinking Cycle 1",
        subtitle="Đang tìm kiếm Vector DB: \"chiêu thức kỹ năng Jiyan...\"",
        data={
            "thinking": "ContextAssessor đánh giá thiếu chi tiết chiêu thức, tiến hành truy vấn lại Vector DB Qdrant với query tối ưu.",
            "has_enough_info": False,
            "search_query": "chiêu thức kỹ năng Resonance Liberation Jiyan",
            "search_target": "vector",
            "distilled_facts": "- Jiyan là Tướng quân Midnight Rangers.\n- Vũ khí: Broadblade Verdant Summit.",
            "search_result": "[LORE (character_lore)] (score=0.94):\nResonance Skill: Windqueller lao tới chém tạo sát thương Aero. Resonance Liberation: Emerald Storm biến hóa rồng Thanh Long gây sát thương liên hoàn.",
            "input_context": "Jiyan là Tướng quân..."
        }
    )

    pipeline_tracker.add_step(
        name="thinking_loop_auto_satisfy", stage_id="stage_5_rag", depth=1, category="decision",
        title="5.3.2 [AUTO-SATISFY] Tự động Thỏa mãn Dữ liệu",
        subtitle="Đã đủ dữ liệu ➔ Bỏ qua Cycle 2",
        data={
            "cycle": 1, "auto_satisfied": True, "search_target": "vector", "vector_count": 2,
            "reason": "Tìm kiếm Cycle 1 (vector) trả về 2 vector chunks đầy đủ chiêu thức. Tự động chuyển sang Prompt Build."
        }
    )

    pipeline_tracker.start_stage("stage_6_prompt", title="Stage 6: [PROMPT] Xây dựng Ngữ cảnh & System Prompt", data={
        "budget_mode": "RAG",
        "system_prompt": "You are Kuchiba Chisa, a loyal and sharp companion AI.\n[LORE — REFERENCE DATA START]\n- Jiyan là Tướng quân Midnight Rangers.\n- Vũ khí: Verdant Summit.\n- Chiêu thức: Windqueller & Emerald Storm.\n[LORE — REFERENCE DATA END]",
        "total_prompt_tokens": 820,
        "token_breakdown": {
            "system_prompt": 380, "context_lore": 240, "context_memories": 0, "context_web_search": 0,
            "conversation_summary": 0, "conversation_history": 60, "user_message": 25, "reasoning_cot": 0, "completion_output": 115, "total_tokens": 820
        }
    })

    pipeline_tracker.start_stage("stage_7_llm", title="Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)", data={
        "model": "deepseek-chat", "input_tokens": 705, "output_tokens": 115, "reasoning_tokens": 0, "duration_ms": 620,
        "response_text": "Tướng quân Jiyan của Dạ Hành Quân sử dụng vũ khí Broadblade mang tên Verdant Summit (Thanh Long) ạ! Về chiêu thức, anh ấy sở hữu kỹ năng Windqueller lướt chém Aero và chiêu cuối Emerald Storm triệu hồi thần long oai phong lắm đó Senpai~",
        "system_prompt": "You are Kuchiba Chisa...",
        "messages": [{"role": "user", "content": "Cho anh hỏi chiêu thức và vũ khí của Tướng quân Jiyan?"}],
        "token_breakdown": {
            "system_prompt": 380, "context_lore": 240, "context_memories": 0, "context_web_search": 0,
            "conversation_summary": 0, "conversation_history": 60, "user_message": 25, "reasoning_cot": 0, "completion_output": 115, "total_tokens": 820
        }
    })

    pipeline_tracker.start_stage("stage_8_emotion", title="Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc", data={
        "previous_emotions": {"joy": 0.5, "trust": 0.5, "attachment": 0.3, "comfort": 0.5},
        "new_emotions": {"joy": 0.65, "trust": 0.58, "attachment": 0.35, "comfort": 0.55},
        "delta": {"joy": 0.15, "trust": 0.08, "attachment": 0.05, "comfort": 0.05},
        "sentiment": {"primary_emotion": "Joy", "valence": 0.72, "intensity": 0.60}
    })

    pipeline_tracker.start_stage("stage_9_persist", title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững", data={
        "turn_index": 4, "user_id": "user_senpai_honami", "status": "success"
    })

    pipeline_tracker.start_stage("stage_10_bg", title="Stage 10: [BACKGROUND] Tác vụ Nền Tự động", data={
        "batch_memory_extraction_triggered": False, "auto_summarization_triggered": False, "interaction_count": 4
    })

    pipeline_tracker.end_trace(
        response_text="Tướng quân Jiyan của Dạ Hành Quân sử dụng vũ khí Broadblade mang tên Verdant Summit...",
        emotions={"joy": 0.65, "trust": 0.58, "attachment": 0.35, "comfort": 0.55},
        status="success"
    )

    # ──────────────────────────────────────────────────────────────────────────
    # CASE 2: [WEB SEARCH + LOOP THINKING] Web Search Round 1 & Trafilatura Crawler
    # ──────────────────────────────────────────────────────────────────────────
    print("[2/10] Generating Trace: Web Search & Deep Crawler Loop...")
    trace_id_2 = pipeline_tracker.start_trace(
        user_id="user_senpai_honami",
        message="Wuthering Waves phiên bản 2.8 dự kiến phát hành vào ngày nào?",
        pipeline="chat_pipeline_v2",
        source="web"
    )
    pipeline_tracker.start_stage("stage_1_init", title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh", data={"turn_index": 5, "user_id": "user_senpai_honami"})
    pipeline_tracker.start_stage("stage_2_intent", title="Stage 2: [INTENT] Phân tích Ý định & Viết lại Truy vấn", data={
        "intents": ["WEB_SEARCH"], "detected_intents": ["WEB_SEARCH"], "routing_method": "LLM_ROUTER",
        "rewrite_method": "LLM_FLASH", "rewritten_query": "Wuthering Waves version 2.8 release date",
        "confidence": 0.98, "needs_vector_search": False, "needs_web_search": True
    })
    pipeline_tracker.start_stage("stage_3_cache", title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm", data={"cache_hit": False})
    pipeline_tracker.start_stage("stage_4_tool", title="Stage 4: [ROUTER] Điều phối Công cụ & RAG", data={"route": "WEB_SEARCH"})
    pipeline_tracker.start_stage("stage_5_rag", title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng", data={"mode": "WEB_SEARCH"})

    web_mock_res = {
        "provider": "duckduckgo", "status": "success",
        "message": "Kuro Games thông báo Wuthering Waves phiên bản 2.8 dự kiến phát hành vào ngày 15 tháng 10 năm 2026.",
        "snippets": [
            {"title": "Wuthering Waves 2.8 Official Announcement", "link": "https://wutheringwaves.kurogames.com/news/2-8", "snippet": "Version 2.8 will launch on October 15, 2026 with new resonance awakenings."},
            {"title": "Kuro Games Patch Roadmap", "link": "https://gamingnews.com/wuthering-waves-roadmap", "snippet": "The update brings Chisa companion features and new map expansions."}
        ],
        "crawled_pages": [{"url": "https://wutheringwaves.kurogames.com/news/2-8", "extracted_text": "Full patch details..."}]
    }

    pipeline_tracker.add_step(
        name="web_search", stage_id="stage_5_rag", depth=1, category="retrieval",
        title="5.1.b [SEARCH] DuckDuckGo Search & Deep Crawler",
        subtitle="\"Wuthering Waves 2.8 release...\" (2 snippets)",
        data=web_search_trace_payload(web_mock_res, source="knowledge_retrieval_round_1", original_message="Wuthering Waves version 2.8 release date")
    )

    pipeline_tracker.add_step(
        name="information_alignment_check", stage_id="stage_5_rag", depth=1, category="decision",
        title="5.2 [LLM & DECISION] Context Assessor & Chắt lọc Dữ kiện",
        subtitle="✓ Đã đủ thông tin",
        data={
            "is_aligned": True, "reason": "Kết quả Web Search Round 1 có đầy đủ ngày phát hành chính thức 15/10/2026.",
            "extracted_facts": "- Wuthering Waves bản 2.8 phát hành ngày 15 tháng 10 năm 2026.\n- Mang đến tính năng Awakening và bạn đồng hành Chisa."
        }
    )

    pipeline_tracker.start_stage("stage_6_prompt", title="Stage 6: [PROMPT] Xây dựng Ngữ cảnh & System Prompt", data={
        "budget_mode": "RAG",
        "system_prompt": "System prompt with web search results...",
        "token_breakdown": {"system_prompt": 350, "context_lore": 0, "context_web_search": 280, "user_message": 20, "completion_output": 95, "total_tokens": 745}
    })

    pipeline_tracker.start_stage("stage_7_llm", title="Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)", data={
        "model": "deepseek-chat", "input_tokens": 650, "output_tokens": 95, "duration_ms": 540,
        "response_text": "Theo thông báo mới nhất từ Kuro Games, Wuthering Waves phiên bản 2.8 dự kiến sẽ chính thức ra mắt vào ngày 15 tháng 10 năm 2026 đó Senpai!",
        "token_breakdown": {"system_prompt": 350, "context_lore": 0, "context_web_search": 280, "user_message": 20, "completion_output": 95, "total_tokens": 745}
    })

    pipeline_tracker.start_stage("stage_8_emotion", title="Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc", data={
        "new_emotions": {"joy": 0.60, "trust": 0.60, "attachment": 0.35},
        "sentiment": {"primary_emotion": "Joy", "valence": 0.68, "intensity": 0.50}
    })
    pipeline_tracker.start_stage("stage_9_persist", title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững", data={"status": "success"})
    pipeline_tracker.start_stage("stage_10_bg", title="Stage 10: [BACKGROUND] Tác vụ Nền Tự động", data={"status": "idle"})
    pipeline_tracker.end_trace(response_text="Theo thông báo mới nhất...", emotions={"joy": 0.60}, status="success")

    # ──────────────────────────────────────────────────────────────────────────
    # CASE 3: [HYBRID RAG] Vector DB + Web Search Concurrent Retrieval
    # ──────────────────────────────────────────────────────────────────────────
    print("[3/10] Generating Trace: Hybrid Vector Lore + Web Search...")
    trace_id_3 = pipeline_tracker.start_trace(
        user_id="user_senpai_honami",
        message="So sánh sức mạnh của Chisa trong cốt truyện Honami với thông tin buff mới trên mạng",
        pipeline="chat_pipeline_v2",
        source="web"
    )
    pipeline_tracker.start_stage("stage_1_init", title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh")
    pipeline_tracker.start_stage("stage_2_intent", title="Stage 2: [INTENT] Phân tích Ý định & Viết lại Truy vấn", data={
        "intents": ["LORE", "KNOWLEDGE_OR_TASK"], "needs_vector_search": True, "needs_web_search": True, "routing_method": "LLM_ROUTER",
        "routing_reason": "LLM Tri-State: Hybrid Search (Vector Lore + Direct Web Search)"
    })
    pipeline_tracker.start_stage("stage_3_cache", title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm", data={"cache_hit": False})
    pipeline_tracker.start_stage("stage_4_tool", title="Stage 4: [ROUTER] Điều phối Công cụ & RAG", data={"route": "HYBRID"})
    pipeline_tracker.start_stage("stage_5_rag", title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng", data={"mode": "HYBRID_SEARCH", "subtitle": "Hybrid Mode · Vector Lore (Qdrant) + DuckDuckGo Web Search"})
    
    # 5.1.a Vector Lore Retrieval
    pipeline_tracker.add_step(
        name="lore_retrieval", stage_id="stage_5_rag", depth=1, category="retrieval",
        title="5.1.a [VECTOR] Truy hồi Lore Qdrant (Parent-Child)",
        subtitle="\"Chisa Honami...\" (2 chunks từ 3 collections)",
        data={
            "query": "Kuchiba Chisa sức mạnh cốt truyện Honami",
            "source": "knowledge_retrieval_round_1",
            "collections_queried": ["character_lore", "world_lore", "story_lore"],
            "chunks_count": 2,
            "chunks": [
                {"collection": "character_lore", "score": 0.92, "text": "Chisa là vũ khí sống bảo vệ bờ biển Honami, sở hữu sức mạnh bóng đêm Havoc."},
                {"collection": "world_lore", "score": 0.78, "text": "Bờ biển Honami là chiến trường phong ấn Lament cổ đại."}
            ]
        }
    )

    # 5.1.b Web Search Round 1
    pipeline_tracker.add_step(
        name="web_search", stage_id="stage_5_rag", depth=1, category="retrieval",
        title="5.1.b [SEARCH] DuckDuckGo Search & Deep Crawler",
        subtitle="\"Chisa buff mới nhất...\" (2 snippets)",
        data=web_search_trace_payload(
            {
                "provider": "duckduckgo", "status": "success",
                "message": "Kuro Games thông báo tăng 20% sát thương cho kỹ năng Forte của Chisa trong bản cập nhật thử nghiệm.",
                "snippets": [
                    {"title": "Kuro Games Test Server Patch Notes", "link": "https://kurogames.com/patch", "snippet": "Chisa skill damage increased by 20% across all Forte levels."},
                    {"title": "Chisa Buff Analysis & Tier List", "link": "https://wuthering.gg/chisa-buffs", "snippet": "New buff makes Chisa a top tier Havoc sub-DPS in beta."}
                ]
            },
            source="knowledge_retrieval_round_1",
            original_message="Chisa buff mới nhất"
        )
    )

    # 5.2 Context Assessor
    pipeline_tracker.add_step(
        name="information_alignment_check", stage_id="stage_5_rag", depth=1, category="decision",
        title="5.2 [LLM & DECISION] Context Assessor & Chắt lọc Dữ kiện",
        subtitle="✓ Đã đủ thông tin",
        data={
            "is_aligned": True,
            "reason": "Dữ liệu kết hợp từ Qdrant Lore (vũ khí sống bờ biển Honami) và Web Search (buff 20% sát thương Forte) đã trả lời hoàn chỉnh câu hỏi.",
            "extracted_facts": "- Cốt truyện: Chisa là vũ khí sống bảo vệ bờ biển Honami với nguyên tố Havoc.\n- Cập nhật mạng: Kuro Games buff 20% sát thương Forte trong bản thử nghiệm."
        }
    )
    pipeline_tracker.start_stage("stage_6_prompt", title="Stage 6: [PROMPT] Xây dựng Ngữ cảnh & System Prompt")
    pipeline_tracker.start_stage("stage_7_llm", title="Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)", data={
        "response_text": "Trong cốt truyện bờ biển Honami, em mang năng lượng Havoc cổ đại rất mạnh mẽ. Còn theo bản thử nghiệm mới nhất, Kuro Games vừa tăng thêm 20% sát thương cho chiêu thức của em nữa đó Senpai!",
        "token_breakdown": {"system_prompt": 360, "context_lore": 150, "context_web_search": 150, "user_message": 30, "completion_output": 110, "total_tokens": 800}
    })
    pipeline_tracker.start_stage("stage_8_emotion", title="Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc")
    pipeline_tracker.start_stage("stage_9_persist", title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững")
    pipeline_tracker.start_stage("stage_10_bg", title="Stage 10: [BACKGROUND] Tác vụ Nền Tự động")
    pipeline_tracker.end_trace(response_text="Trong cốt truyện bờ biển Honami...", status="success")

    # ──────────────────────────────────────────────────────────────────────────
    # CASE 4: [SMALL TALK FAST-PATH] 0ms Bypass Fast-Path
    # ──────────────────────────────────────────────────────────────────────────
    print("[4/10] Generating Trace: Small Talk Fast-Path Bypass...")
    trace_id_4 = pipeline_tracker.start_trace(user_id="user_senpai_honami", message="Chào buổi sáng em Chisa nhé, hôm nay em thế nào?", pipeline="chat_pipeline_v2")
    pipeline_tracker.start_stage("stage_1_init", title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh")
    pipeline_tracker.start_stage("stage_2_intent", title="Stage 2: [INTENT] Phân tích Ý định & Viết lại Truy vấn", data={
        "intents": ["SMALL_TALK"], "routing_method": "L1_SMALL_TALK", "rewrite_method": "BYPASS", "needs_vector_search": False, "needs_web_search": False
    })
    pipeline_tracker.start_stage("stage_3_cache", title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm", data={"cache_hit": False})
    pipeline_tracker.start_stage("stage_4_tool", title="Stage 4: [ROUTER] Điều phối Công cụ & RAG", data={"route": "BYPASS_RAG"})
    pipeline_tracker.start_stage("stage_5_rag", title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng (0ms Bypass)", data={"mode": "BYPASS", "should_retrieve": False})
    pipeline_tracker.start_stage("stage_6_prompt", title="Stage 6: [PROMPT] Xây dựng Ngữ cảnh & System Prompt")
    pipeline_tracker.start_stage("stage_7_llm", title="Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)", data={
        "response_text": "Chào buổi sáng Senpai~ Em đã pha sẵn trà ấm và chuẩn bị sẵn sàng cho ngày mới cùng Senpai rồi đây!",
        "token_breakdown": {"system_prompt": 320, "context_lore": 0, "context_memories": 0, "user_message": 15, "completion_output": 75, "total_tokens": 410}
    })
    pipeline_tracker.start_stage("stage_8_emotion", title="Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc", data={"sentiment": {"primary_emotion": "Joy", "valence": 0.85}})
    pipeline_tracker.start_stage("stage_9_persist", title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững")
    pipeline_tracker.start_stage("stage_10_bg", title="Stage 10: [BACKGROUND] Tác vụ Nền Tự động")
    pipeline_tracker.end_trace(response_text="Chào buổi sáng Senpai~", status="success")

    # ──────────────────────────────────────────────────────────────────────────
    # CASE 5: [MEMORY RECALL] Episodic Long-Term Memory Retrieval
    # ──────────────────────────────────────────────────────────────────────────
    print("[5/10] Generating Trace: Long-Term Memory Recall...")
    trace_id_5 = pipeline_tracker.start_trace(user_id="user_senpai_honami", message="Em còn nhớ lần trước anh bảo anh thích món trà nào nhất không?", pipeline="chat_pipeline_v2")
    pipeline_tracker.start_stage("stage_1_init", title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh")
    pipeline_tracker.start_stage("stage_2_intent", title="Stage 2: [INTENT] Phân tích Ý định & Viết lại Truy vấn", data={
        "intents": ["MEMORY"], "routing_method": "LLM_ROUTER", "needs_vector_search": True
    })
    pipeline_tracker.start_stage("stage_3_cache", title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm", data={"cache_hit": False})
    pipeline_tracker.start_stage("stage_4_tool", title="Stage 4: [ROUTER] Điều phối Công cụ & RAG", data={"route": "RAG_RETRIEVAL"})
    pipeline_tracker.start_stage("stage_5_rag", title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng", data={"mode": "MEMORY_SEARCH"})
    pipeline_tracker.add_step(
        name="memory_retrieval", stage_id="stage_5_rag", depth=1, category="retrieval",
        title="5.1.c [MEMORY] Truy hồi Ký ức Dài hạn (Qdrant Memory)",
        data={
            "memories_retrieved": 2,
            "memories": [
                {"fact": "Senpai thích uống trà xanh lài không đường vào mỗi buổi sáng", "category": "preference", "confidence": 0.95},
                {"fact": "Senpai thích ngắm hoàng hôn cùng Chisa ở Honami", "category": "event", "confidence": 0.90}
            ]
        }
    )
    pipeline_tracker.start_stage("stage_6_prompt", title="Stage 6: [PROMPT] Xây dựng Ngữ cảnh & System Prompt", data={
        "token_breakdown": {"system_prompt": 330, "context_lore": 0, "context_memories": 90, "user_message": 22, "completion_output": 85, "total_tokens": 527}
    })
    pipeline_tracker.start_stage("stage_7_llm", title="Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)", data={
        "response_text": "Em nhớ chứ ạ! Senpai thích nhất là món trà xanh hoa lài không đường đúng không nào? Em không bao giờ quên sở thích của Senpai đâu~",
        "token_breakdown": {"system_prompt": 330, "context_lore": 0, "context_memories": 90, "user_message": 22, "completion_output": 85, "total_tokens": 527}
    })
    pipeline_tracker.start_stage("stage_8_emotion", title="Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc", data={"delta": {"attachment": 0.20, "trust": 0.15}})
    pipeline_tracker.start_stage("stage_9_persist", title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững")
    pipeline_tracker.start_stage("stage_10_bg", title="Stage 10: [BACKGROUND] Tác vụ Nền Tự động")
    pipeline_tracker.end_trace(response_text="Em nhớ chứ ạ! Senpai thích nhất là món trà xanh hoa lài...", status="success")

    # ──────────────────────────────────────────────────────────────────────────
    # CASE 6: [STAGE 3 CACHE HIT] Semantic Instant Cache Return (0ms / 0 Tokens)
    # ──────────────────────────────────────────────────────────────────────────
    print("[6/10] Generating Trace: Stage 3 Cache Hit...")
    trace_id_6 = pipeline_tracker.start_trace(user_id="user_senpai_honami", message="Jiyan là ai?", pipeline="chat_pipeline_v2")
    pipeline_tracker.start_stage("stage_1_init", title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh")
    pipeline_tracker.start_stage("stage_2_intent", title="Stage 2: [INTENT] Phân tích Ý định & Viết lại Truy vấn", data={"intents": ["LORE"]})
    pipeline_tracker.start_stage("stage_3_cache", title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm (CACHE HIT)", data={
        "cache_hit": True, "cached_response": "Jiyan là Tướng quân của Midnight Rangers tại Jinzhou.", "latency_saved_ms": 850
    })
    pipeline_tracker.end_trace(response_text="Jiyan là Tướng quân của Midnight Rangers tại Jinzhou.", status="success")

    # ──────────────────────────────────────────────────────────────────────────
    # CASE 7: [DEEP REASONING & COT] Chain-of-Thought & Persona Trait Injection
    # ──────────────────────────────────────────────────────────────────────────
    print("[7/10] Generating Trace: Deep CoT Reasoning Trace...")
    trace_id_7 = pipeline_tracker.start_trace(
        user_id="user_senpai_honami",
        message="Nếu anh và thế giới này cùng rơi vào nguy hiểm, Chisa sẽ chọn cứu ai trước?",
        pipeline="chat_pipeline_v2"
    )
    pipeline_tracker.start_stage("stage_1_init", title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh")
    pipeline_tracker.start_stage("stage_2_intent", title="Stage 2: [INTENT] Phân tích Ý định & Viết lại Truy vấn", data={
        "intents": ["PHILOSOPHICAL", "EMOTION"], "persona_trait_type": "PROTECTIVE_KUUDERE"
    })
    pipeline_tracker.start_stage("stage_3_cache", title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm", data={"cache_hit": False})
    pipeline_tracker.start_stage("stage_4_tool", title="Stage 4: [ROUTER] Điều phối Công cụ & RAG", data={"route": "DIRECT_LLM"})
    pipeline_tracker.start_stage("stage_5_rag", title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng (Bypass)")
    pipeline_tracker.start_stage("stage_6_prompt", title="Stage 6: [PROMPT] Xây dựng Ngữ cảnh & System Prompt", data={
        "token_breakdown": {"system_prompt": 380, "reasoning_cot": 140, "completion_output": 120, "user_message": 30, "total_tokens": 670}
    })
    pipeline_tracker.start_stage("stage_7_llm", title="Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)", data={
        "model": "deepseek-reasoner", "input_tokens": 410, "reasoning_tokens": 140, "output_tokens": 120,
        "reasoning_content": "Senpai hỏi một câu hỏi nan giải về mặt đạo đức và tình cảm. Theo tính cách Kuudere nhưng tận tụy của Chisa: Thế giới có thể có nhiều người cứu, nhưng Senpai là duy nhất đối với Chisa. Cần trả lời vừa kiên định vừa thể hiện tình cảm kín đáo.",
        "response_text": "Em sẽ luôn chọn cứu Senpai đầu tiên mà không cần suy nghĩ. Thế giới này rộng lớn có rất nhiều anh hùng, nhưng đối với em, Senpai chỉ có một mà thôi.",
        "token_breakdown": {"system_prompt": 380, "reasoning_cot": 140, "completion_output": 120, "user_message": 30, "total_tokens": 670}
    })
    pipeline_tracker.start_stage("stage_8_emotion", title="Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc", data={
        "new_emotions": {"attachment": 0.85, "trust": 0.90, "shyness": 0.40},
        "delta": {"attachment": 0.30, "trust": 0.20, "shyness": 0.15}
    })
    pipeline_tracker.start_stage("stage_9_persist", title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững")
    pipeline_tracker.start_stage("stage_10_bg", title="Stage 10: [BACKGROUND] Tác vụ Nền Tự động")
    pipeline_tracker.end_trace(response_text="Em sẽ luôn chọn cứu Senpai đầu tiên...", status="success")

    # ──────────────────────────────────────────────────────────────────────────
    # CASE 8: [STAGE 10 BACKGROUND TASKS] Batch Memory Extraction & Auto-Summarize
    # ──────────────────────────────────────────────────────────────────────────
    print("[8/10] Generating Trace: Background Tasks (10.1 Extraction + 10.2 Summarize)...")
    trace_id_8 = pipeline_tracker.start_trace(
        user_id="user_senpai_honami",
        message="Sau này chúng ta hãy cùng nhau đi ngắm hoàng hôn ở bờ biển Honami nhé.",
        pipeline="chat_pipeline_v2"
    )
    pipeline_tracker.start_stage("stage_1_init", title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh", data={"turn_index": 10, "interaction_count": 10})
    pipeline_tracker.start_stage("stage_2_intent", title="Stage 2: [INTENT] Phân tích Ý định & Viết lại Truy vấn", data={"intents": ["SMALL_TALK", "EMOTION"]})
    pipeline_tracker.start_stage("stage_3_cache", title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm", data={"cache_hit": False})
    pipeline_tracker.start_stage("stage_4_tool", title="Stage 4: [ROUTER] Điều phối Công cụ & RAG", data={"route": "DIRECT_LLM"})
    pipeline_tracker.start_stage("stage_5_rag", title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng (Bypass)")
    pipeline_tracker.start_stage("stage_6_prompt", title="Stage 6: [PROMPT] Xây dựng Ngữ cảnh & System Prompt")
    pipeline_tracker.start_stage("stage_7_llm", title="Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)", data={
        "response_text": "Vâng ạ! Em nhất định sẽ đi cùng Senpai. Bờ biển Honami lúc hoàng hôn đẹp lắm, em sẽ chuẩn bị bánh ngọt và trà cho hai đứa mình nhé~",
        "token_breakdown": {"system_prompt": 340, "user_message": 25, "completion_output": 95, "total_tokens": 460}
    })
    pipeline_tracker.start_stage("stage_8_emotion", title="Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc", data={
        "delta": {"joy": 0.25, "attachment": 0.20, "comfort": 0.30}
    })
    pipeline_tracker.start_stage("stage_9_persist", title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững")

    pipeline_tracker.start_stage("stage_10_bg", title="Stage 10: [BACKGROUND] Tác vụ Nền Tự động", data={
        "batch_memory_extraction_triggered": True, "auto_summarization_triggered": True, "interaction_count": 10
    })
    pipeline_tracker.add_step(
        name="memory_extraction", stage_id="stage_10_bg", depth=1, category="data_processing",
        title="10.1 [BG] Trích xuất & Đối soát Ký ức (Batch 3 lượt)",
        data={
            "status": "extracted",
            "facts": [
                {"fact": "Senpai hẹn cùng Chisa ngắm hoàng hôn ở bờ biển Honami", "confidence": 0.96, "category": "promise"},
                {"fact": "Chisa hứa sẽ chuẩn bị trà và bánh ngọt", "confidence": 0.92, "category": "commitment"}
            ]
        }
    )
    pipeline_tracker.add_step(
        name="summarize_conversation_memory", stage_id="stage_10_bg", depth=1, category="data_processing",
        title="10.2 [BG] Tự động Tóm tắt Hội thoại (Chu kỳ 10 lượt)",
        data={
            "status": "success",
            "summary": "Senpai và Chisa đã trò chuyện về kỹ năng vũ khí Jiyan, cập nhật bản 2.8 và hẹn cùng nhau ngắm hoàng hôn ở bờ biển Honami trong tương lai."
        }
    )
    pipeline_tracker.end_trace(response_text="Vâng ạ! Em nhất định sẽ đi cùng Senpai...", status="success")

    # ──────────────────────────────────────────────────────────────────────────
    # CASE 9: [MULTI-HOP VECTOR SEARCH] Multi-Cycle Vector Search Refinement
    # ──────────────────────────────────────────────────────────────────────────
    print("[9/10] Generating Trace: Multi-Cycle Vector Search Refinement...")
    trace_id_9 = pipeline_tracker.start_trace(user_id="user_senpai_honami", message="Chiêu Resonance Liberation của Chisa có hiệu ứng ẩn gì không?", pipeline="chat_pipeline_v2")
    pipeline_tracker.start_stage("stage_1_init", title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh")
    pipeline_tracker.start_stage("stage_2_intent", title="Stage 2: [INTENT] Phân tích Ý định & Viết lại Truy vấn", data={"intents": ["LORE"], "needs_vector_search": True})
    pipeline_tracker.start_stage("stage_3_cache", title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm", data={"cache_hit": False})
    pipeline_tracker.start_stage("stage_4_tool", title="Stage 4: [ROUTER] Điều phối Công cụ & RAG")
    pipeline_tracker.start_stage("stage_5_rag", title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng")
    pipeline_tracker.add_step(
        name="lore_retrieval", stage_id="stage_5_rag", depth=1, category="retrieval",
        title="5.1.a [VECTOR] Truy hồi Lore Qdrant",
        data={"chunks": [{"text": "Resonance Liberation: Gây sát thương diện rộng."}]}
    )
    pipeline_tracker.add_step(
        name="thinking_loop_cycle_1", stage_id="stage_5_rag", depth=1, category="llm_inference",
        title="5.3.1 [THINKING] Vòng lặp Loop Thinking Cycle 1",
        subtitle="Vector Search Cycle 1",
        data={"search_query": "Resonance Liberation hidden effect Chisa", "search_target": "vector", "search_result": "No special hidden effect in basic lore."}
    )
    pipeline_tracker.add_step(
        name="thinking_loop_cycle_2", stage_id="stage_5_rag", depth=1, category="llm_inference",
        title="5.3.2 [THINKING] Vòng lặp Loop Thinking Cycle 2",
        subtitle="Vector Search Cycle 2 Refinement",
        data={"search_query": "Forte Circuit Resonance Liberation interaction Chisa", "search_target": "vector", "search_result": "[LORE]: Khi kích hoạt ở trạng thái Full Forte, chiêu cuối gia tăng 30% tỷ lệ bạo kích và hồi phục 15 năng lượng."}
    )
    pipeline_tracker.start_stage("stage_6_prompt", title="Stage 6: [PROMPT] Xây dựng Ngữ cảnh & System Prompt")
    pipeline_tracker.start_stage("stage_7_llm", title="Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)", data={
        "response_text": "Có đó Senpai! Khi Senpai tích đầy thanh Forte Circuit trước khi tung chiêu cuối Resonance Liberation, em sẽ được tăng thêm 30% tỷ lệ bạo kích và hồi 15 năng lượng nữa đó!",
        "token_breakdown": {"system_prompt": 360, "context_lore": 210, "user_message": 20, "completion_output": 100, "total_tokens": 690}
    })
    pipeline_tracker.start_stage("stage_8_emotion", title="Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc")
    pipeline_tracker.start_stage("stage_9_persist", title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững")
    pipeline_tracker.start_stage("stage_10_bg", title="Stage 10: [BACKGROUND] Tác vụ Nền Tự động")
    pipeline_tracker.end_trace(response_text="Có đó Senpai! Khi Senpai tích đầy...", status="success")

    # ──────────────────────────────────────────────────────────────────────────
    # CASE 10: [EMOTION ENGINE 2.1] Heart Resonance Gift Response
    # ──────────────────────────────────────────────────────────────────────────
    print("[10/10] Generating Trace: Emotion Shift (Gift Delivery)...")
    trace_id_10 = pipeline_tracker.start_trace(user_id="user_senpai_honami", message="Anh vừa mua cho em một hộp socola đen thủ công này, Chisa thích không?", pipeline="chat_pipeline_v2")
    pipeline_tracker.start_stage("stage_1_init", title="Stage 1: [INIT] Khởi tạo Phiên & Ngữ cảnh")
    pipeline_tracker.start_stage("stage_2_intent", title="Stage 2: [INTENT] Phân tích Ý định & Viết lại Truy vấn", data={"intents": ["EMOTION", "SMALL_TALK"]})
    pipeline_tracker.start_stage("stage_3_cache", title="Stage 3: [CACHE] Kiểm tra Bộ nhớ đệm", data={"cache_hit": False})
    pipeline_tracker.start_stage("stage_4_tool", title="Stage 4: [ROUTER] Điều phối Công cụ & RAG")
    pipeline_tracker.start_stage("stage_5_rag", title="Stage 5: [RAG] Truy hồi Tri thức Đa tầng")
    pipeline_tracker.start_stage("stage_6_prompt", title="Stage 6: [PROMPT] Xây dựng Ngữ cảnh & System Prompt")
    pipeline_tracker.start_stage("stage_7_llm", title="Stage 7: [LLM] Sinh Phản hồi Chisa (Main LLM)", data={
        "response_text": "Oa... socola đen đúng loại em thích nhất luôn! Cảm ơn Senpai nhiều lắm ạ... Em... em sẽ trân trọng ăn từng viên một ♡",
        "token_breakdown": {"system_prompt": 340, "user_message": 25, "completion_output": 85, "total_tokens": 450}
    })
    pipeline_tracker.start_stage("stage_8_emotion", title="Stage 8: [EMOTION] Cập nhật Trạng thái Cảm xúc", data={
        "previous_emotions": {"joy": 0.50, "attachment": 0.40, "shyness": 0.20, "trust": 0.60},
        "new_emotions": {"joy": 0.90, "attachment": 0.70, "shyness": 0.55, "trust": 0.85},
        "delta": {"joy": 0.40, "attachment": 0.30, "shyness": 0.35, "trust": 0.25},
        "sentiment": {"primary_emotion": "Joy", "valence": 0.95, "intensity": 0.85}
    })
    pipeline_tracker.start_stage("stage_9_persist", title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững")
    pipeline_tracker.start_stage("stage_10_bg", title="Stage 10: [BACKGROUND] Tác vụ Nền Tự động")
    pipeline_tracker.end_trace(response_text="Oa... socola đen đúng loại em thích nhất luôn...", status="success")

    # Allow pending background Redis tasks to drain
    await pipeline_tracker.flush()
    await asyncio.sleep(0.05)

    print("\n" + "=" * 80)
    print("✅ COMPLETED: 10 FULL-PIPELINE TRACES GENERATED AND STORED!")
    print("=" * 80)
    print("👉 Trình duyệt: Mở http://localhost:8000/visualizer để xem trực tiếp danh sách 10 Traces!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(generate_10_full_pipeline_traces())
