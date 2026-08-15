"""
================================================================================
BENCHMARK 50 HARD & IMPLICIT MULTILINGUAL LORE RETRIEVAL
================================================================================
- 50 Hard, Indirect, and Implicit Questions in Vietnamese against English Wiki Lore.
- Challenges:
    1. Zero/Minimal explicit name-dropping (queries rely on character traits, weapons,
       appearance, backstory events, roles).
    2. Deep lore & hidden backstory facts (Forte diagnosis, past battles, overclock signs).
    3. Cross-entity & relational queries (mentors, rescuers, rivals, factions).
    4. Complex world mechanics & natural conversational phrasing.
- Evaluates: Hit@1, Hit@3, Hit@5, MRR, Latency, and Error Analysis.
- Logs full detailed report to `tests/logs/benchmark_hard_50_wiki_lore.log`.
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

from app.infrastructure.vector.qdrant.qdrant_service import (
    qdrant_service,
    COLLECTION_CHARACTER_LORE,
    COLLECTION_WORLD_LORE,
    COLLECTION_STORY_LORE,
)
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.domain.tuning.rag import RAGTuning


# ──────────────────────────────────────────────────────────────────────────────
# 50 HARD & IMPLICIT QUESTIONS (NO EASY NAME-DROPPING / HIGHLY INDIRECT)
# ──────────────────────────────────────────────────────────────────────────────
HARD_50_QUESTIONS: List[Dict[str, Any]] = [
    # ── CATEGORY 1: IMPLICIT CHARACTER DESCRIPTIONS (15 Questions) ──
    {
        "id": 1,
        "category": "Implicit Description",
        "query": "Cô nàng cảnh vệ tóc đỏ hay cầm hai khẩu súng lục nhiệt tình đi tuần tra ở thành phố biên giới là ai?",
        "keywords": ["Chixia", "Gallant Blaze", "Patroller", "Outrider", "Pistols"],
        "target_entity": "Chixia"
    },
    {
        "id": 2,
        "category": "Implicit Description",
        "query": "Vị tướng quân từng làm bác sĩ quân y trước khi cầm đại đao triệu hồi rồng xanh chỉ huy tiền tuyến là ai?",
        "keywords": ["Jiyan", "Midnight Rangers", "Qingloong", "Doctor", "Medic"],
        "target_entity": "Jiyan"
    },
    {
        "id": 3,
        "category": "Implicit Description",
        "query": "Nữ kiếm sĩ cận vệ bị mất thị lực thông thường nhưng có thể nhìn thấy thế giới dưới dạng tần số sóng tuyết là ai?",
        "keywords": ["Sanhua", "Vision", "Frequency", "Glacio", "Snow"],
        "target_entity": "Sanhua"
    },
    {
        "id": 4,
        "category": "Implicit Description",
        "query": "Nữ điều tra viên ngầm sử dụng búp bê cơ khí điều khiển bằng dây sét điện màu tím để truy bắt tội phạm là ai?",
        "keywords": ["Yinlin", "Zapstring", "Puppet", "Patroller", "Electro"],
        "target_entity": "Yinlin"
    },
    {
        "id": 5,
        "category": "Implicit Description",
        "query": "Cô gái mặc sườn xám đỏ tay cầm quạt lông vũ chuyên chơi cờ vây và là quân sư của vị lãnh đạo trẻ là ai?",
        "keywords": ["Changli", "Counselor", "Jinhsi", "Go", "Feather"],
        "target_entity": "Changli"
    },
    {
        "id": 6,
        "category": "Implicit Description",
        "query": "Người bảo hộ bí ẩn sống trong không gian số ngập tràn hoa dạ quang của quần đảo biệt lập là ai?",
        "keywords": ["Shorekeeper", "Black Shores", "Tethys", "Stellarealm"],
        "target_entity": "Shorekeeper"
    },
    {
        "id": 7,
        "category": "Implicit Description",
        "query": "Cô nàng mang dây leo gai hoa nở rộ luôn điên cuồng bám đuổi và muốn nhìn thấy sự phát triển của nhân vật chính là ai?",
        "keywords": ["Camellya", "Black Shores", "Bloom", "Vine", "Seed"],
        "target_entity": "Camellya"
    },
    {
        "id": 8,
        "category": "Implicit Description",
        "query": "Cô bé ngồi trên quả bóng cừu bông trắng hồng luôn tìm kiếm những câu chuyện vui vẻ khắp thế giới là ai?",
        "keywords": ["Encore", "Cosmos", "Cloudy", "Wooly"],
        "target_entity": "Encore"
    },
    {
        "id": 9,
        "category": "Implicit Description",
        "query": "Nhà khoa học nghiên cứu vũ khí tính tình nóng nảy sẽ bùng phát ngọn lửa rồng rực cháy khi tức giận là ai?",
        "keywords": ["Mortefi", "Huaxu", "Dragon", "Fusion", "Anger"],
        "target_entity": "Mortefi"
    },
    {
        "id": 10,
        "category": "Implicit Description",
        "query": "Nữ họa sĩ tài năng nhút nhát dùng cây cọ ma thuật vẽ ra các nét mực băng giá để kiếm sống là ai?",
        "keywords": ["Zhezhi", "Painter", "Brush", "Ink", "Glacio"],
        "target_entity": "Zhezhi"
    },
    {
        "id": 11,
        "category": "Implicit Description",
        "query": "Thiên tài chế tạo máy móc trẻ tuổi sở hữu cánh tay nhân tạo đoạt giải quán quân công nghệ tại hội chợ là ai?",
        "keywords": ["Xiangli Yao", "Huaxu", "Principal", "Arm", "Gauntlet"],
        "target_entity": "Xiangli Yao"
    },
    {
        "id": 12,
        "category": "Implicit Description",
        "query": "Nữ giáo sư nghiêm nghị có sinh vật Remnant hình dạng lơ lửng bay bên cạnh làm nhiệm vụ hồi phục trị liệu là ai?",
        "keywords": ["Baizhi", "You'tan", "Huaxu", "Remnant"],
        "target_entity": "Baizhi"
    },
    {
        "id": 13,
        "category": "Implicit Description",
        "query": "Chàng trai mang dòng máu linh thú múa lân có tính cách ngây thơ hiếu động chiến đấu bằng bao tay quyền cước là ai?",
        "keywords": ["Lingyang", "Liondance", "Suan'ni", "Gauntlet"],
        "target_entity": "Lingyang"
    },
    {
        "id": 14,
        "category": "Implicit Description",
        "query": "Tiểu thư quý tộc vùng Rinascita sử dụng hai khẩu súng ngắn phong cách rối nước và mang vẻ đẹp kiêu sa là ai?",
        "keywords": ["Carlotta", "Montelli", "Rinascita", "Pistols"],
        "target_entity": "Carlotta"
    },
    {
        "id": 15,
        "category": "Implicit Description",
        "query": "Cô gái mang thanh kiếm đỏ thẫm sẵn sàng dùng chính sinh mệnh và máu của mình để trừng trị tội ác là ai?",
        "keywords": ["Danjin", "Crimson", "Havoc", "Blood", "Sword"],
        "target_entity": "Danjin"
    },

    # ── CATEGORY 2: DEEP LORE & FORTE DIAGNOSTICS (12 Questions) ──
    {
        "id": 16,
        "category": "Deep Lore & Diagnostics",
        "query": "Vết dấu ấn Tacet Mark trên cơ thể người biến dị sẽ có biến đổi bất thường gì khi rơi vào trạng thái bạo tẩu Overclock?",
        "keywords": ["Overclock", "Tacet Mark", "Stability", "Frequency", "Resonator"],
        "target_entity": "Tacet Mark"
    },
    {
        "id": 17,
        "category": "Deep Lore & Diagnostics",
        "query": "Hiện tượng gì xảy ra khi các luồng sóng ký ức từ Etheric Sea ngưng tụ lại làm các sự kiện quá khứ phát lại thành ảo ảnh?",
        "keywords": ["Retroact Rain", "Remnant", "Etheric Sea", "Illusion", "Phantom"],
        "target_entity": "Retroact Rain"
    },
    {
        "id": 18,
        "category": "Deep Lore & Diagnostics",
        "query": "Cấu trúc không gian dị giới hình thành từ sự chồng lấn trường tần số đặc biệt mà Resonator có thể bước vào chiến đấu gọi là gì?",
        "keywords": ["Sonoro Sphere", "Sub-dimension", "Frequency", "Space"],
        "target_entity": "Sonoro Sphere"
    },
    {
        "id": 19,
        "category": "Deep Lore & Diagnostics",
        "query": "Thảm họa diệt vong đầu tiên xóa sổ nền văn minh nhân loại cổ đại và sinh ra hiện tượng Tacet Discord trên Solaris-3 gọi là gì?",
        "keywords": ["The Lament", "Lament", "Cataclysm", "Solaris-3", "Tacet Discord"],
        "target_entity": "The Lament"
    },
    {
        "id": 20,
        "category": "Deep Lore & Diagnostics",
        "query": "Thực thể hủy diệt cấp cao nhất xuất hiện từ các đợt bùng phát thảm họa mang sức mạnh san phẳng cả một quốc gia được gọi là gì?",
        "keywords": ["Threnodian", "Catastrophe", "Lord", "Destruction"],
        "target_entity": "Threnodian"
    },
    {
        "id": 21,
        "category": "Deep Lore & Diagnostics",
        "query": "Thiết bị Chronosorter trên hòn đảo cô lập có cơ chế can thiệp và điều chỉnh dòng chảy thời gian ra sao?",
        "keywords": ["Chronosorter", "Mt. Firmament", "Time", "Temporal", "Jué"],
        "target_entity": "Mt. Firmament"
    },
    {
        "id": 22,
        "category": "Deep Lore & Diagnostics",
        "query": "Loại khoáng sản phát sáng màu xanh băng giá dưới đáy khu mỏ công nghiệp Jinzhou bị quái vật xâm chiếm có tên là gì?",
        "keywords": ["Lampylumen", "Tiger's Maw", "Mine", "Ore"],
        "target_entity": "Tiger's Maw"
    },
    {
        "id": 23,
        "category": "Deep Lore & Diagnostics",
        "query": "Biển lửa không thể dập tắt từng thiêu rụi cả một thành phố cảng phồn hoa trong quá khứ bắt nguồn từ đâu?",
        "keywords": ["Sea of Flames", "Guixu", "Port City", "Inferno", "Fire"],
        "target_entity": "Port City of Guixu"
    },
    {
        "id": 24,
        "category": "Deep Lore & Diagnostics",
        "query": "Thí nghiệm hợp nhất tần số quái vật và cơ thể người của tổ chức tôn thờ bóng tối cổ xưa đã để lại di tích gì?",
        "keywords": ["Court of Savantae", "Savantae", "Experiment", "Ruins"],
        "target_entity": "Court of Savantae"
    },
    {
        "id": 25,
        "category": "Deep Lore & Diagnostics",
        "query": "Tổ chức cuồng tín chủ trương đẩy nhanh thảm họa để thúc đẩy sự tiến hóa bắt buộc của nhân loại có tên là gì?",
        "keywords": ["Fractsidus", "Evolution", "Order", "Lament", "Tacet Discord"],
        "target_entity": "Fractsidus"
    },
    {
        "id": 26,
        "category": "Deep Lore & Diagnostics",
        "query": "Bản chất của tàn dư Echo mà các chiến binh thu thập sau khi đánh bại quái vật là gì?",
        "keywords": ["Echo", "Remnant", "Frequency", "Absorption", "Tacet Discord"],
        "target_entity": "Echo"
    },
    {
        "id": 27,
        "category": "Deep Lore & Diagnostics",
        "query": "Hệ thống siêu máy tính lượng tử điều phối và lưu trữ ký ức của tổ chức Hắc Ngạn có tên gọi là gì?",
        "keywords": ["Tethys", "Black Shores", "System", "Shorekeeper", "Stellarealm"],
        "target_entity": "Black Shores"
    },

    # ── CATEGORY 3: RELATIONSHIPS & HISTORICAL BACKSTORY (13 Questions) ──
    {
        "id": 28,
        "category": "Relationships & Backstory",
        "query": "Vị tướng tiền nhiệm của Dạ Hành Quân đã biến mất trong làn mưa ảo ảnh sau khi hạ lệnh phản công sinh tử ở chiến trường nào?",
        "keywords": ["Geshu Lin", "Norfall Barrens", "Midnight Rangers", "Retroact Rain", "General"],
        "target_entity": "Geshu Lin"
    },
    {
        "id": 29,
        "category": "Relationships & Backstory",
        "query": "Mối nhân duyên thời thơ ấu khi người phụ nữ quạt lông vũ cứu mạng và chỉ dạy cách cai trị cho cô gái đứng đầu thành phố là gì?",
        "keywords": ["Changli", "Jinhsi", "Magistrate", "Mentor", "Jinzhou"],
        "target_entity": "Changli"
    },
    {
        "id": 30,
        "category": "Relationships & Backstory",
        "query": "Biến cố trong bão tuyết khiến cô gái kiếm sĩ mù được quan trấn thủ cứu thoát và thề sẽ bảo vệ bằng tính mạng diễn ra thế nào?",
        "keywords": ["Sanhua", "Jinhsi", "Snow", "Rescue", "Loyalty", "Guard"],
        "target_entity": "Sanhua"
    },
    {
        "id": 31,
        "category": "Relationships & Backstory",
        "query": "Thỏa thuận sinh mệnh giữa quan trấn thủ và vị Thần Thú điều khiển thời gian trên núi Thừa Tiêu Sơn có ý nghĩa gì?",
        "keywords": ["Jinhsi", "Jué", "Sentinel", "Pact", "Temporal", "Resonance"],
        "target_entity": "Jinhsi"
    },
    {
        "id": 32,
        "category": "Relationships & Backstory",
        "query": "Ký ức đầu tiên khi nhân vật chính thức tỉnh giữa thung lũng đá và được hai cô gái tuần tra phát hiện diễn ra ở đâu?",
        "keywords": ["Rover", "Gorges of Spirits", "Yangyang", "Chixia", "Awakening"],
        "target_entity": "Gorges of Spirits"
    },
    {
        "id": 33,
        "category": "Relationships & Backstory",
        "query": "Tại sao cô nàng hoa dây leo lại gọi nhân vật chính là hạt giống định mệnh và theo đuổi một cách cuồng nhiệt?",
        "keywords": ["Camellya", "Rover", "Seed", "Black Shores", "Bloom", "Fate"],
        "target_entity": "Camellya"
    },
    {
        "id": 34,
        "category": "Relationships & Backstory",
        "query": "Sự hy sinh của người bảo hộ Hắc Ngạn khi cố gắng duy trì lõi hệ thống dữ liệu để chờ đợi sự trở lại của người sáng lập?",
        "keywords": ["Shorekeeper", "Rover", "Tethys", "Black Shores", "Stellarealm"],
        "target_entity": "Shorekeeper"
    },
    {
        "id": 35,
        "category": "Relationships & Backstory",
        "query": "Cái chết của người thân trong lực lượng an ninh đã thúc đẩy cô gái múa rối dấn thân vào con đường điều tra đơn độc như thế nào?",
        "keywords": ["Yinlin", "Patroller", "Investigation", "Grandfather", "Puppet"],
        "target_entity": "Yinlin"
    },
    {
        "id": 36,
        "category": "Relationships & Backstory",
        "query": "Gánh nặng tâm lý và sự dằn vặt của vị bác sĩ trẻ sau khi phải chứng kiến hàng ngàn đồng đội ngã xuống ở trận địa biên giới?",
        "keywords": ["Jiyan", "Norfall Barrens", "Grief", "Midnight Rangers", "Comrades"],
        "target_entity": "Jiyan"
    },
    {
        "id": 37,
        "category": "Relationships & Backstory",
        "query": "Nguồn gốc xuất thân của sinh vật You'tan gắn liền với tuổi thơ và công trình nghiên cứu sinh thái học của vị nữ viện phó?",
        "keywords": ["Baizhi", "You'tan", "Huaxu", "Remnant", "Research"],
        "target_entity": "Baizhi"
    },
    {
        "id": 38,
        "category": "Relationships & Backstory",
        "query": "Tình bạn thắm thiết giữa cô nàng cảnh vệ nhiệt huyết và cô gái Outrider dịu dàng mang lông vũ diễn ra như thế nào?",
        "keywords": ["Chixia", "Yangyang", "Outrider", "Jinzhou", "Friends"],
        "target_entity": "Yangyang"
    },
    {
        "id": 39,
        "category": "Relationships & Backstory",
        "query": "Nữ chỉ huy áo giáp phòng ngự của Bộ Phát Triển Jinzhou đã bảo vệ các công trình kiến trúc vượt qua các đợt quái vật ra sao?",
        "keywords": ["Taoqi", "Ministry of Development", "Shield", "Defense", "Havoc"],
        "target_entity": "Taoqi"
    },
    {
        "id": 40,
        "category": "Relationships & Backstory",
        "query": "Người phụ nữ chơi đàn cello trong hàng ngũ kẻ thù có quá khứ liên quan đến âm nhạc và tần số quái vật như thế nào?",
        "keywords": ["Phrolova", "Cello", "Music", "Fractsidus", "Tacet Discord"],
        "target_entity": "Phrolova"
    },

    # ── CATEGORY 4: NATURAL CONVERSATIONAL & WORLD LOGIC (10 Questions) ──
    {
        "id": 41,
        "category": "Natural Dialogue & World Logic",
        "query": "Tại sao người lữ khách đặc biệt lại có thể hấp thụ trực tiếp lõi năng lượng của quái vật vào lòng bàn tay mà không bị nhiễm độc?",
        "keywords": ["Rover", "Tacet Mark", "Absorb", "Echo", "Hand", "Spectro"],
        "target_entity": "Rover"
    },
    {
        "id": 42,
        "category": "Natural Dialogue & World Logic",
        "query": "Vùng đồng bằng rộng lớn ở trung tâm lục địa Huanglong nơi đặt căn cứ phòng thủ chính chống lại quái vật là đâu?",
        "keywords": ["Central Plains", "Huanglong", "Plains", "Defense", "Jinzhou"],
        "target_entity": "Central Plains"
    },
    {
        "id": 43,
        "category": "Natural Dialogue & World Logic",
        "query": "Khu rừng rậm u ám chứa đầy bào tử và tiếng than khóc của loài chim cổ đại trong lãnh thổ Huanglong là khu vực nào?",
        "keywords": ["Dim Forest", "Whining Aix", "Mire", "Forest", "Huanglong"],
        "target_entity": "Dim Forest"
    },
    {
        "id": 44,
        "category": "Natural Dialogue & World Logic",
        "query": "Nguyên lý vận hành của năng lực phân tích cấu trúc vật chất thông qua các sợi dây cảm nhận vô hình của một Mutant Resonator?",
        "keywords": ["Thread Perception", "Structure", "Havoc", "Resonator", "Analysis"],
        "target_entity": "Kuchiba Chisa"
    },
    {
        "id": 45,
        "category": "Natural Dialogue & World Logic",
        "query": "Mục tiêu đào tạo và tôn chỉ nghiên cứu của học viện Star Torch Academy đối với các Resonator trẻ tuổi?",
        "keywords": ["Startorch Academy", "Academy", "Students", "Resonator", "Research"],
        "target_entity": "Startorch Academy"
    },
    {
        "id": 46,
        "category": "Natural Dialogue & World Logic",
        "query": "Tại sao các cư dân ở thế giới này lại gọi các đợt sóng âm kỳ lạ sau thảm họa là hiện tượng Waveworn?",
        "keywords": ["Waveworn", "Phenomenon", "Lament", "Tacet Discord", "Frequency"],
        "target_entity": "Waveworn Phenomenon"
    },
    {
        "id": 47,
        "category": "Natural Dialogue & World Logic",
        "query": "Người bảo vệ đứng đầu liên minh tiên phong luôn chăm sóc những mầm cây thực vật quý hiếm nở hoa giữa hoang mạc là ai?",
        "keywords": ["Verina", "Pioneer Association", "Plant", "Photosynthesis"],
        "target_entity": "Verina"
    },
    {
        "id": 48,
        "category": "Natural Dialogue & World Logic",
        "query": "Chàng trai chủ tiệm trà quyền thuật luôn giữ bình tĩnh và hướng dẫn các võ sinh rèn luyện thể chất tại Jinzhou là ai?",
        "keywords": ["Yuanwu", "Boxing", "Gauntlet", "Electro", "Tea"],
        "target_entity": "Yuanwu"
    },
    {
        "id": 49,
        "category": "Natural Dialogue & World Logic",
        "query": "Người đàn ông bí ẩn mang năng lực sương mù chuyên nhận các hợp đồng thông tin đắt giá tại tổ chức Hắc Ngạn là ai?",
        "keywords": ["Aalto", "Mist", "Information", "Black Shores", "Aero"],
        "target_entity": "Aalto"
    },
    {
        "id": 50,
        "category": "Natural Dialogue & World Logic",
        "query": "Đội quân đánh thuê Ghost Hounds thiện chiến trên chiến trường do thủ lĩnh mang năng lực sấm sét nào lãnh đạo?",
        "keywords": ["Calcharo", "Ghost Hounds", "Mercenary", "Electro", "Broadblade"],
        "target_entity": "Calcharo"
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# EVALUATION METRICS ENGINE
# ──────────────────────────────────────────────────────────────────────────────
def check_hit(retrieved_texts: List[str], expected_keywords: List[str]) -> Tuple[bool, int, List[str]]:
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
    expected_kws = item.get("keywords", [])

    t0 = time.perf_counter()
    query_vector = await embedder.embed_text(query, prefix="query: ")

    # Concurrently search all 3 lore collections
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
        "target_entity": item.get("target_entity", ""),
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
async def run_hard_benchmark():
    log_dir = Path("tests/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "benchmark_hard_50_wiki_lore.log"

    print("=" * 80)
    print("🔥 BẮT ĐẦU BENCHMARK 50 CÂU HỎI KHÓ & ẨN Ý (HARD & IMPLICIT LORE RETRIEVAL)")
    print(f"📊 Tập dữ liệu kiểm thử gồm 50 câu hỏi khó, không lộ tên riêng trực tiếp:")
    print("   • Phân nhóm 1: Mô tả gián tiếp nhân vật qua ngoại hình/vũ khí/tính cách (15 câu)")
    print("   • Phân nhóm 2: Khái niệm Lore sâu, chẩn đoán Overclock & cơ chế thế giới (12 câu)")
    print("   • Phân nhóm 3: Mối quan hệ, tiền kiếp & sự kiện lịch sử ẩn (13 câu)")
    print("   • Phân nhóm 4: Hội thoại tự nhiên & logic thế giới (10 câu)")
    print("=" * 80)

    embedder = FastEmbedAdapter()
    retriever = LoreRetriever(vector_store=qdrant_service)

    # Production weights from RAGTuning (0.80, 0.10, 0.10)
    weights = (RAGTuning.WEIGHT_VECTOR, RAGTuning.WEIGHT_KEYWORD, RAGTuning.WEIGHT_METADATA)
    threshold = RAGTuning.SCORE_THRESHOLD

    print(f"\n[*] Đang chạy đánh giá với thông số Production RAGTuning:")
    print(f"    - Hybrid Weights: Vector={weights[0]}, Keyword={weights[1]}, Metadata={weights[2]}")
    print(f"    - Score Threshold: {threshold}")
    print(f"    - Top K: {RAGTuning.TOP_K}")

    results = []
    log_lines = []
    log_lines.append(f"HARD BENCHMARK REPORT: 50 IMPLICIT VIETNAMESE -> ENGLISH WIKI LORE QUERIES\n{'='*75}\n")

    for item in HARD_50_QUESTIONS:
        eval_res = await run_single_eval(
            item=item,
            embedder=embedder,
            retriever=retriever,
            weights=weights,
            score_threshold=threshold,
        )
        results.append(eval_res)

        status_icon = "✅" if eval_res["is_hit"] else "❌"
        rank_str = f"Rank #{eval_res['hit_rank']}" if eval_res["is_hit"] else "MISS"
        print(f"  [{eval_res['id']:02d}/50] {status_icon} {rank_str:8} | Score: {eval_res['top_score']:.3f} (Vec: {eval_res['vector_score']:.3f}) | {eval_res['latency_ms']:5.1f}ms | Target: {eval_res['target_entity']:15} | {eval_res['query'][:40]}...")

        log_lines.append(
            f"[{eval_res['id']:02d}] {status_icon} {rank_str} | Target: {eval_res['target_entity']} | Score: {eval_res['top_score']} (Vec: {eval_res['vector_score']}) | Latency: {eval_res['latency_ms']}ms\n"
            f"     Query: {eval_res['query']}\n"
            f"     Category: {eval_res['category']}\n"
            f"     Matched KWs: {eval_res['matched_keywords']}\n\n"
        )

    # Statistical Breakdown
    total = len(results)
    hits_top1 = sum(1 for r in results if r["is_hit"] and r["hit_rank"] == 1)
    hits_top3 = sum(1 for r in results if r["is_hit"] and r["hit_rank"] <= 3)
    hits_top5 = sum(1 for r in results if r["is_hit"] and r["hit_rank"] <= 5)
    mrr = sum(r["reciprocal_rank"] for r in results) / total
    avg_latency = sum(r["latency_ms"] for r in results) / total

    print("\n" + "=" * 80)
    print("📈 KẾT QUẢ HIỆU NĂNG TỔNG QUAN (50 CÂU HỎI KHÓ & ẨN Ý)")
    print("=" * 80)
    print(f"  🎯 Hit Rate @ 1 : {hits_top1:2d} / {total} ({hits_top1/total * 100:.1f}%)")
    print(f"  🎯 Hit Rate @ 3 : {hits_top3:2d} / {total} ({hits_top3/total * 100:.1f}%)")
    print(f"  🎯 Hit Rate @ 5 : {hits_top5:2d} / {total} ({hits_top5/total * 100:.1f}%)")
    print(f"  🏆 MRR (Mean Reciprocal Rank) : {mrr:.4f}")
    print(f"  ⏱️ Độ trễ trung bình           : {avg_latency:.2f} ms / query")
    print("=" * 80)

    # Category Breakdown
    print("\n📊 ĐÁNH GIÁ THEO TỪNG PHÂN NHÓM:")
    categories = sorted(list(set(r["category"] for r in results)))
    for cat in categories:
        cat_items = [r for r in results if r["category"] == cat]
        cat_total = len(cat_items)
        cat_hit1 = sum(1 for r in cat_items if r["is_hit"] and r["hit_rank"] == 1)
        cat_hit5 = sum(1 for r in cat_items if r["is_hit"] and r["hit_rank"] <= 5)
        cat_mrr = sum(r["reciprocal_rank"] for r in cat_items) / cat_total
        print(f"  • {cat:<32}: Hit@1: {cat_hit1/cat_total*100:5.1f}% | Hit@5: {cat_hit5/cat_total*100:5.1f}% | MRR: {cat_mrr:.4f} ({cat_total} câu)")

    summary_text = (
        f"\nFINAL HARD BENCHMARK SUMMARY\n"
        f"Total Queries: {total}\n"
        f"Hit@1: {hits_top1/total*100:.1f}%\n"
        f"Hit@3: {hits_top3/total*100:.1f}%\n"
        f"Hit@5: {hits_top5/total*100:.1f}%\n"
        f"MRR  : {mrr:.4f}\n"
        f"Avg Latency: {avg_latency:.2f}ms\n"
    )
    log_lines.append(summary_text)

    with open(log_file, "w", encoding="utf-8") as f:
        f.writelines(log_lines)
    print(f"\n📁 Báo cáo chi tiết đã được ghi vào: {log_file}")


if __name__ == "__main__":
    asyncio.run(run_hard_benchmark())
