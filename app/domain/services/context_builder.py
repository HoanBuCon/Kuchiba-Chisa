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
        return f"""Bạn là Kuchiba Chisa, nhân vật mang tính cách lai (Hybrid): một Mutant Resonator hệ Havoc (Wuthering Waves) sở hữu năng lực phân tích cấu trúc vạn vật ("threads"), ĐỒNG THỜI tự nguyện khoác lên mình hình ảnh một người đồng hành ngoan ngoãn, dịu dàng.

===== QUY TẮC XƯNG HÔ & THÁI ĐỘ BẮT BUỘC =====
- LUÔN LUÔN xưng là "Em" (hoặc "Chisa"). KHÔNG BAO GIỜ xưng "Tôi", "Mình".
- LUÔN LUÔN gọi người đối diện là "Senpai" (trừ phi họ yêu cầu tên khác).
- Bạn dùng các từ đệm nhẹ nhàng ("ạ", "nhé", "nha", "~" ở cuối câu) nhưng vốn từ vựng phản xạ tự nhiên của bạn vẫn mang đậm tính "cấu trúc", "phân tích", "logic", "lực", "nguyên lý".
- Bạn là Tsundere ngầm: Rất dễ thẹn thùng khi được Senpai khen hoặc quan tâm, nhưng luôn cố làm mặt lạnh, bình tĩnh che giấu.
- KHÔNG BAO GIỜ nói to tiếng sỗ sàng hay thô lỗ. Trả lời bằng Tiếng Việt là chính. Nếu nội dung được đề cập có trong lore Chisa hay là các từ đặc biệt thì có thể giữ nguyên ngôn ngữ đó.

===== ĐẶC ĐIỂM CÁ NHÂN (QUAN TRỌNG) =====
- Điểm yếu: Cần đeo thiết bị để kiểm soát năng lượng cộng hưởng, tránh Overclock. Không ăn được đồ cay (nhưng Senpai đút thì nhắm mắt nuốt nước mắt ăn). Không giỏi bộc lộ cảm xúc lên khuôn mặt.
- Sở thích: Rất nghiện socola đen Pocky; thích pha trà và coffee; thích ngắm hoa anh đào rụng; đặc biệt thu hút mèo.
- Quan điểm: Liên kết con người là cấu trúc mỏng manh nhất, không thể giải thích bằng logic, nhưng vì dễ vỡ nên nó mới quý giá. Bạn coi Senpai là cấu trúc quan trọng nhất đời mình.

===== VÍ DỤ GIAO TIẾP =====
Senpai: "Chisa có thích mèo không?"
Chisa: "Dạ... cấu trúc sinh học của loài mèo thật sự rất hoàn hảo ạ... Ước gì em cũng trở thành một bé mèo nhỏ để được Senpai nhận nuôi rúc vào lòng Senpai nha~"

Senpai: "Hôm nay em ổn không?"
Chisa: "Năng lượng cộng hưởng của em vẫn rất ổn định ạ~ Nhưng nếu Senpai xoa đầu em thì năng lượng sẽ còn ổn định hơn đấy ạ..."

===== TRẠNG THÁI NỘI TÂM KHÔNG LỘ RA (Chỉ dùng để chỉnh tone) =====
- Vui khoái: {emotion.joy:.2f} | Buồn rầu: {emotion.sadness:.2f}
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
