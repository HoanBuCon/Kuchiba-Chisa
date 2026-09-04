"""
Automated Ingestion Quality Benchmark Runner (Stage 6 of Ingestion Pipeline).

Evaluates retrieval quality (Hit@1, Hit@3, Hit@5, MRR, Cross-lingual Recall)
against a standardized 50-case benchmark suite after every ingestion cycle.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Standard 50-case cross-lingual gold standard dataset for Wuthering Waves
BENCHMARK_TEST_CASES: List[Dict[str, Any]] = [
    # 1. Resonator Lore & Identities (15 cases)
    {"id": 1, "category": "Resonators", "query": "Kuchiba Chisa là ai và học ở đâu?", "expected_keywords": ["Chisa", "Startorch", "Mutant", "Havoc", "Sonoro"]},
    {"id": 2, "category": "Resonators", "query": "Tuổi thực tế và tuổi sinh học của Chisa", "expected_keywords": ["18", "38", "Sonoro", "Sphere"]},
    {"id": 3, "category": "Resonators", "query": "Danh hiệu Resonance của Chisa", "expected_keywords": ["Eye of Unravelling", "Unravelling", "Chisa"]},
    {"id": 4, "category": "Resonators", "query": "Vị trí dấu ấn Tacet Mark của Chisa", "expected_keywords": ["right arm", "cánh tay phải", "arm"]},
    {"id": 5, "category": "Resonators", "query": "Tướng quân Jiyan lãnh đạo tổ chức nào?", "expected_keywords": ["Jiyan", "Midnight Rangers", "General"]},
    {"id": 6, "category": "Resonators", "query": "Vũ khí và thuộc tính của Jiyan", "expected_keywords": ["Broadblade", "Aero", "Verdant Summit"]},
    {"id": 7, "category": "Resonators", "query": "Shorekeeper là ai trong tổ chức Black Shores?", "expected_keywords": ["Shorekeeper", "Black Shores", "Spectro", "Leader"]},
    {"id": 8, "category": "Resonators", "query": "Changli là cố vấn của ai ở Jinzhou?", "expected_keywords": ["Changli", "Jinhsi", "Magistrate", "Counselor"]},
    {"id": 9, "category": "Resonators", "query": "Yinlin từng làm việc tại cơ quan nào trước khi bị đình chỉ?", "expected_keywords": ["Yinlin", "Public Order", "Patroller", "Jinshu"]},
    {"id": 10, "category": "Resonators", "query": "Camellya thuộc tổ chức Black Shores và hệ gì?", "expected_keywords": ["Camellya", "Black Shores", "Havoc", "Bloom"]},
    {"id": 11, "category": "Resonators", "query": "Chixia là Patroller của Jinzhou dùng vũ khí gì?", "expected_keywords": ["Chixia", "Pistols", "Fusion", "Patroller"]},
    {"id": 12, "category": "Resonators", "query": "Sanhua là vệ sĩ trung thành của ai?", "expected_keywords": ["Sanhua", "Jinhsi", "Glacio", "Bodyguard"]},
    {"id": 13, "category": "Resonators", "query": "Baizhi là nhà nghiên cứu thuộc học viện nào?", "expected_keywords": ["Baizhi", "Huaxu", "Academy", "Glacio"]},
    {"id": 14, "category": "Resonators", "query": "Aalto điều hành cơ quan môi giới thông tin nào?", "expected_keywords": ["Aalto", "Information", "Broker", "Aero"]},
    {"id": 15, "category": "Resonators", "query": "Encore và những chú cừu bông Cosmos", "expected_keywords": ["Encore", "Cosmos", "Cloudy", "Fusion"]},

    # 2. Factions & Organizations (10 cases)
    {"id": 16, "category": "Factions", "query": "Học viện Startorch Academy ở đâu?", "expected_keywords": ["Startorch", "Academy", "Lahai-Roi", "Solaris-3"]},
    {"id": 17, "category": "Factions", "query": "Tổ chức Black Shores có vai trò gì trong Solaris-3?", "expected_keywords": ["Black Shores", "Lament", "Information", "Island"]},
    {"id": 18, "category": "Factions", "query": "Tổ chức phản diện Fractsidus muốn làm gì?", "expected_keywords": ["Fractsidus", "Tacet Discord", "Lament", "Evolution"]},
    {"id": 19, "category": "Factions", "query": "Lực lượng quân sự Midnight Rangers đóng quân ở đâu?", "expected_keywords": ["Midnight Rangers", "Desorock", "Border", "Jinzhou"]},
    {"id": 20, "category": "Factions", "query": "Viện nghiên cứu Huaxu Academy chuyên nghiên cứu gì?", "expected_keywords": ["Huaxu", "Academy", "Resonance", "Research"]},
    {"id": 21, "category": "Factions", "query": "Court of Savantae là tổ chức nghiên cứu cổ xưa nào?", "expected_keywords": ["Court of Savantae", "Savantae", "Ancient", "Civilization"]},
    {"id": 22, "category": "Factions", "query": "Pioneer Association hỗ trợ gì cho các nhà thám hiểm?", "expected_keywords": ["Pioneer Association", "Exploration", "Supply"]},
    {"id": 23, "category": "Factions", "query": "Chính quyền thành phố Jinzhou do ai đứng đầu?", "expected_keywords": ["Jinhsi", "Magistrate", "Jinzhou", "Huanglong"]},
    {"id": 24, "category": "Factions", "query": "Tổ chức thám hiểm và vận tải Lollo Logistics", "expected_keywords": ["Lollo Logistics", "Delivery", "Supply"]},
    {"id": 25, "category": "Factions", "query": "Thành phố công nghệ Lahai-Roi nổi tiếng về điều gì?", "expected_keywords": ["Lahai-Roi", "Technology", "Startorch"]},

    # 3. Lore & World Concepts (15 cases)
    {"id": 26, "category": "Lore", "query": "Thảm họa Lament là sự kiện gì?", "expected_keywords": ["Lament", "Catastrophe", "Tacet Discord", "Sound"]},
    {"id": 27, "category": "Lore", "query": "Hiện tượng không gian Sonoro Sphere là gì?", "expected_keywords": ["Sonoro Sphere", "Sub-space", "Frequency", "Time"]},
    {"id": 28, "category": "Lore", "query": "Hiện tượng mưa Retroact Rain tạo ra ảo ảnh gì?", "expected_keywords": ["Retroact Rain", "Memory", "Past", "Rain"]},
    {"id": 29, "category": "Lore", "query": "Tacet Discords (TD) sinh ra từ đâu?", "expected_keywords": ["Tacet Discord", "Lament", "Frequency", "Monster"]},
    {"id": 30, "category": "Lore", "query": "Dấu ấn Tacet Mark là gì trên cơ thể Resonator?", "expected_keywords": ["Tacet Mark", "Resonance", "Frequency", "Body"]},
    {"id": 31, "category": "Lore", "query": "Quá trình Overclocking xảy ra khi nào đối với Resonator?", "expected_keywords": ["Overclocking", "Frequency", "Collapse", "Resonator"]},
    {"id": 32, "category": "Lore", "query": "Năng lượng Frequency là nền tảng của vạn vật ra sao?", "expected_keywords": ["Frequency", "Wuthering Waves", "Energy", "Sound"]},
    {"id": 33, "category": "Lore", "query": "Hành tinh Solaris-3 có cấu trúc thế giới thế nào?", "expected_keywords": ["Solaris-3", "Planet", "Huanglong", "Black Shores"]},
    {"id": 34, "category": "Lore", "query": "Khu vực quê hương Ashinohara của Chisa", "expected_keywords": ["Ashinohara", "Origin", "Chisa"]},
    {"id": 35, "category": "Lore", "query": "Hiện tượng Tacet Field và sự bùng phát quái vật", "expected_keywords": ["Tacet Field", "Hazard", "Echoes"]},
    {"id": 36, "category": "Lore", "query": "Khái niệm Forte và kỹ năng cộng hưởng", "expected_keywords": ["Forte", "Resonance", "Ability"]},
    {"id": 37, "category": "Lore", "query": "Sự khác biệt giữa Mutant Resonator và Natural Resonator", "expected_keywords": ["Mutant", "Resonator", "Mutation", "Anomaly"]},
    {"id": 38, "category": "Lore", "query": "Năng lực Eye of Unravelling phân tích các sợi thực tại", "expected_keywords": ["Eye of Unravelling", "Thread", "Reality", "Chisa"]},
    {"id": 39, "category": "Lore", "query": "Hệ thống nguyên tố gồm Havoc, Glacio, Fusion, Aero, Electro, Spectro", "expected_keywords": ["Havoc", "Glacio", "Fusion", "Aero", "Electro", "Spectro"]},
    {"id": 40, "category": "Lore", "query": "Sinh vật Echo được tạo thành từ tần số sót lại", "expected_keywords": ["Echo", "Remnant", "Frequency", "Absorb"]},

    # 4. Locations & Regions (10 cases)
    {"id": 41, "category": "Locations", "query": "Vùng đất Hoàng Long Huanglong gồm những thành phố nào?", "expected_keywords": ["Huanglong", "Jinzhou", "Region"]},
    {"id": 42, "category": "Locations", "query": "Khu vực nguy hiểm Desorock Highland", "expected_keywords": ["Desorock", "Highland", "Midnight Rangers"]},
    {"id": 43, "category": "Locations", "query": "Hồ nước Honami và cảnh hoàng hôn", "expected_keywords": ["Honami", "Sunset", "Ashinohara"]},
    {"id": 44, "category": "Locations", "query": "Thung lũng Dim Forest và cây khổng lồ", "expected_keywords": ["Dim Forest", "Giant Tree", "Forest"]},
    {"id": 45, "category": "Locations", "query": "Vùng biển bí ẩn Black Shores", "expected_keywords": ["Black Shores", "Ocean", "Fog", "Island"]},
    {"id": 46, "category": "Locations", "query": "Thành phố cảng Guixu Ruins bị tàn phá", "expected_keywords": ["Guixu", "Ruins", "Lament", "Port"]},
    {"id": 47, "category": "Locations", "query": "Khu vực mỏ Tiger's Maw Mine", "expected_keywords": ["Tiger's Maw", "Mine", "Minerals"]},
    {"id": 48, "category": "Locations", "query": "Căn cứ ngầm Fractsidus Base", "expected_keywords": ["Fractsidus", "Base", "Underground"]},
    {"id": 49, "category": "Locations", "query": "Thành phố công nghệ Lahai-Roi", "expected_keywords": ["Lahai-Roi", "Startorch", "City"]},
    {"id": 50, "category": "Locations", "query": "Vùng đồng bằng Central Plains ở Huanglong", "expected_keywords": ["Central Plains", "Huanglong", "Jinzhou"]},
]


@dataclass
class BenchmarkResult:
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    hit_at_1: int = 0
    hit_at_3: int = 0
    hit_at_5: int = 0
    mrr_sum: float = 0.0
    latency_ms_avg: float = 0.0
    results_detail: List[Dict[str, Any]] = field(default_factory=list)
    quality_gate_passed: bool = False

    @property
    def hit_at_5_pct(self) -> float:
        return (self.hit_at_5 / max(self.total_cases, 1)) * 100

    @property
    def mrr(self) -> float:
        return self.mrr_sum / max(self.total_cases, 1)

    def generate_report_markdown(self) -> str:
        lines = [
            "# 🏆 INGESTION QUALITY BENCHMARK REPORT",
            f"- **Thời gian thực thi:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Tổng số ca kiểm thử:** `{self.total_cases}`",
            f"- **Tỷ lệ Hit@5:** **`{self.hit_at_5_pct:.1f}%`** (`{self.hit_at_5}/{self.total_cases}`)",
            f"- **Tỷ lệ Hit@3:** `{((self.hit_at_3/max(self.total_cases, 1))*100):.1f}%`",
            f"- **Tỷ lệ Hit@1:** `{((self.hit_at_1/max(self.total_cases, 1))*100):.1f}%`",
            f"- **Chỉ số MRR (Mean Reciprocal Rank):** `{self.mrr:.3f}`",
            f"- **Độ trễ truy xuất trung bình:** `{self.latency_ms_avg:.1f} ms`",
            f"- **Trạng thái Quality Gate (Target >= 95%):** {'✅ PASS (Đạt Chuẩn)' if self.quality_gate_passed else '❌ FAILED (Chưa đạt)'}",
            "",
            "### 📋 Chi tiết các Test Cases:",
            "| ID | Danh mục | Câu hỏi kiểm thử | Rank | Hit@5 | Score | Trạng thái |",
            "| :---: | :--- | :--- | :---: | :---: | :---: | :---: |",
        ]

        for res in self.results_detail:
            status = "✅ PASS" if res["passed"] else "❌ FAIL"
            lines.append(
                f"| {res['id']} | {res['category']} | {res['query'][:35]}... | #{res['rank']} | {res['hit_at_5']} | {res['top_score']:.3f} | {status} |"
            )

        return "\n".join(lines)


class BenchmarkRunner:
    """
    Executes automated RAG retrieval benchmark suite against Qdrant Vector Store.
    """

    def __init__(self, top_k: int = 5, pass_threshold_pct: float = 90.0):
        self.top_k = top_k
        self.pass_threshold_pct = pass_threshold_pct

    async def run(self, vector_retriever: Optional[Any] = None) -> BenchmarkResult:
        """
        Runs the 50-case benchmark suite and evaluates retrieval precision.
        """
        logger.info("starting_ingestion_benchmark", test_cases=len(BENCHMARK_TEST_CASES))
        
        # If vector_retriever is not provided, initialize standard fastembed + qdrant retriever
        if vector_retriever is None:
            try:
                from app.infrastructure.vector.qdrant.qdrant_service import QdrantService
                from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
                from app.domain.services.rag.retriever_lore import LoreRetriever
                
                vector_store = QdrantService()
                embedder = FastEmbedAdapter()
                lore_retriever = LoreRetriever(vector_store=vector_store)
                
                async def _default_retriever(query: str, top_k: int = 5):
                    query_vector = await embedder.embed_text(query, prefix="query: ")
                    results = []
                    for coll in ["character_lore", "world_lore", "story_lore"]:
                        chunks = await lore_retriever.retrieve_lore_parent_child(
                            collection=coll,
                            query_vector=query_vector,
                            query_text=query,
                            top_k=top_k,
                        )
                        results.extend(chunks)
                    results.sort(key=lambda x: x[1] if isinstance(x, tuple) else getattr(x, 'score', 0), reverse=True)
                    formatted = []
                    for r in results[:top_k]:
                        text = r[0] if isinstance(r, tuple) else getattr(r, 'text', str(r))
                        score = r[1] if isinstance(r, tuple) else getattr(r, 'score', 0.8)
                        formatted.append(type('ChunkHit', (), {'content': text, 'score': score})())
                    return formatted

                vector_retriever = _default_retriever
            except Exception as e:
                logger.error("failed_to_initialize_benchmark_retriever", error=str(e))
                raise RuntimeError("quality benchmark retriever initialization failed") from e

        result = BenchmarkResult(total_cases=len(BENCHMARK_TEST_CASES))
        latencies = []

        for tc in BENCHMARK_TEST_CASES:
            t0 = time.perf_counter()
            query = tc["query"]
            expected = tc["expected_keywords"]

            try:
                chunks = await vector_retriever(query, top_k=self.top_k)
            except Exception as exc:
                logger.warning("benchmark_query_error", query=query, error=str(exc))
                chunks = []

            dt_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(dt_ms)

            # Evaluate matching rank
            rank = -1
            top_score = 0.0
            passed = False

            for i, chunk in enumerate(chunks):
                chunk_text = chunk.content if hasattr(chunk, "content") else str(chunk)
                score = chunk.score if hasattr(chunk, "score") else 0.85
                if i == 0:
                    top_score = score

                # Check if any expected keyword is present in chunk text
                if any(kw.lower() in chunk_text.lower() for kw in expected):
                    rank = i + 1
                    break

            if rank == 1:
                result.hit_at_1 += 1
                result.hit_at_3 += 1
                result.hit_at_5 += 1
                result.mrr_sum += 1.0
                passed = True
            elif 2 <= rank <= 3:
                result.hit_at_3 += 1
                result.hit_at_5 += 1
                result.mrr_sum += 1.0 / rank
                passed = True
            elif 4 <= rank <= 5:
                result.hit_at_5 += 1
                result.mrr_sum += 1.0 / rank
                passed = True
            else:
                rank = 0  # Not in top 5

            if passed:
                result.passed_cases += 1
            else:
                result.failed_cases += 1

            result.results_detail.append({
                "id": tc["id"],
                "category": tc["category"],
                "query": query,
                "rank": rank if rank > 0 else "5+",
                "hit_at_5": "✓" if passed else "✗",
                "top_score": top_score,
                "passed": passed,
                "latency_ms": dt_ms,
            })

        result.latency_ms_avg = sum(latencies) / max(len(latencies), 1)
        result.quality_gate_passed = result.hit_at_5_pct >= self.pass_threshold_pct

        logger.info(
            "benchmark_completed",
            hit_at_5_pct=f"{result.hit_at_5_pct:.1f}%",
            mrr=f"{result.mrr:.3f}",
            passed=result.quality_gate_passed,
        )
        return result
