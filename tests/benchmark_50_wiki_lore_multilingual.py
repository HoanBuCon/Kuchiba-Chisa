"""
================================================================================
BENCHMARK 50 MULTILINGUAL WIKI LORE RETRIEVAL & PARAMETER OPTIMIZATION
================================================================================
- Evaluates Cross-Language (Vietnamese query -> English Wiki corpus) RAG Retrieval.
- 50 diverse questions covering Characters, World, Factions, Lore Concepts, and Quests.
- Computes Hit Rate@1, Hit Rate@3, Hit Rate@5, MRR (Mean Reciprocal Rank), Latency.
- Runs Grid Search / Optimization across Hybrid Weights and Score Thresholds.
- Outputs detailed report to console and `tests/logs/benchmark_50_wiki_lore.log`.
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
from pathlib import Path
from typing import List, Dict, Any, Tuple

from app.config.settings import settings
from app.infrastructure.vector.qdrant.qdrant_service import (
    qdrant_service,
    COLLECTION_CHARACTER_LORE,
    COLLECTION_WORLD_LORE,
    COLLECTION_STORY_LORE,
)
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.domain.services.rag.entity_resolver import EntityResolver
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.domain.tuning.rag import RAGTuning


# ──────────────────────────────────────────────────────────────────────────────
# 50 MULTILINGUAL BENCHMARK QUESTIONS (VIETNAMESE -> ENGLISH WIKI)
# ──────────────────────────────────────────────────────────────────────────────
BENCHMARK_50_QUESTIONS: List[Dict[str, Any]] = [
    # ── GROUP 1: RESONATORS & CHARACTER LORE (20 Questions) ──
    {
        "id": 1,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Chixia sử dụng loại vũ khí nào và năng lực Forte của cô ấy là gì?",
        "expected_entities": ["Chixia"],
        "keywords": ["Chixia", "Gallant Blaze", "Pistols", "Dual Pistols", "Resonator"]
    },
    {
        "id": 2,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Jiyan là thủ lĩnh của đội quân nào và mang Rồng gì khi chiến đấu?",
        "expected_entities": ["Jiyan"],
        "keywords": ["Jiyan", "Midnight Rangers", "Qingloong", "Broadblade", "General"]
    },
    {
        "id": 3,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Jinhsi là quan trấn thủ của thành phố nào và có mối liên kết với Thánh Thú nào?",
        "expected_entities": ["Jinhsi"],
        "keywords": ["Jinhsi", "Jinzhou", "Magistrate", "Jué", "Sentinel"]
    },
    {
        "id": 4,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Yinlin từng làm việc cho cơ quan an ninh nào trước khi hoạt động ngầm?",
        "expected_entities": ["Yinlin"],
        "keywords": ["Yinlin", "Public Security", "Patroller", "Puppet", "Zapstring"]
    },
    {
        "id": 5,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Changli là quân sư cho ai và sở hữu năng lực hệ gì?",
        "expected_entities": ["Changli"],
        "keywords": ["Changli", "Jinhsi", "Counselor", "Fusion", "Sword"]
    },
    {
        "id": 6,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Shorekeeper là người bảo hộ vùng đất nào và có vai trò gì với Black Shores?",
        "expected_entities": ["Shorekeeper"],
        "keywords": ["Shorekeeper", "Black Shores", "Tethys", "Stellarealm", "Guardian"]
    },
    {
        "id": 7,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Camellya thuộc tổ chức Black Shores có tính cách và phong cách chiến đấu thế nào?",
        "expected_entities": ["Camellya"],
        "keywords": ["Camellya", "Black Shores", "Bloom", "Havoc", "Vine"]
    },
    {
        "id": 8,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Yangyang là Outrider của Jinzhou sử dụng vũ khí và Forte hệ Khí (Aero) như thế nào?",
        "expected_entities": ["Yangyang"],
        "keywords": ["Yangyang", "Outrider", "Aero", "Sword", "Feather"]
    },
    {
        "id": 9,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Baizhi là nhà nghiên cứu tại học viện Huaxu với sinh vật cộng sinh tên là gì?",
        "expected_entities": ["Baizhi"],
        "keywords": ["Baizhi", "Huaxu", "You'tan", "Glacio", "Rectifier"]
    },
    {
        "id": 10,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Sanhua bị mất thị giác thông thường nhưng nhìn thấy thế giới qua tần số sóng như thế nào?",
        "expected_entities": ["Sanhua"],
        "keywords": ["Sanhua", "Vision", "Frequency", "Glacio", "Guard"]
    },
    {
        "id": 11,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Danjin sử dụng máu và kiếm Crimson Blade để trừng phạt kẻ xấu ra sao?",
        "expected_entities": ["Danjin"],
        "keywords": ["Danjin", "Havoc", "Sword", "Crimson", "Justice"]
    },
    {
        "id": 12,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Aalto là nhân viên môi giới thông tin của công ty dịch vụ nào?",
        "expected_entities": ["Aalto"],
        "keywords": ["Aalto", "Black Shores", "Information", "Aero", "Mist"]
    },
    {
        "id": 13,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Encore có hai chú cừu bông tên là gì và mang tính cách như thế nào?",
        "expected_entities": ["Encore"],
        "keywords": ["Encore", "Cosmos", "Cloudy", "Fusion", "Wooly"]
    },
    {
        "id": 14,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Mortefi là nhà nghiên cứu vũ khí tại Học viện Huaxu dễ mất bình tĩnh khi nào?",
        "expected_entities": ["Mortefi"],
        "keywords": ["Mortefi", "Huaxu", "Dragon", "Fusion", "Pistols", "Anger"]
    },
    {
        "id": 15,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Zhezhi là họa sĩ tài năng sử dụng bút vẽ mực ma thuật hệ Glacio như thế nào?",
        "expected_entities": ["Zhezhi"],
        "keywords": ["Zhezhi", "Painter", "Brush", "Glacio", "Ink"]
    },
    {
        "id": 16,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Xiangli Yao là Viện trưởng trẻ tuổi của Học viện Huaxu nghiên cứu về lĩnh vực gì?",
        "expected_entities": ["Xiangli Yao"],
        "keywords": ["Xiangli Yao", "Huaxu", "Principal", "Electro", "Gauntlet", "Automaton"]
    },
    {
        "id": 17,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Carlotta là tiểu thư của gia tộc nào tại Rinascita?",
        "expected_entities": ["Carlotta"],
        "keywords": ["Carlotta", "Rinascita", "Montelli", "Glacio", "Pistols"]
    },
    {
        "id": 18,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Lingyang có nguồn gốc là sinh vật Liondance Suan'ni thức tỉnh Forte thế nào?",
        "expected_entities": ["Lingyang"],
        "keywords": ["Lingyang", "Liondance", "Suan'ni", "Glacio", "Gauntlet"]
    },
    {
        "id": 19,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Taoqi phụ trách công tác an ninh tại Bộ Quốc phòng Jinzhou với Forte hộ thuẫn gì?",
        "expected_entities": ["Taoqi"],
        "keywords": ["Taoqi", "Ministry of Development", "Shield", "Havoc", "Broadblade"]
    },
    {
        "id": 20,
        "category": "Character",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Verina là cô bé thực vật học thuộc Đội Tiên phong Pioneer Association có năng lực gì?",
        "expected_entities": ["Verina"],
        "keywords": ["Verina", "Pioneer Association", "Plant", "Spectro", "Photosynthesis"]
    },

    # ── GROUP 2: WORLD, REGIONS, FACTIONS & LORE CONCEPTS (15 Questions) ──
    {
        "id": 21,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Jinzhou là thành phố thuộc lục địa nào và có vị trí chiến lược ra sao?",
        "expected_entities": ["Jinzhou", "Huanglong"],
        "keywords": ["Jinzhou", "Huanglong", "Border", "City", "Magistrate"]
    },
    {
        "id": 22,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Thảm họa Lament là gì và đã làm thay đổi thế giới Solaris-3 như thế nào?",
        "expected_entities": ["Lament", "Solaris-3"],
        "keywords": ["Lament", "Solaris-3", "Cataclysm", "Tacet Discords", "Collapse"]
    },
    {
        "id": 23,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Hiện tượng Mưa ngược Retroact Rain sinh ra từ đâu và gây ảnh hưởng gì?",
        "expected_entities": ["Retroact Rain"],
        "keywords": ["Retroact Rain", "Frequency", "Remnant", "Illusion", "Rain"]
    },
    {
        "id": 24,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Tổ chức Black Shores (Hắc Ngạn) nằm ở đâu và có sứ mệnh kết nối thế giới ra sao?",
        "expected_entities": ["Black Shores"],
        "keywords": ["Black Shores", "Tethys", "System", "Islands", "Consultant"]
    },
    {
        "id": 25,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Quân đoàn Midnight Rangers đóng quân ở đâu và bảo vệ biên giới Huanglong thế nào?",
        "expected_entities": ["Midnight Rangers"],
        "keywords": ["Midnight Rangers", "Norfall Barrens", "Border", "Desorock", "Garrison"]
    },
    {
        "id": 26,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Tổ chức phản diện Fractsidus (Tàn Tinh Hội) có tôn chỉ gì về việc dung hợp Tacet Discord?",
        "expected_entities": ["Fractsidus"],
        "keywords": ["Fractsidus", "Tacet Discord", "Fusion", "Lament", "Order"]
    },
    {
        "id": 27,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Thánh Thú Jué là Sentinel của vùng đất nào và có quyền năng điều khiển thời gian ra sao?",
        "expected_entities": ["Jué"],
        "keywords": ["Jué", "Sentinel", "Temporal", "Time", "Mt. Firmament", "Dragon"]
    },
    {
        "id": 28,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Vùng núi Mt. Firmament (Thừa Tiêu Sơn) có dòng chảy thời gian bất thường thế nào?",
        "expected_entities": ["Mt. Firmament"],
        "keywords": ["Mt. Firmament", "Chronosorter", "Time", "Temporal", "Jué"]
    },
    {
        "id": 29,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Học viện Huaxu (Hoa Hư Viện) là trung tâm nghiên cứu khoa học công nghệ của ai?",
        "expected_entities": ["Huaxu"],
        "keywords": ["Huaxu", "Academy", "Research", "Jinzhou", "Xiangli Yao"]
    },
    {
        "id": 30,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Tổ chức Court of Savantae thời cổ đại đã tiến hành những thí nghiệm cấm gì?",
        "expected_entities": ["Court of Savantae"],
        "keywords": ["Court of Savantae", "Savantae", "Experiment", "Ancient", "Remnant"]
    },
    {
        "id": 31,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Tacet Discord là loài quái vật hình thành từ các trường tần số như thế nào?",
        "expected_entities": ["Tacet Discord"],
        "keywords": ["Tacet Discord", "Frequency", "Echo", "Wave", "Monster"]
    },
    {
        "id": 32,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Thorenodian (Dị Loại Thần Ma) có sức mạnh hủy diệt các nền văn minh ra sao?",
        "expected_entities": ["Threnodian"],
        "keywords": ["Threnodian", "Catastrophe", "Lament", "Destruction", "Lord"]
    },
    {
        "id": 33,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Tacet Mark là dấu ấn xuất hiện trên cơ thể Resonator biểu thị điều gì?",
        "expected_entities": ["Tacet Mark"],
        "keywords": ["Tacet Mark", "Resonator", "Overclock", "Body", "Resonance"]
    },
    {
        "id": 34,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Không gian Sonoro Sphere là dị giới tần số được tạo ra như thế nào?",
        "expected_entities": ["Sonoro Sphere"],
        "keywords": ["Sonoro Sphere", "Sub-dimension", "Domain", "Frequency", "Space"]
    },
    {
        "id": 35,
        "category": "World & Factions",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Mỏ Tiger's Maw Mine là nơi khai thác khoáng thạch Lampylumen và gặp biến cố gì?",
        "expected_entities": ["Tiger's Maw"],
        "keywords": ["Tiger's Maw", "Mine", "Lampylumen", "Industry", "Quarry"]
    },

    # ── GROUP 3: STORY, PLOT, QUESTS & RELATIONSHIPS (15 Questions) ──
    {
        "id": 36,
        "category": "Story & Quest",
        "collection": COLLECTION_STORY_LORE,
        "query": "Trận chiến tại Norfall Barrens trong quá khứ gắn liền với sự biến mất của ai?",
        "expected_entities": ["Norfall Barrens", "Geshu Lin"],
        "keywords": ["Norfall Barrens", "Geshu Lin", "Battle", "Midnight Rangers", "Retroact Rain"]
    },
    {
        "id": 37,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Geshu Lin từng là tướng quân tiền nhiệm của Midnight Rangers trước Jiyan như thế nào?",
        "expected_entities": ["Geshu Lin", "Jiyan"],
        "keywords": ["Geshu Lin", "General", "Midnight Rangers", "Overclock", "Norfall"]
    },
    {
        "id": 38,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Mối quan hệ thân thiết giữa Chixia và Yangyang khi đón tiếp Rover tại Jinzhou?",
        "expected_entities": ["Chixia", "Yangyang", "Rover"],
        "keywords": ["Chixia", "Yangyang", "Rover", "Jinzhou", "Outrider"]
    },
    {
        "id": 39,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Tại sao Changli quyết tâm phò tá và đào tạo Jinhsi trở thành Magistrate của Jinzhou?",
        "expected_entities": ["Changli", "Jinhsi"],
        "keywords": ["Changli", "Jinhsi", "Magistrate", "Mentor", "Jinzhou"]
    },
    {
        "id": 40,
        "category": "Story & Quest",
        "collection": COLLECTION_STORY_LORE,
        "query": "Hiệp ước giữa Quan trấn thủ Jinhsi và Thánh Thú Jué tại Mt. Firmament diễn ra thế nào?",
        "expected_entities": ["Jinhsi", "Jué"],
        "keywords": ["Jinhsi", "Jué", "Sentinel", "Pact", "Mt. Firmament", "Resonance"]
    },
    {
        "id": 41,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Shorekeeper đã hy sinh và duy trì hệ thống Tethys System vì Rover như thế nào?",
        "expected_entities": ["Shorekeeper", "Rover"],
        "keywords": ["Shorekeeper", "Rover", "Tethys", "Black Shores", "Stellarealm"]
    },
    {
        "id": 42,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Sự say mê và ám ảnh đặc biệt của Camellya dành cho Rover bắt nguồn từ đâu?",
        "expected_entities": ["Camellya", "Rover"],
        "keywords": ["Camellya", "Rover", "Black Shores", "Seed", "Bloom", "Destiny"]
    },
    {
        "id": 43,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Nhiệm vụ điều tra ngầm của Yinlin truy tìm kẻ buôn bán búp bê điều khiển rối?",
        "expected_entities": ["Yinlin"],
        "keywords": ["Yinlin", "Puppet", "Investigation", "Undercover", "Doll"]
    },
    {
        "id": 44,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Jiyan đã vượt qua gánh nặng tâm lý sau trận chiến Norfall Barrens để dẫn dắt quân đội ra sao?",
        "expected_entities": ["Jiyan"],
        "keywords": ["Jiyan", "Midnight Rangers", "Norfall Barrens", "Grief", "Responsibility"]
    },
    {
        "id": 45,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Rover thức tỉnh đầu game tại thung lũng Gorges of Spirits được ai tìm thấy đầu tiên?",
        "expected_entities": ["Rover", "Yangyang", "Chixia"],
        "keywords": ["Rover", "Yangyang", "Chixia", "Awakening", "Gorges of Spirits"]
    },
    {
        "id": 46,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Thân thế bí ẩn của Rover và ấn ký Tacet Mark trên bàn tay phải có khả năng hấp thụ Echo?",
        "expected_entities": ["Rover"],
        "keywords": ["Rover", "Tacet Mark", "Absorb", "Echo", "Hand", "Spectro"]
    },
    {
        "id": 47,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Phrolova là thành viên cấp cao của Fractsidus có năng lực âm nhạc điều khiển Tacet Discord ra sao?",
        "expected_entities": ["Phrolova", "Fractsidus"],
        "keywords": ["Phrolova", "Fractsidus", "Music", "Cello", "Tacet Discord"]
    },
    {
        "id": 48,
        "category": "Story & Quest",
        "collection": COLLECTION_WORLD_LORE,
        "query": "Thành phố đổ nát Port City of Guixu bị thiêu rụi bởi biển lửa gì trong quá khứ?",
        "expected_entities": ["Guixu"],
        "keywords": ["Guixu", "Port City", "Inferno", "Rider", "Sea of Flames", "Ruin"]
    },
    {
        "id": 49,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Quá khứ của Sanhua khi được Jinhsi giải cứu và trở thành cận vệ trung thành nhất?",
        "expected_entities": ["Sanhua", "Jinhsi"],
        "keywords": ["Sanhua", "Jinhsi", "Guard", "Loyalty", "Rescue", "Snow"]
    },
    {
        "id": 50,
        "category": "Story & Quest",
        "collection": COLLECTION_CHARACTER_LORE,
        "query": "Những phát minh cơ khí và cánh tay máy nhân tạo của Xiangli Yao giúp ích gì cho cư dân Jinzhou?",
        "expected_entities": ["Xiangli Yao"],
        "keywords": ["Xiangli Yao", "Prosthetic", "Arm", "Invention", "Huaxu", "Jinzhou"]
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# EVALUATION METRICS ENGINE
# ──────────────────────────────────────────────────────────────────────────────
def check_hit(retrieved_texts: List[str], expected_keywords: List[str]) -> Tuple[bool, int, List[str]]:
    """
    Checks if any retrieved chunk contains key reference keywords (case-insensitive).
    Returns (is_hit, hit_rank_1_indexed, matched_keywords).
    """
    matched_kws = set()
    for rank, text in enumerate(retrieved_texts, 1):
        text_lower = text.lower()
        chunk_matches = [kw for kw in expected_keywords if kw.lower() in text_lower]
        if chunk_matches:
            matched_kws.update(chunk_matches)
            return True, rank, list(matched_kws)
    return False, 0, []


async def run_single_eval(
    item: Dict[str, Any],
    embedder: FastEmbedAdapter,
    retriever: LoreRetriever,
    weights: Tuple[float, float, float],
    score_threshold: float,
) -> Dict[str, Any]:
    query = item["query"]
    target_col = item.get("collection", COLLECTION_CHARACTER_LORE)
    expected_kws = item.get("keywords", [])

    t0 = time.perf_counter()
    query_vector = await embedder.embed_text(query, prefix="query: ")

    # Query all 3 lore collections concurrently as in production pipeline
    search_tasks = [
        qdrant_service.search_lore(
            collection=col,
            query_vector=query_vector,
            limit=10,
            score_threshold=score_threshold,
        )
        for col in [COLLECTION_CHARACTER_LORE, COLLECTION_WORLD_LORE, COLLECTION_STORY_LORE]
    ]
    all_res = await asyncio.gather(*search_tasks)
    
    raw_results = []
    seen_ids = set()
    for col_res in all_res:
        for cand in col_res:
            c_id = cand.get("id") or cand.get("payload", {}).get("chunk_id")
            if c_id not in seen_ids:
                seen_ids.add(c_id)
                raw_results.append(cand)

    # Reranking with custom weights
    query_tokens = retriever.reranker.tokenize(query)
    scored = []
    w_vec, w_key, w_meta = weights

    for cand in raw_results:
        payload = cand.get("payload", {})
        child_text = payload.get("text_content", "")
        v_score = cand.get("score", 0.0)
        if child_text:
            k_score = retriever.reranker.calculate_score(query_tokens, child_text)
            canon = payload.get("canonical_name") or ""
            head = payload.get("heading_path") or ""
            meta_text = f"{canon} {head}".strip()
            m_score = retriever.reranker.calculate_score(query_tokens, meta_text) if meta_text else 0.0
            
            hybrid = (v_score * w_vec) + (k_score * w_key) + (m_score * w_meta)
            scored.append((child_text, hybrid, v_score, k_score, m_score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_5 = scored[:5]
    latency = time.perf_counter() - t0

    retrieved_texts = [x[0] for x in top_5]
    is_hit, hit_rank, matched = check_hit(retrieved_texts, expected_kws)

    return {
        "id": item["id"],
        "category": item["category"],
        "query": query,
        "latency_ms": round(latency * 1000, 2),
        "retrieved_count": len(top_5),
        "is_hit": is_hit,
        "hit_rank": hit_rank,
        "reciprocal_rank": (1.0 / hit_rank) if is_hit and hit_rank > 0 else 0.0,
        "matched_keywords": matched,
        "top_score": round(top_5[0][1], 4) if top_5 else 0.0,
        "vector_score": round(top_5[0][2], 4) if top_5 else 0.0,
    }


# ──────────────────────────────────────────────────────────────────────────────
# MAIN BENCHMARK RUNNER
# ──────────────────────────────────────────────────────────────────────────────
async def run_benchmark_and_tune():
    log_dir = Path("tests/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "benchmark_50_wiki_lore.log"

    print("=" * 80)
    print("🚀 BẮT ĐẦU BENCHMARK 50 CÂU HỎI LORE WIKI ĐA NGÔN NGỮ (VIETNAMESE -> ENGLISH)")
    print(f"📊 Tập dữ liệu kiểm thử: {len(BENCHMARK_50_QUESTIONS)} câu hỏi bao quát 3 nhóm:")
    print("   • Nhóm 1: Nhân vật, Resonators & Báo cáo Forte (20 câu)")
    print("   • Nhóm 2: Thế giới, Địa danh, Phe phái & Khái niệm Lore (15 câu)")
    print("   • Nhóm 3: Cốt truyện, Nhiệm vụ, Sự kiện & Mối quan hệ (15 câu)")
    print("=" * 80)

    embedder = FastEmbedAdapter()
    retriever = LoreRetriever(vector_store=qdrant_service)

    # 1. Run Baseline Evaluation with Current Settings (Weights: 0.60, 0.25, 0.15; Threshold: 0.35)
    default_weights = (RAGTuning.WEIGHT_VECTOR, RAGTuning.WEIGHT_KEYWORD, RAGTuning.WEIGHT_METADATA)
    default_thresh = RAGTuning.SCORE_THRESHOLD

    print(f"\n[*] Đang chạy đánh giá Baseline với thông số hiện tại:")
    print(f"    - Hybrid Weights: Vector={default_weights[0]}, Keyword={default_weights[1]}, Metadata={default_weights[2]}")
    print(f"    - Score Threshold: {default_thresh}")
    print(f"    - Top K: {RAGTuning.TOP_K}")

    results = []
    log_lines = []
    log_lines.append(f"BENCHMARK REPORT: 50 VIETNAMESE -> ENGLISH WIKI LORE QUERIES\n{'='*70}\n")

    for item in BENCHMARK_50_QUESTIONS:
        eval_res = await run_single_eval(
            item=item,
            embedder=embedder,
            retriever=retriever,
            weights=default_weights,
            score_threshold=default_thresh,
        )
        results.append(eval_res)

        status_icon = "✅" if eval_res["is_hit"] else "❌"
        rank_str = f"Rank #{eval_res['hit_rank']}" if eval_res["is_hit"] else "MISS"
        print(f"  [{eval_res['id']:02d}/50] {status_icon} {rank_str:8} | Score: {eval_res['top_score']:.3f} | {eval_res['latency_ms']:5.1f}ms | {eval_res['query'][:55]}...")

        log_lines.append(
            f"[{eval_res['id']:02d}] {status_icon} {rank_str} | TopScore: {eval_res['top_score']} (Vec: {eval_res['vector_score']}) | Latency: {eval_res['latency_ms']}ms\n"
            f"     Query: {eval_res['query']}\n"
            f"     Matched KWs: {eval_res['matched_keywords']}\n"
        )

    # Calculate Statistics
    total = len(results)
    hits_top1 = sum(1 for r in results if r["is_hit"] and r["hit_rank"] == 1)
    hits_top3 = sum(1 for r in results if r["is_hit"] and r["hit_rank"] <= 3)
    hits_top5 = sum(1 for r in results if r["is_hit"] and r["hit_rank"] <= 5)
    mrr = sum(r["reciprocal_rank"] for r in results) / total
    avg_latency = sum(r["latency_ms"] for r in results) / total

    print("\n" + "=" * 80)
    print("📈 KẾT QUẢ HIỆU NĂNG TRUY HỒI BASELINE (50 CÂU HỎI)")
    print("=" * 80)
    print(f"  🎯 Hit Rate @ 1 : {hits_top1:2d} / {total} ({hits_top1/total * 100:.1f}%)")
    print(f"  🎯 Hit Rate @ 3 : {hits_top3:2d} / {total} ({hits_top3/total * 100:.1f}%)")
    print(f"  🎯 Hit Rate @ 5 : {hits_top5:2d} / {total} ({hits_top5/total * 100:.1f}%)")
    print(f"  🏆 MRR (Mean Reciprocal Rank) : {mrr:.4f}")
    print(f"  ⏱️ Độ trễ trung bình           : {avg_latency:.2f} ms / query")
    print("=" * 80)

    # 2. Grid Search / Parameter Optimization across Candidate Configurations
    print("\n" + "=" * 80)
    print("🔬 BẮT ĐẦU GRID SEARCH TỐI ƯU HÓA THÔNG SỐ (HYBRID WEIGHTS & THRESHOLDS)")
    print("=" * 80)

    weight_candidates = [
        ("Current (60/25/15)", (0.60, 0.25, 0.15)),
        ("Vector Heavy (75/15/10)", (0.75, 0.15, 0.10)),
        ("Balanced Multilingual (70/20/10)", (0.70, 0.20, 0.10)),
        ("High Semantic (80/10/10)", (0.80, 0.10, 0.10)),
        ("Dense Dominated (85/10/05)", (0.85, 0.10, 0.05)),
    ]
    threshold_candidates = [0.25, 0.30, 0.35, 0.40]

    grid_results = []
    print(f"{'Config Name':<32} | {'Thresh':<6} | {'Hit@1':<7} | {'Hit@3':<7} | {'Hit@5':<7} | {'MRR':<7}")
    print("-" * 75)

    best_config = None
    best_score = -1.0

    for name, w in weight_candidates:
        for th in threshold_candidates:
            c_hits1 = 0
            c_hits3 = 0
            c_hits5 = 0
            c_mrr_sum = 0.0

            for item in BENCHMARK_50_QUESTIONS:
                eval_res = await run_single_eval(
                    item=item,
                    embedder=embedder,
                    retriever=retriever,
                    weights=w,
                    score_threshold=th,
                )
                if eval_res["is_hit"]:
                    if eval_res["hit_rank"] == 1:
                        c_hits1 += 1
                    if eval_res["hit_rank"] <= 3:
                        c_hits3 += 1
                    if eval_res["hit_rank"] <= 5:
                        c_hits5 += 1
                c_mrr_sum += eval_res["reciprocal_rank"]

            c_mrr = c_mrr_sum / total
            score_metric = (c_hits5 / total) * 0.5 + c_mrr * 0.5

            grid_results.append({
                "name": name,
                "weights": w,
                "threshold": th,
                "hit1": c_hits1 / total,
                "hit3": c_hits3 / total,
                "hit5": c_hits5 / total,
                "mrr": c_mrr,
                "composite_score": score_metric
            })

            print(f"{name:<32} | {th:<6.2f} | {c_hits1/total*100:5.1f}% | {c_hits3/total*100:5.1f}% | {c_hits5/total*100:5.1f}% | {c_mrr:6.4f}")

            if score_metric > best_score:
                best_score = score_metric
                best_config = (name, w, th, c_hits5/total, c_mrr)

    print("=" * 80)
    print(f"🌟 CẤU HÌNH TỐI ƯU NHẤT: {best_config[0]} (Ngưỡng Threshold: {best_config[2]})")
    print(f"   • Hit Rate @ 5: {best_config[3]*100:.1f}%")
    print(f"   • MRR Score   : {best_config[4]:.4f}")
    print("=" * 80)

    # Save log file
    summary_text = (
        f"\n\nFINAL BENCHMARK SUMMARY\n"
        f"Total Queries: {total}\n"
        f"Baseline Hit@1: {hits_top1/total*100:.1f}%\n"
        f"Baseline Hit@5: {hits_top5/total*100:.1f}%\n"
        f"Baseline MRR  : {mrr:.4f}\n"
        f"Optimal Config: {best_config[0]} with threshold {best_config[2]}\n"
        f"Optimal Hit@5 : {best_config[3]*100:.1f}%\n"
        f"Optimal MRR   : {best_config[4]:.4f}\n"
    )
    log_lines.append(summary_text)

    with open(log_file, "w", encoding="utf-8") as f:
        f.writelines(log_lines)
    print(f"📁 Báo cáo chi tiết đã được ghi vào: {log_file}")


if __name__ == "__main__":
    asyncio.run(run_benchmark_and_tune())
