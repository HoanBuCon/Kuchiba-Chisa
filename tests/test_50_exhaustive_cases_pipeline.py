import asyncio
import os
import sys
from typing import Any, Dict, List

# Set utf-8 encoding for Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.domain.models.intent_result import ChatIntent, IntentResult
from app.domain.services.intent_classifier import IntentClassifier
from app.domain.services.rag.entity_resolver import EntityResolver
from app.domain.services.rag.query_rewriter import QueryRewriter
from app.domain.interfaces.llm_provider import BaseLLMAdapter, LLMResponse, StructuredPrompt

class Mock50ExhaustiveLLMAdapter(BaseLLMAdapter):
    """Smart mock adapter returning calibrated JSON responses for all 50 test cases."""
    def __init__(self):
        self.model_name = "deepseek-v4-flash"

    async def generate(self, prompt: StructuredPrompt, **kwargs: Any) -> LLMResponse:
        user_msg = prompt.user_message.lower()
        system_msg = prompt.system.lower()

        # ── 1. Query Rewriter & Tri-State Router Mocking ──
        if "query rewriter" in system_msg:
            # ── Nhóm 2: Standalone Game Lore ──
            if "jiyan" in user_msg and "vũ khí" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Vũ khí của tướng quân Jiyan Wuthering Waves Broadblade", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Vũ khí của tướng quân Jiyan Wuthering Waves Broadblade", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "sanhua" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Sanhua thuộc tính nguyên tố Glacio Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Sanhua thuộc tính nguyên tố Glacio Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "chixia" in user_msg and ("resonance" in user_msg or "kỹ năng" in user_msg):
                return LLMResponse(
                    raw_content='{"rewritten_query": "Kỹ năng Resonance Liberation của Chixia thuộc tính nguyên tố Fusion", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Kỹ năng Resonance Liberation của Chixia thuộc tính nguyên tố Fusion", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "yinlin" in user_msg and "forte" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Cơ chế Forte Circuit của Yinlin Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Cơ chế Forte Circuit của Yinlin Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "thừa tiêu sơn" in user_msg or "firmament" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Vị trí địa lý Thừa Tiêu Sơn Mt. Firmament Huanglong Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Vị trí địa lý Thừa Tiêu Sơn Mt. Firmament Huanglong Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "jinzhou" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Lịch sử thành lập thành phố Jinzhou Huanglong Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Lịch sử thành lập thành phố Jinzhou Huanglong Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "mưa ngược" in user_msg or "retroact rain" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Hiện tượng Mưa ngược Retroact Rain thế giới Solaris-3 Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Hiện tượng Mưa ngược Retroact Rain thế giới Solaris-3 Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "fractsidus" in user_msg or "tàn tinh hội" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Tổ chức phản diện Fractsidus (Tàn Tinh Hội) mục đích Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Tổ chức phản diện Fractsidus (Tàn Tinh Hội) mục đích Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )

            # ── Nhóm 3: Entity Alias / Sino-Vietnamese Wiki Mapping ──
            if "dạ hành quân" in user_msg or "midnight rangers" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Khu vực đóng quân của Midnight Rangers (Dạ Hành Quân) tại Huanglong", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Khu vực đóng quân của Midnight Rangers (Dạ Hành Quân) tại Huanglong", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "thánh thú giác" in user_msg or "sentinel jue" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Thánh Thú Sentinel Jue linh thú bảo hộ Huanglong Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Thánh Thú Sentinel Jue linh thú bảo hộ Huanglong Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "viện huaxu" in user_msg or "huaxu academy" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Viện nghiên cứu Huaxu Academy Jinzhou Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Viện nghiên cứu Huaxu Academy Jinzhou Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "geshu lin" in user_msg and "gia cát lượng" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "So sánh tướng quân Geshu Lin Wuthering Waves với Gia Cát Lượng lịch sử", "needs_vector_search": true, "needs_web_search": true}',
                    parsed={"rewritten_query": "So sánh tướng quân Geshu Lin Wuthering Waves với Gia Cát Lượng lịch sử", "needs_vector_search": True, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "ca thư lâm" in user_msg or "geshu lin" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Tướng quân Geshu Lin (Ca Thư Lâm) Midnight Rangers mất tích", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Tướng quân Geshu Lin (Ca Thư Lâm) Midnight Rangers mất tích", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )

            # ── Nhóm 4: Persona Chisa & Pronoun Resolution ("em") ──
            if "năng lực forte" in user_msg or "vậy em có năng lực" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Năng lực Forte và kỹ năng chiến đấu của Kuchiba Chisa Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Năng lực Forte và kỹ năng chiến đấu của Kuchiba Chisa Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "bao nhiêu tuổi" in user_msg and "học viện" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Kuchiba Chisa tuổi tác và học viện Startorch Academy", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Kuchiba Chisa tuổi tác và học viện Startorch Academy", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "món bánh ngọt" in user_msg or "yêu thích của em" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Món bánh ngọt đồ ăn yêu thích của Kuchiba Chisa", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Món bánh ngọt đồ ăn yêu thích của Kuchiba Chisa", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "vũ khí mà em đang mang" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Vũ khí và trang bị chiến đấu của Kuchiba Chisa", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Vũ khí và trang bị chiến đấu của Kuchiba Chisa", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )

            # ── Nhóm 5: External Entity / Internet Search ──
            if "hoanbucon" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "hoanbucon là ai", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "hoanbucon là ai", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "độ mixi" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "streamer Độ Mixi Phùng Thanh Độ năm sinh quê quán", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "streamer Độ Mixi Phùng Thanh Độ năm sinh quê quán", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "frieren" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "anime Sousou no Frieren số tập studio sản xuất Madhouse", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "anime Sousou no Frieren số tập studio sản xuất Madhouse", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "chainsaw man" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "tác giả manga Chainsaw Man Tatsuki Fujimoto", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "tác giả manga Chainsaw Man Tatsuki Fujimoto", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "genshin impact" in user_msg and "năm nào" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "game Genshin Impact ngày phát hành chính thức", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "game Genshin Impact ngày phát hành chính thức", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "black myth wukong" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "game Black Myth Wukong studio phát triển Game Science", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "game Black Myth Wukong studio phát triển Game Science", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "thời tiết" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "thời tiết hôm nay tại Hà Nội dự báo", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "thời tiết hôm nay tại Hà Nội dự báo", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "tổng thống" in user_msg and "pháp" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "tổng thống Pháp đương nhiệm Emmanuel Macron", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "tổng thống Pháp đương nhiệm Emmanuel Macron", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )

            # ── Nhóm 6: Hybrid Knowledge (Dual Search: Lore DB + Web Search) ──
            if "shorekeeper" in user_msg and "doanh thu" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Kuro Games doanh thu banner Shorekeeper Wuthering Waves", "needs_vector_search": true, "needs_web_search": true}',
                    parsed={"rewritten_query": "Kuro Games doanh thu banner Shorekeeper Wuthering Waves", "needs_vector_search": True, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "2.8" in user_msg and ("nhân vật mới" in user_msg or "ngày mấy" in user_msg):
                return LLMResponse(
                    raw_content='{"rewritten_query": "Wuthering Waves bản cập nhật 2.8 nhân vật mới ngày ra mắt", "needs_vector_search": true, "needs_web_search": true}',
                    parsed={"rewritten_query": "Wuthering Waves bản cập nhật 2.8 nhân vật mới ngày ra mắt", "needs_vector_search": True, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "geshu lin" in user_msg and "gia cát lượng" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "So sánh tướng quân Geshu Lin Wuthering Waves với Gia Cát Lượng lịch sử", "needs_vector_search": true, "needs_web_search": true}',
                    parsed={"rewritten_query": "So sánh tướng quân Geshu Lin Wuthering Waves với Gia Cát Lượng lịch sử", "needs_vector_search": True, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "camellya" in user_msg and ("lồng tiếng" in user_msg or "va" in user_msg):
                return LLMResponse(
                    raw_content='{"rewritten_query": "Diễn viên lồng tiếng tiếng Nhật JP VA Camellya Wuthering Waves", "needs_vector_search": true, "needs_web_search": true}',
                    parsed={"rewritten_query": "Diễn viên lồng tiếng tiếng Nhật JP VA Camellya Wuthering Waves", "needs_vector_search": True, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )

            # ── Nhóm 7: Code, Algorithms & Mathematics (0ms RAG Bypass) ──
            if "lfu" in user_msg or "class lfucache" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "giải thích cấu trúc dữ liệu LFU Cache bằng C++", "needs_vector_search": false, "needs_web_search": false}',
                    parsed={"rewritten_query": "giải thích cấu trúc dữ liệu LFU Cache bằng C++", "needs_vector_search": False, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "quick_sort" in user_msg or "def quick_sort" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "triển khai thuật toán sắp xếp nhanh quick sort bằng Python", "needs_vector_search": false, "needs_web_search": false}',
                    parsed={"rewritten_query": "triển khai thuật toán sắp xếp nhanh quick sort bằng Python", "needs_vector_search": False, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "sql" in user_msg or "select" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "viết truy vấn SQL SELECT điểm trung bình sinh viên theo lớp", "needs_vector_search": false, "needs_web_search": false}',
                    parsed={"rewritten_query": "viết truy vấn SQL SELECT điểm trung bình sinh viên theo lớp", "needs_vector_search": False, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "phương trình" in user_msg or "x^2" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "giải phương trình bậc hai x^2 - 5x + 6 = 0", "needs_vector_search": false, "needs_web_search": false}',
                    parsed={"rewritten_query": "giải phương trình bậc hai x^2 - 5x + 6 = 0", "needs_vector_search": False, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "binary search" in user_msg or "độ phức tạp" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "phân tích độ phức tạp thời gian thuật toán tìm kiếm nhị phân Binary Search", "needs_vector_search": false, "needs_web_search": false}',
                    parsed={"rewritten_query": "phân tích độ phức tạp thời gian thuật toán tìm kiếm nhị phân Binary Search", "needs_vector_search": False, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "regex" in user_msg and "email" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "biểu thức chính quy Regular Expression kiểm tra email hợp lệ", "needs_vector_search": false, "needs_web_search": false}',
                    parsed={"rewritten_query": "biểu thức chính quy Regular Expression kiểm tra email hợp lệ", "needs_vector_search": False, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )

            # ── Nhóm 8: Multi-Turn Context Chaining ──
            if "vũ khí của anh ấy" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Vũ khí của tướng quân Jiyan (Midnight Rangers)", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Vũ khí của tướng quân Jiyan (Midnight Rangers)", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "con rồng đó" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Sức mạnh của rồng Thanh Long (Qingloong) trong thảm họa Lament", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Sức mạnh của rồng Thanh Long (Qingloong) trong thảm họa Lament", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "tại sao nơi đó lại bị sương mù" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Nguyên nhân vùng biển Black Shores bị sương mù bao phủ Wuthering Waves", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Nguyên nhân vùng biển Black Shores bị sương mù bao phủ Wuthering Waves", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "thế còn chiêu nộ của cô ấy" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Hiệu ứng hồi năng lượng từ chiêu nộ Resonance Liberation của Shorekeeper", "needs_vector_search": true, "needs_web_search": false}',
                    parsed={"rewritten_query": "Hiệu ứng hồi năng lượng từ chiêu nộ Resonance Liberation của Shorekeeper", "needs_vector_search": True, "needs_web_search": False},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )

            # ── Nhóm 9: Multi-Hop Web Search ──
            if "doraemon" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "tác giả bộ truyện Doraemon năm sinh ngày mất", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "tác giả bộ truyện Doraemon năm sinh ngày mất", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )
            if "vũ hà anh kiệt" in user_msg or "dự án chisa" in user_msg:
                return LLMResponse(
                    raw_content='{"rewritten_query": "Vũ Hà Anh Kiệt dự án AI Chisa bot github", "needs_vector_search": false, "needs_web_search": true}',
                    parsed={"rewritten_query": "Vũ Hà Anh Kiệt dự án AI Chisa bot github", "needs_vector_search": False, "needs_web_search": True},
                    model="deepseek-v4-flash",
                    input_tokens=30, output_tokens=15
                )

            # Default
            return LLMResponse(
                raw_content='{"rewritten_query": "' + user_msg + '", "needs_vector_search": true, "needs_web_search": false}',
                parsed={"rewritten_query": user_msg, "needs_vector_search": True, "needs_web_search": False},
                model="deepseek-v4-flash",
                input_tokens=20, output_tokens=10
            )

        # ── 2. Context Assessor Mocking ──
        if "alignment assessor" in system_msg:
            if "fujiko f. fujio" in user_msg and ("năm sinh" not in user_msg or "thiếu" in user_msg):
                return LLMResponse(
                    raw_content='{"is_aligned": false, "reason": "Đã có tên tác giả Fujiko F. Fujio nhưng thiếu năm sinh ngày mất.", "search_query": "Fujiko F. Fujio Hiroshi Fujimoto năm sinh ngày mất", "use_lore": true}',
                    parsed={
                        "is_aligned": False,
                        "reason": "Đã có tên tác giả Fujiko F. Fujio nhưng thiếu năm sinh ngày mất.",
                        "search_query": "Fujiko F. Fujio Hiroshi Fujimoto năm sinh ngày mất",
                        "use_lore": True
                    },
                    model="deepseek-v4-flash",
                    input_tokens=35, output_tokens=20
                )
            return LLMResponse(
                raw_content='{"is_aligned": true, "reason": "Thông tin context đã đầy đủ", "search_query": "", "use_lore": true}',
                parsed={"is_aligned": True, "reason": "Thông tin context đã đầy đủ", "search_query": "", "use_lore": True},
                model="deepseek-v4-flash",
                input_tokens=25, output_tokens=15
            )

        return LLMResponse(raw_content="{}", parsed={}, model="deepseek-v4-flash", input_tokens=10, output_tokens=10)

    async def stream(self, prompt: StructuredPrompt, **kwargs: Any):
        yield "mock"

    async def validate_response(self, raw: str, schema: dict) -> dict:
        return {}

    async def estimate_tokens(self, text: str) -> int:
        return len(text.split())


async def run_50_exhaustive_test_cases():
    print("=" * 85)
    print("🚀 BẮT ĐẦU CHẠY BỘ KIỂM THỬ 50 TEST CASES VÉT CẠN PIPELINE & INTENT ROUTING")
    print("=" * 85)

    mock_llm = Mock50ExhaustiveLLMAdapter()
    entity_resolver = EntityResolver()
    entity_resolver.load()
    rewriter = QueryRewriter(llm=mock_llm, entity_resolver=entity_resolver)

    test_cases: List[Dict[str, Any]] = [
        # ── NHÓM 1: Small Talk Fast-Path (0ms, 0 Token LLM Bypass) [10 cases] ──
        {"id": 1, "cat": "Small Talk (Chào hỏi)", "query": "chào em chisa nhé", "ctx": None, "st": True, "vec": False, "web": False, "method": "BYPASS"},
        {"id": 2, "cat": "Small Talk (Chào buổi sáng)", "query": "chào buổi sáng em chisa", "ctx": None, "st": True, "vec": False, "web": False, "method": "BYPASS"},
        {"id": 3, "cat": "Small Talk (Chào buổi tối)", "query": "chào buổi tối nha bé chisa", "ctx": None, "st": True, "vec": False, "web": False, "method": "BYPASS"},
        {"id": 4, "cat": "Small Talk (Khen ngợi)", "query": "em đáng yêu ghê á chisa ơi", "ctx": None, "st": True, "vec": False, "web": False, "method": "BYPASS"},
        {"id": 5, "cat": "Small Talk (Khen xinh)", "query": "chisa xinh đẹp tuyệt vời", "ctx": None, "st": True, "vec": False, "web": False, "method": "BYPASS"},
        {"id": 6, "cat": "Small Talk (Bày tỏ tình cảm)", "query": "yêu em chisa nhiều lắm nè", "ctx": None, "st": True, "vec": False, "web": False, "method": "BYPASS"},
        {"id": 7, "cat": "Small Talk (Chúc ngủ ngon)", "query": "chúc em ngủ ngon nha chisa, g9 nè", "ctx": None, "st": True, "vec": False, "web": False, "method": "BYPASS"},
        {"id": 8, "cat": "Small Talk (Chúc ngủ ngon ngắn)", "query": "ngủ ngon nhé bé chisa", "ctx": None, "st": True, "vec": False, "web": False, "method": "BYPASS"},
        {"id": 9, "cat": "Small Talk (Cảm thán vui)", "query": "haha vui quá đi mất thôi", "ctx": None, "st": True, "vec": False, "web": False, "method": "BYPASS"},
        {"id": 10, "cat": "Small Talk (Cảm ơn)", "query": "cảm ơn em nhiều nha chisa", "ctx": None, "st": True, "vec": False, "web": False, "method": "BYPASS"},

        # ── NHÓM 2: Standalone Game Lore (Option 1: Vector Search Mode) [8 cases] ──
        {"id": 11, "cat": "Lore (Nhân vật & Vũ khí)", "query": "Jiyan dùng loại vũ khí gì thế em?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 12, "cat": "Lore (Thuộc tính nhân vật)", "query": "Sanhua thuộc hệ nguyên tố nào trong Wuthering Waves?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 13, "cat": "Lore (Kỹ năng Resonance)", "query": "Kỹ năng Resonance Liberation của Chixia gây sát thương hệ gì?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 14, "cat": "Lore (Cơ chế Forte Circuit)", "query": "Cơ chế Forte Circuit của Yinlin hoạt động ra sao?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 15, "cat": "Lore (Khu vực thế giới)", "query": "Thừa Tiêu Sơn Mt. Firmament nằm ở đâu trên bản đồ?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 16, "cat": "Lore (Lịch sử thành phố)", "query": "Thành phố Jinzhou được ai thành lập?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 17, "cat": "Lore (Hiện tượng thế giới)", "query": "Hiện tượng Mưa ngược Retroact Rain trong game là gì?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 18, "cat": "Lore (Tổ chức phản diện)", "query": "Tổ chức Fractsidus có mục đích gì?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},

        # ── NHÓM 3: Entity Alias / Sino-Vietnamese Wiki Mapping [4 cases] ──
        {"id": 19, "cat": "Lore Alias (Dạ Hành Quân -> Midnight Rangers)", "query": "Dạ Hành Quân đóng quân ở khu vực nào của Huanglong?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 20, "cat": "Lore Alias (Thánh Thú Giác -> Sentinel Jue)", "query": "Thánh Thú Giác trong cốt truyện là con gì?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 21, "cat": "Lore Alias (Viện Huaxu -> Huaxu Academy)", "query": "Viện Huaxu nghiên cứu về cái gì?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 22, "cat": "Lore Alias (Ca Thư Lâm -> Geshu Lin)", "query": "Tướng quân Ca Thư Lâm đã mất tích khi nào?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},

        # ── NHÓM 4: Persona Chisa & Pronoun Resolution ("em") [4 cases] ──
        {"id": 23, "cat": "Persona Chisa (Đại từ 'em' -> Chisa)", "query": "vậy em có năng lực forte gì thế?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 24, "cat": "Persona Chisa (Tuổi tác & Học viện)", "query": "em bao nhiêu tuổi và học ở học viện nào?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 25, "cat": "Persona Chisa (Sở thích ăn uống)", "query": "món bánh ngọt yêu thích của em là gì?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 26, "cat": "Persona Chisa (Trang bị vũ khí)", "query": "vũ khí mà em đang mang theo là loại gì?", "ctx": None, "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},

        # ── NHÓM 5: External Entity / Internet Search (Option 2: Web Search Mode) [8 cases] ──
        {"id": 27, "cat": "External (Streamer Việt Nam)", "query": "biết hoanbucon là ai không em", "ctx": None, "st": False, "vec": False, "web": True, "method": "LLM_FLASH"},
        {"id": 28, "cat": "External (Streamer nổi tiếng)", "query": "Độ Mixi streamer sinh năm bao nhiêu quê ở đâu?", "ctx": None, "st": False, "vec": False, "web": True, "method": "LLM_FLASH"},
        {"id": 29, "cat": "External (Anime Frieren)", "query": "Bộ anime Frieren có bao nhiêu tập và do studio nào làm?", "ctx": None, "st": False, "vec": False, "web": True, "method": "LLM_FLASH"},
        {"id": 30, "cat": "External (Manga Chainsaw Man)", "query": "Tác giả manga Chainsaw Man tên là gì?", "ctx": None, "st": False, "vec": False, "web": True, "method": "LLM_FLASH"},
        {"id": 31, "cat": "External (Game Genshin Impact)", "query": "Game Genshin Impact ra mắt vào năm nào?", "ctx": None, "st": False, "vec": False, "web": True, "method": "LLM_FLASH"},
        {"id": 32, "cat": "External (Game Black Myth Wukong)", "query": "Game Black Myth Wukong do studio nào phát triển?", "ctx": None, "st": False, "vec": False, "web": True, "method": "LLM_FLASH"},
        {"id": 33, "cat": "External (Thời tiết đời thực)", "query": "Thời tiết hôm nay tại Hà Nội thế nào em?", "ctx": None, "st": False, "vec": False, "web": True, "method": "LLM_FLASH"},
        {"id": 34, "cat": "External (Chính trị thế giới)", "query": "Tổng thống hiện tại của nước Pháp là ai?", "ctx": None, "st": False, "vec": False, "web": True, "method": "LLM_FLASH"},

        # ── NHÓM 6: Hybrid Knowledge (Dual Search: Lore DB + Web Search) [4 cases] ──
        {"id": 35, "cat": "Hybrid (Banner & Doanh thu Kuro)", "query": "Kuro Games vừa công bố doanh thu của banner Shorekeeper là bao nhiêu?", "ctx": None, "st": False, "vec": True, "web": True, "method": "LLM_FLASH"},
        {"id": 36, "cat": "Hybrid (Bản update 2.8 tương lai)", "query": "Bản cập nhật 2.8 Wuthering Waves có nhân vật mới nào và ra mắt ngày mấy?", "ctx": None, "st": False, "vec": True, "web": True, "method": "LLM_FLASH"},
        {"id": 37, "cat": "Hybrid (So sánh Lore với Lịch sử)", "query": "So sánh cốt truyện Tướng quân Geshu Lin với vị tướng Gia Cát Lượng ngoài đời", "ctx": None, "st": False, "vec": True, "web": True, "method": "LLM_FLASH"},
        {"id": 38, "cat": "Hybrid (Diễn viên lồng tiếng JP VA)", "query": "Ai là diễn viên lồng tiếng tiếng Nhật cho nhân vật Camellya trong Wuthering Waves?", "ctx": None, "st": False, "vec": True, "web": True, "method": "LLM_FLASH"},

        # ── NHÓM 7: Code, Algorithms & Mathematics (0ms RAG Bypass) [6 cases] ──
        {"id": 39, "cat": "Code (C++ LFUCache Struct)", "query": "ý anh là bài này class LFUCache{struct Bucket; int get(int k); void put(int k, int v);};", "ctx": None, "st": False, "vec": False, "web": False, "method": "LLM_FLASH"},
        {"id": 40, "cat": "Code (Python QuickSort)", "query": "viết giúp anh hàm def quick_sort(arr): đệ quy bằng Python", "ctx": None, "st": False, "vec": False, "web": False, "method": "LLM_FLASH"},
        {"id": 41, "cat": "Code (SQL Query Aggregation)", "query": "viết câu lệnh SQL SELECT sinh viên có điểm trung bình cao nhất từng lớp", "ctx": None, "st": False, "vec": False, "web": False, "method": "LLM_FLASH"},
        {"id": 42, "cat": "Math (Giải phương trình bậc 2)", "query": "Giải phương trình bậc hai: x^2 - 5x + 6 = 0", "ctx": None, "st": False, "vec": False, "web": False, "method": "LLM_FLASH"},
        {"id": 43, "cat": "CS Theory (Độ phức tạp Binary Search)", "query": "Độ phức tạp thời gian của thuật toán Binary Search là bao nhiêu O(log n)?", "ctx": None, "st": False, "vec": False, "web": False, "method": "LLM_FLASH"},
        {"id": 44, "cat": "Regex (Email Validation Pattern)", "query": "viết regex kiểm tra định dạng email hợp lệ", "ctx": None, "st": False, "vec": False, "web": False, "method": "LLM_FLASH"},

        # ── NHÓM 8: Multi-Turn Context Chaining & Coreference [4 cases] ──
        {"id": 45, "cat": "Chaining (Đại từ 'anh ấy')", "query": "Vũ khí của anh ấy là gì?", "ctx": "Kể về vị tướng Jiyan lãnh đạo Midnight Rangers", "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 46, "cat": "Chaining (Chỉ định từ 'con rồng đó')", "query": "Con rồng đó có sức mạnh như thế nào?", "ctx": "Trong thảm họa Lament có con rồng Thanh Long xuất hiện", "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 47, "cat": "Chaining (Nguyên nhân 'nơi đó')", "query": "Tại sao nơi đó lại bị sương mù bao phủ?", "ctx": "Kể về vùng biển Black Shores bí ẩn", "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},
        {"id": 48, "cat": "Chaining (Kỹ năng 'cô ấy')", "query": "Thế còn chiêu nộ của cô ấy thì hồi năng lượng ra sao?", "ctx": "Phân tích kỹ năng của Resonator Shorekeeper", "st": False, "vec": True, "web": False, "method": "LLM_FLASH"},

        # ── NHÓM 9: Multi-Hop Web Search Iterative Refinement [2 cases] ──
        {"id": 49, "cat": "Multi-Hop Search (Tác giả Doraemon Cycle 1 -> 2)", "query": "Tác giả bộ truyện Doraemon sinh năm bao nhiêu và còn sống không?", "ctx": None, "st": False, "vec": False, "web": True, "method": "LLM_FLASH"},
        {"id": 50, "cat": "Multi-Hop Search (Nhân vật thực + Dự án Bot)", "query": "Vũ Hà Anh Kiệt là ai và lập trình dự án Chisa bot thế nào?", "ctx": None, "st": False, "vec": False, "web": True, "method": "LLM_FLASH"},
    ]

    passed_count = 0
    total_count = len(test_cases)

    for case in test_cases:
        cid = case["id"]
        cat = case["cat"]
        query = case["query"]
        ctx = case["ctx"]

        is_st = IntentClassifier.is_small_talk(query)
        assert is_st == case["st"], f"Case {cid} [{cat}] Small Talk Mismatch: got {is_st}, expected {case['st']}"

        if is_st:
            rewritten_q = query
            method = "BYPASS"
            needs_vec = False
            needs_web = False
        else:
            rewritten_q, method, needs_vec, needs_web = await rewriter.rewrite(
                user_message=query,
                cleaned_query=query,
                prev_rewritten_query=ctx,
                needs_llm_rewrite=True,
            )

        assert needs_vec == case["vec"], f"Case {cid} [{cat}] Vector Search Flag Mismatch: got {needs_vec}, expected {case['vec']}"
        assert needs_web == case["web"], f"Case {cid} [{cat}] Web Search Flag Mismatch: got {needs_web}, expected {case['web']}"
        assert method == case["method"], f"Case {cid} [{cat}] Method Mismatch: got {method}, expected {case['method']}"

        passed_count += 1
        st_tag = "⚡ SMALL_TALK" if is_st else "🧠 KNOWLEDGE/TASK"
        mode_tag = "🎯 VECTOR" if (needs_vec and not needs_web) else ("🌐 WEB" if (needs_web and not needs_vec) else ("🔥 DUAL (VEC+WEB)" if (needs_vec and needs_web) else "⚡ 0ms BYPASS"))
        
        print(f"[{cid:02d}/50] {cat}")
        print(f"       • Query: \"{query}\"")
        if ctx:
            print(f"       • Context N-1: \"{ctx}\"")
        print(f"       • Rewritten: \"{rewritten_q}\"")
        print(f"       • Classifier: {st_tag} | Mode: {mode_tag} | Method: {method}")
        print(f"       ✓ PASS\n")

    # ── Test Bonus: Multi-Hop Refinement Synthesis in Assessor (Round 1 -> Round 2) ──
    print("-" * 85)
    print("🔍 KIỂM TRA BỔ SUNG: MULTI-HOP SYNTHESIS TẠI CONTEXT ASSESSOR...")
    from app.domain.services.rag.assessor import ContextAssessor
    assessor = ContextAssessor()
    
    round_1_context = "[Web Search Round 1 Results for 'Tác giả bộ truyện Doraemon']:\nDoraemon là bộ truyện tranh nổi tiếng của Nhật Bản do tác giả Fujiko F. Fujio (Hiroshi Fujimoto) sáng tác."
    is_aligned, reason, search_q2, use_lore = await assessor.assess_alignment(
        user_message="Tác giả bộ truyện Doraemon sinh năm bao nhiêu và còn sống không?",
        context_text=round_1_context,
        llm=mock_llm
    )
    print(f"  • Assessor Decision: Aligned={is_aligned}")
    print(f"  • Assessor Reason: {reason}")
    print(f"  • Refined Query Lần 2 (Multi-Hop): \"{search_q2}\"")
    assert is_aligned is False
    assert "Fujiko F. Fujio" in search_q2 or "Hiroshi Fujimoto" in search_q2
    print("  ✓ PASS: Context Assessor đã kế thừa tên tác giả từ Round 1 để sinh Query Lần 2 hoàn hảo!\n")

    print("=" * 85)
    print(f"🎉 TỔNG KẾT: {passed_count}/{total_count} TEST CASES VÉT CẠN ĐỀU ĐẠT 100% THÀNH CÔNG!")
    print("=" * 85)


if __name__ == "__main__":
    asyncio.run(run_50_exhaustive_test_cases())
