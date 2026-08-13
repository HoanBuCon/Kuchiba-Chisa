"""
Comprehensive 20-Question Benchmark Suite: RAG & Data Utilization Evaluation
Tests end-to-end intent classification, hybrid retrieval (Wiki vs Chisa Lore),
prompt context assembly, CoT deep reasoning, and response quality.
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.application.dependencies import container
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
from app.infrastructure.cache.redis.redis_service import get_redis_client


@dataclass
class BenchmarkCase:
    id: str
    domain: str
    query: str
    expected_source_type: str  # "wiki", "chisa_lore", or "hybrid"
    key_terms: List[str]       # Terms expected in chunks or response


BENCHMARK_CASES: List[BenchmarkCase] = [
    # ── Domain 1: Wuthering Waves Wiki — Waveworn Phenomena & Atmospheric Events ──
    BenchmarkCase(
        id="BM01",
        domain="Wiki: Waveworn Phenomena",
        query="Hiện tượng Retroact Rain trong Waveworn Phenomenon là gì và nó tạo ra ảo ảnh như thế nào?",
        expected_source_type="wiki",
        key_terms=["Retroact Rain", "Remnant Energy", "Waveworn", "Etheric Sea"],
    ),
    BenchmarkCase(
        id="BM02",
        domain="Wiki: Waveworn Phenomena",
        query="Hiện tượng Void Storm tại vùng Lahai-Roi diễn ra theo chu kỳ ra sao?",
        expected_source_type="wiki",
        key_terms=["Void Storm", "Lahai-Roi", "Waveworn", "frequency"],
    ),
    BenchmarkCase(
        id="BM03",
        domain="Wiki: Waveworn Phenomena",
        query="Etheric Sea và Remnant Energy có vai trò như thế nào trong sự hình thành tần số thế giới?",
        expected_source_type="wiki",
        key_terms=["Etheric Sea", "Remnant Energy", "Frequency", "Waveworn"],
    ),
    BenchmarkCase(
        id="BM04",
        domain="Wiki: Waveworn Phenomena",
        query="Reverberation là dạng năng lượng gì theo các ghi chép khoa học?",
        expected_source_type="wiki",
        key_terms=["Reverberation", "Frequency", "Waveworn", "Matter"],
    ),

    # ── Domain 2: Wuthering Waves Wiki — Threnodian, The Lament & Monsters ──
    BenchmarkCase(
        id="BM05",
        domain="Wiki: The Lament & Cataclysm",
        query="Thảm họa The Lament đã tàn phá nền văn minh nhân loại trên hành tinh Solaris-3 như thế nào?",
        expected_source_type="wiki",
        key_terms=["The Lament", "Solaris-3", "Tacet Discord", "Frequency"],
    ),
    BenchmarkCase(
        id="BM06",
        domain="Wiki: Threnodian & Entities",
        query="Threnodian là thực thể gì và chúng có khả năng thao túng Tacet Discord ra sao?",
        expected_source_type="wiki",
        key_terms=["Threnodian", "Tacet Discord", "Lament", "Entity"],
    ),
    BenchmarkCase(
        id="BM07",
        domain="Wiki: Monsters & Fields",
        query="Cơ chế tái sinh và hấp thụ tần số của quái vật Tacet Discord tại các Tacet Field?",
        expected_source_type="wiki",
        key_terms=["Tacet Discord", "Tacet Field", "Frequency", "Energy"],
    ),
    BenchmarkCase(
        id="BM08",
        domain="Wiki: World Lore",
        query="Quái vật Leviathan và Dị thể Tacet có đặc điểm nhận dạng gì?",
        expected_source_type="wiki",
        key_terms=["Leviathan", "Tacet Discord", "Frequency", "Solaris"],
    ),

    # ── Domain 3: Wuthering Waves Wiki — Factions, Regions & Technology ──
    BenchmarkCase(
        id="BM09",
        domain="Wiki: Factions & Academy",
        query="Học viện Startorch Academy tại Lahai-Roi có cơ cấu tổ chức và mục tiêu nghiên cứu gì?",
        expected_source_type="wiki",
        key_terms=["Startorch Academy", "Lahai-Roi", "Resonator", "Research"],
    ),
    BenchmarkCase(
        id="BM10",
        domain="Wiki: Technology & Regions",
        query="Hệ thống thiết bị Pangu Terminal tại Hoàng Long (Huanglong) và Jinzhou hoạt động thế nào?",
        expected_source_type="wiki",
        key_terms=["Terminal", "Pangu", "Huanglong", "Jinzhou"],
    ),
    BenchmarkCase(
        id="BM11",
        domain="Wiki: Quests & Lore",
        query="Torn Pages và Abandoned Data Chips trong nhiệm vụ Tales of the Past and Present mang lại thông tin gì?",
        expected_source_type="wiki",
        key_terms=["Tales of the Past", "Torn Pages", "Jinzhou", "Chips"],
    ),
    BenchmarkCase(
        id="BM12",
        domain="Wiki: Regions & Defense",
        query="Thành phố Jinzhou và lực lượng Midnight Rangers giữ vai trò gì trong phòng thủ Hoàng Long?",
        expected_source_type="wiki",
        key_terms=["Jinzhou", "Huanglong", "Midnight Rangers", "Defense"],
    ),

    # ── Domain 4: Chisa Character Core & Combat Mechanics ──
    BenchmarkCase(
        id="BM13",
        domain="Chisa: Combat & Forte",
        query="Cơ chế hoạt động của năng lực Forte Thread Perception và vũ khí kéo Broadblade của Chisa?",
        expected_source_type="chisa_lore",
        key_terms=["Thread Perception", "Broadblade", "kéo", "sợi tơ"],
    ),
    BenchmarkCase(
        id="BM14",
        domain="Chisa: Resonator Profile",
        query="Dấu ấn Tacet Mark của Chisa nằm ở vị trí nào và thuộc hệ nguyên tố nào?",
        expected_source_type="chisa_lore",
        key_terms=["Tacet Mark", "Havoc", "cánh tay", "Resonator"],
    ),
    BenchmarkCase(
        id="BM15",
        domain="Chisa: Health & State",
        query="Hiện tượng quá tải tần số Overclocking của Chisa có triệu chứng nguy hiểm gì?",
        expected_source_type="chisa_lore",
        key_terms=["Overclock", "tần số", "quá tải", "biến dị"],
    ),
    BenchmarkCase(
        id="BM16",
        domain="Chisa: Profile & Lifestyle",
        query="Thói quen ăn uống và món đồ ngọt ưa thích của Chisa lúc rảnh rỗi là gì?",
        expected_source_type="chisa_lore",
        key_terms=["socola", "Pocky", "ngọt", "trà"],
    ),

    # ── Domain 5: Story, Deep Relationships & Sonoro Sphere ──
    BenchmarkCase(
        id="BM17",
        domain="Chisa: Relationship with Rover",
        query="Chisa cảm thấy thế nào về Senpai (Rover) và lời thề nguyện đồng hành bảo vệ Senpai?",
        expected_source_type="chisa_lore",
        key_terms=["Senpai", "Rover", "bảo vệ", "gắn kết"],
    ),
    BenchmarkCase(
        id="BM18",
        domain="Chisa: Story & Sumika",
        query="Nội dung cuốn nhật ký của cứu hộ viên quá cố Sumika trong Sonoro Sphere Honami?",
        expected_source_type="chisa_lore",
        key_terms=["Sumika", "nhật ký", "Honami", "vòng lặp"],
    ),
    BenchmarkCase(
        id="BM19",
        domain="Chisa: Breaking The Loop",
        query="Chisa và Rover đã phối hợp giải mã và phá vỡ vòng lặp 20 năm của Honami Loop như thế nào?",
        expected_source_type="chisa_lore",
        key_terms=["Honami", "vòng lặp", "Rover", "phá vỡ"],
    ),
    BenchmarkCase(
        id="BM20",
        domain="Chisa: Sonoro Sphere Isolation",
        query="Không gian Sonoro Sphere Honami đã cô lập Chisa suốt 20 năm ngưng đọng thời gian ra sao?",
        expected_source_type="chisa_lore",
        key_terms=["Sonoro Sphere", "Honami", "20 năm", "ngưng đọng"],
    ),
]


async def run_single_benchmark(case: BenchmarkCase, user_id_prefix: str) -> Dict[str, Any]:
    user_id = f"{user_id_prefix}_{case.id.lower()}"
    start_time = time.time()
    
    trace_id = pipeline_tracker.start_trace(user_id=user_id, message=case.query, pipeline="benchmark")
    
    try:
        async with AsyncSessionFactory() as session:
            reply, emotions = await container.chat_engine.chat(
                session=session,
                user_id=user_id,
                user_message=case.query
            )
        pipeline_tracker.end_trace(response_text=reply, emotions=emotions)
    except Exception as e:
        reply = f"[ERROR]: {e}"
        emotions = {}
        pipeline_tracker.end_trace(response_text=reply, emotions=emotions, status="error")
        
    duration = round(time.time() - start_time, 2)
    
    # Inspect trace from Redis
    r = get_redis_client()
    raw = await r.lindex("chisa:pipeline_history", 0)
    trace_data = {}
    if raw:
        try:
            trace_data = json.loads(raw)
        except Exception:
            pass
            
    # Extract telemetry metrics
    intents = []
    routing_method = "UNKNOWN"
    extracted_entities = []
    expanded_entities = []
    retrieved_chunks = []
    scoring_details = []
    use_deep_thinking = False
    reasoning_chars = 0
    token_in = 0
    token_out = 0
    
    for s in trace_data.get("steps", []):
        sname = s.get("name")
        sdata = s.get("data", {})
        if sname in ("intent_classification", "intent_stage"):
            intents = sdata.get("intents", [])
            routing_method = sdata.get("routing_method", "L3_SEMANTIC")
        elif sname in ("rag_retrieval", "rag_stage"):
            extracted_entities = sdata.get("extracted_entities", [])
            expanded_entities = sdata.get("expanded_entities", [])
            retrieved_chunks = sdata.get("retrieved_lore_chunks", [])
            scoring_details = sdata.get("lore_scoring_details", [])
        elif sname == "context_building":
            use_deep_thinking = sdata.get("use_deep_thinking", False)
        elif sname == "llm_generation" and sdata.get("purpose") == "chat_response":
            use_deep_thinking = sdata.get("use_deep_thinking", use_deep_thinking)
            reasoning = sdata.get("reasoning_content") or ""
            reasoning_chars = len(reasoning)
            token_in = sdata.get("input_tokens", 0)
            token_out = sdata.get("output_tokens", 0)
            
    # Evaluate Data Utilization
    found_terms = [t for t in case.key_terms if t.lower() in reply.lower() or any(t.lower() in c.lower() for c in retrieved_chunks)]
    utilization_score = len(found_terms) / len(case.key_terms) if case.key_terms else 1.0
    passed = len(retrieved_chunks) > 0 and len(found_terms) >= 1
    
    # Identify Chunk Sources (Wiki vs Lore)
    wiki_chunks_count = 0
    lore_chunks_count = 0
    for d in scoring_details:
        col = d.get("collection", "")
        if col in ("world_lore", "wiki") or d.get("source_type") == "wiki":
            wiki_chunks_count += 1
        else:
            lore_chunks_count += 1
            
    return {
        "id": case.id,
        "domain": case.domain,
        "query": case.query,
        "passed": passed,
        "duration_sec": duration,
        "intents": intents,
        "routing_method": routing_method,
        "extracted_entities": extracted_entities,
        "expanded_entities_count": len(expanded_entities),
        "retrieved_chunks_count": len(retrieved_chunks),
        "wiki_chunks_count": wiki_chunks_count,
        "lore_chunks_count": lore_chunks_count,
        "top_hybrid_score": scoring_details[0].get("hybrid_score", 0.0) if scoring_details else 0.0,
        "top_canon_title": scoring_details[0].get("canonical_name") or scoring_details[0].get("heading_path") if scoring_details else "-",
        "use_deep_thinking": use_deep_thinking,
        "reasoning_chars": reasoning_chars,
        "token_in": token_in,
        "token_out": token_out,
        "matched_key_terms": found_terms,
        "utilization_pct": round(utilization_score * 100, 1),
        "reply": reply,
        "retrieved_chunks_preview": [c[:180].replace("\n", " ") + "..." for c in retrieved_chunks[:3]]
    }


async def main():
    print("=" * 85)
    print(" 🚀 WUTHERING WAVES & CHISA BOT: 20-QUESTION DATA UTILIZATION BENCHMARK")
    print("=" * 85)
    print(f"Total Test Cases: {len(BENCHMARK_CASES)} across 5 Domains (Wiki, World, Mechanics, Lore, Story)")
    
    # Warmup dependencies
    container.entity_resolver.load()
    _ = container.embedder
    
    user_id_prefix = f"bm_{int(time.time())}"
    results = []
    
    for idx, case in enumerate(BENCHMARK_CASES, 1):
        print(f"\n[{idx:02d}/{len(BENCHMARK_CASES):02d}] 🧪 Running {case.id}: {case.domain}")
        print(f"     ❓ Query: \"{case.query}\"")
        
        res = await run_single_benchmark(case, user_id_prefix)
        results.append(res)
        
        status_badge = "✅ PASS" if res["passed"] else "❌ FAIL"
        cot_badge = f"🧠 CoT ON ({res['reasoning_chars']} chars)" if res["use_deep_thinking"] else "CoT OFF"
        
        print(f"     {status_badge} | Latency: {res['duration_sec']}s | Chunks: {res['retrieved_chunks_count']} (🌐 Wiki: {res['wiki_chunks_count']} | 🌸 Lore: {res['lore_chunks_count']})")
        print(f"     📊 Top Match: '{res['top_canon_title']}' (Score: {res['top_hybrid_score']}) | {cot_badge}")
        print(f"     🏷️  Entities: {res['extracted_entities']} | Matched KWs: {res['matched_key_terms']} ({res['utilization_pct']}%)")
        print(f"     🌸 Chisa Reply Preview: \"{res['reply'][:120]}...\"")
        
        # Brief pause between test calls
        await asyncio.sleep(0.3)
        
    # ── Summary Report ──
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    wiki_total_chunks = sum(r["wiki_chunks_count"] for r in results)
    lore_total_chunks = sum(r["lore_chunks_count"] for r in results)
    cot_on_count = sum(1 for r in results if r["use_deep_thinking"])
    avg_score = sum(r["top_hybrid_score"] for r in results) / total if total > 0 else 0
    avg_util = sum(r["utilization_pct"] for r in results) / total if total > 0 else 0
    avg_latency = sum(r["duration_sec"] for r in results) / total if total > 0 else 0

    print("\n" + "=" * 85)
    print(" 📈 BENCHMARK SUMMARY & DATA UTILIZATION METRICS")
    print("=" * 85)
    print(f"  • Total Test Cases           : {total}")
    print(f"  • Passed Cases               : {passed_count}/{total} ({passed_count/total*100:.1f}%)")
    print(f"  • Average Latency per Query  : {avg_latency:.2f}s")
    print(f"  • Total Chunks Retrieved     : {wiki_total_chunks + lore_total_chunks} (🌐 Wiki Chunks: {wiki_total_chunks} | 🌸 Custom Lore: {lore_total_chunks})")
    print(f"  • Average Top-1 Hybrid Score : {avg_score:.4f}")
    print(f"  • Data Utilization Rate      : {avg_util:.1f}%")
    print(f"  • Deep Reasoning (CoT) Rate  : {cot_on_count}/{total} ({cot_on_count/total*100:.1f}%)")
    print("=" * 85)

    # Export results to JSON
    output_path = PROJECT_ROOT / "tests" / "benchmark_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "total": total,
                "passed": passed_count,
                "pass_rate": f"{passed_count/total*100:.1f}%",
                "wiki_chunks_retrieved": wiki_total_chunks,
                "lore_chunks_retrieved": lore_total_chunks,
                "cot_active_rate": f"{cot_on_count/total*100:.1f}%",
                "avg_top_score": round(avg_score, 4),
                "avg_utilization": f"{avg_util:.1f}%",
                "avg_latency_sec": round(avg_latency, 2)
            },
            "cases": results
        }, f, indent=2, ensure_ascii=False)
        
    print(f"\n[+] Detailed benchmark report saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
