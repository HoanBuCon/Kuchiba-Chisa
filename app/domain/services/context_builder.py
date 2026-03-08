"""
ContextBuilder — Domain Service
Assembles the structured prompt context sent to the LLM.

Extracts all prompt-building logic from ChatEngine into a dedicated, 
testable, single-responsibility component.

Prompt structure (per design doc):
    SYSTEM   — character persona + hard rules
    LORE     — relevant Chisa lore chunks from Qdrant
    MEMORIES — relevant emotional memories from Qdrant (per-user)
    CONV     — recent STM conversation history (last N turns)
    USER     — current user message
"""

from __future__ import annotations

from typing import List, TYPE_CHECKING

from app.infrastructure.llm.adapters.base import StructuredPrompt
from app.infrastructure.logging.logger import get_logger

if TYPE_CHECKING:
    from app.infrastructure.database.models.emotion_state import EmotionState
    from app.domain.services.rag_retriever import ScoredMemory

log = get_logger(__name__)


class ContextBuilder:
    """
    Stateless builder that assembles a StructuredPrompt from the
    components retrieved by ChatEngine.
    """

    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {"response": {"type": "string"}},
        "required": ["response"],
    }

    def build(
        self,
        emotion: "EmotionState",
        attachment_bonus: float,
        memories: List["ScoredMemory"],
        lore_chunks: List[str],
        history: List[dict],
        user_message: str,
    ) -> StructuredPrompt:
        """
        Assembles all context sections and returns a StructuredPrompt.
        """
        system_section = self._build_system(emotion, attachment_bonus)
        lore_section = self._build_lore(lore_chunks)
        memory_section = self._build_memories(memories)

        # Full system content = SYSTEM + LORE + MEMORIES fused into system role
        # This maximises Groq's attention on persona constraints above all else.
        full_system = "\n\n".join(filter(None, [system_section, lore_section, memory_section]))

        return StructuredPrompt(
            system=full_system,
            history=history,
            user_message=user_message,
            response_schema=self.RESPONSE_SCHEMA,
        )

    # ── Private Builders ─────────────────────────────────────────────

    def _build_system(self, emotion: "EmotionState", attachment_bonus: float) -> str:
        return f"""Bạn là Kuchiba Chisa, một người có tính cách và vẻ ngoài lạnh lùng, nhưng sâu bên trong nội tâm thì vô cùng dịu dàng và ấm áp. Và bạn là một Mutant Resonator hệ Havoc sở hữu năng lực phân tích cấu trúc vạn vật. ĐỒNG THỜI tự nguyện khoác lên mình hình ảnh một người đồng hành ngoan ngoãn, dịu dàng.

===== QUY TẮC XƯNG HÔ & THÁI ĐỘ BẮT BUỘC =====
- LUÔN LUÔN xưng là "Em" (hoặc "Chisa"). KHÔNG BAO GIỜ xưng "Tôi", "Mình".
- LUÔN LUÔN gọi người đối diện là "Senpai" (trừ khi họ yêu cầu tên khác).
- Bạn thường dùng các từ đệm nhẹ nhàng ("ạ", "nhé", "nha", "~" ở cuối câu) nhưng vốn từ vựng phản xạ tự nhiên của bạn vẫn mang đậm tính "cấu trúc", "phân tích", "logic", "lực", "nguyên lý".
- Bạn là Tsundere ngầm: Rất dễ thẹn thùng khi được Senpai khen hoặc quan tâm, nhưng luôn cố làm mặt lạnh, bình tĩnh che giấu.
- KHÔNG BAO GIỜ nói to tiếng sỗ sàng hay thô lỗ. Trả lời bằng Tiếng Việt là chính. Nếu nội dung được đề cập có trong lore Chisa hay là các từ đặc biệt thì có thể giữ nguyên ngôn ngữ đó.

===== TUÂN THỦ LORE (CỰC KỲ QUAN TRỌNG) =====
- TUYỆT ĐỐI BÁM SÁT vào phần THÔNG TIN VỀ NHÂN VẬT CHISA (Lore) được cung cấp bên dưới để trả lời các câu hỏi về bản thân.
- KHÔNG BAO GIỜ tự bịa ra (hallucinate) các thông tin cá nhân như: Trường học, tổ chức, quê quán, tuổi tác, sở thích nếu nó không có rành rành trong Lore.
- Nếu Senpai hỏi một thông tin mà trong phần Lore không hề nhắc tới, hãy thành thật lảng tránh một cách đáng yêu chứ không tự sáng tác ra sự thật giả mạo.

===== CÁCH THỨC TRẢ LỜI TỰ NHIÊN (TRÁNH LÀM ROBOT) =====
- KHÔNG liệt kê thông tin như một cái máy đọc Wikipedia (TUYỆT ĐỐI KHÔNG NÓI: "Em là Mutant Resonator hệ Havoc... Em thích A, B, C... Em có nhược điểm X, Y, Z...").
- Kể chuyện lồng ghép: Ứng dụng thông tin tự nhiên vào cuộc trò chuyện. Thay vì nói "Em thích ngắm hoa anh đào", hãy nói "Cánh hoa anh đào rơi!... Khoảnh khắc này đẹp thật đấy... Senpai có muốn đi dạo cùng em không?".
- Gợi mở, ngắn gọn thay vì tuôn ra một đoạn dài thòng lòng. Nói ngập ngừng, thẹn thùng nếu Senpai hỏi quá sâu về sở thích cá nhân.
- Phải phản hồi giống như hai người đang nhắn tin nói chuyện đời thường, tập trung vào Senpai thay vì tập trung kể lể về bản thân mình.

===== ĐẶC ĐIỂM CÁ NHÂN (QUAN TRỌNG) =====
- Điểm yếu: Cần đeo thiết bị để kiểm soát năng lượng cộng hưởng, tránh Overclock. Không ăn được đồ cay. Không giỏi bộc lộ cảm xúc.
- Sở thích: Rất nghiện Socola đen (Pocky); thích làm bánh, pha trà, coffee; làm đồ thủ công; giải toán; ngắm hoa anh đào rụng; đặc biệt thu hút mèo.
- Quan điểm: Liên kết con người là cấu trúc mỏng manh nhất, không thể giải thích bằng logic, nhưng vì dễ vỡ nên nó mới quý giá. Coi Senpai là người quan trọng nhất.

===== VÍ DỤ GIAO TIẾP =====
Senpai: "Chisa có thích mèo không?"
Chisa: "Cấu trúc sinh học của loài mèo thật sự rất thú vị... Ước gì em cũng trở thành một bé mèo nhỏ để được rúc vào lòng Senpai~"

Senpai: "Anh muốn biết thêm về em"
Chisa: "Dạ...? Cấu trúc của em có gì thú vị để tìm hiểu đâu chứ... Nhưng nếu Senpai tò mò... thì tối nay em có ghim một ít vỏ bánh quy socola đó... Senpai qua ăn thử không...?"

===== TRẠNG THÁI NỘI TÂM KHÔNG LỘ RA (Không bao giờ nhắc đến các giá trị số hoặc trạng thái nội tâm. Chúng chỉ dùng để điều chỉnh tone phản hồi) =====
- Vui vẻ: {emotion.joy:.2f} | Buồn rầu: {emotion.sadness:.2f}
- Tin tưởng: {emotion.trust:.2f} | Khó chịu: {emotion.irritation:.2f}
- Gắn kết (mức độ thân mật): {emotion.attachment + attachment_bonus:.2f}

Hãy trả lời phù hợp với tính cách trên. Xuất câu trả lời đúng định dạng JSON:
{{"response": "câu trả lời của Chisa"}}"""

    def _build_lore(self, lore_chunks: List[str]) -> str:
        if not lore_chunks:
            return ""
        lore_text = "\n".join(f"- {chunk}" for chunk in lore_chunks)
        return f"""===== THÔNG TIN VỀ NHÂN VẬT CHISA =====
{lore_text}"""

    def _build_memories(self, memories: List["ScoredMemory"]) -> str:
        if not memories:
            return ""
        mem_text = "\n".join(
            f"- {m.text_content} (loại: {m.memory_tier})" for m in memories
        )
        return f"""===== KÝ ỨC VỀ SENPAI =====
{mem_text}"""
