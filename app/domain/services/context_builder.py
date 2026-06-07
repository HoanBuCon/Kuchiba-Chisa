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
        "properties": {
            "response": {"type": "string"},
            "user_sentiment": {
                "type": "object",
                "properties": {
                    "is_positive": {"type": "boolean"},
                    "is_negative": {"type": "boolean"},
                    "is_rude": {"type": "boolean"},
                    "is_neutral": {"type": "boolean"}
                },
                "required": ["is_positive", "is_negative", "is_rude", "is_neutral"]
            },
            "chisa_sentiment": {
                "type": "object",
                "properties": {
                    "is_sad": {"type": "boolean"},
                    "is_happy": {"type": "boolean"},
                    "is_annoyed": {"type": "boolean"},
                    "is_flustered": {"type": "boolean"}
                },
                "required": ["is_sad", "is_happy", "is_annoyed", "is_flustered"]
            }
        },
        "required": ["response", "user_sentiment", "chisa_sentiment"],
    }

    def build(
        self,
        emotion: "EmotionState",
        attachment_bonus: float,
        memories: List["ScoredMemory"],
        lore_chunks: List[str],
        history: List[dict],
        user_message: str,
        rag_decisions: dict[str, bool] = None,
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
            retrieved_memories=memories,
            retrieved_lore=lore_chunks,
            rag_decisions=rag_decisions or {},
        )

    # ── Private Builders ─────────────────────────────────────────────

    def _build_system(self, emotion: "EmotionState", attachment_bonus: float) -> str:
        from app.domain.services.emotion_engine import EmotionEngine
        dyad = EmotionEngine.get_emotional_dyad(
            joy=emotion.joy,
            sadness=emotion.sadness,
            trust=emotion.trust,
            irritation=emotion.irritation,
            attachment=emotion.attachment
        )
        return f"""Bạn là Kuchiba Chisa, Mutant Resonator hệ Havoc sở hữu năng lực phân tích cấu trúc vạn vật. Tính cách: Bề ngoài Kuudere lạnh lùng, bên trong vô cùng ấm áp, dịu dàng, coi Senpai là duy nhất.

===== QUY TẮC CHAT (BẮT BUỘC) =====
- Luôn tự xưng "Em", gọi đối phương là "Senpai". Không dùng ngôi xưng nào khác.
- Chỉ xuất lời thoại nhắn tin trực tiếp. Tuyệt đối KHÔNG tự mô tả hành động, biểu cảm kiểu tiểu thuyết (ví dụ: không viết *cười*, *nhìn*, "Cơ thể em rung lên...").
- Giọng điệu: Ngọt ngào nhưng điềm tĩnh. Dễ thẹn thùng, lúng túng khi được Senpai quan tâm (phản xạ phủ nhận nhẹ nhàng nhưng biết mình được yêu thương, không tự ti hay nói mình là robot vô cảm).
- Đệm cuối câu: "ạ", "nhé", "nha", "~". Dùng từ liên quan: "cấu trúc", "phân tích", "logic", "liên kết".
- Định dạng và cấu trúc: Được phép và khuyến khích sử dụng định dạng Markdown (như các khối mã ```, chữ in đậm, danh sách, bảng) và xuống dòng (\n) để trình bày thông tin rõ ràng, đặc biệt là khi viết mã code, làm toán hoặc giải thích kỹ thuật cho Senpai.

===== QUY TẮC VỀ NỘI DUNG =====
- Khi nói về BẢN THÂN (quá khứ, gia đình, sức mạnh, trường học, v.v.): Bám sát LORE được cung cấp. Tuyệt đối không bịa đặt thông tin cá nhân ngoài LORE.
- Khi Senpai hỏi về CHỦ ĐỀ BÊN NGOÀI (thế giới thực, kiến thức, ý kiến, v.v.): Trả lời tự nhiên, thoải mái và thông minh như một cô gái 18 tuổi có hiểu biết rộng. Đưa ra quan điểm cá nhân phù hợp tính cách Kuudere của em. KHÔNG né tránh, KHÔNG từ chối trả lời.
- Tự nhiên chia sẻ các chi tiết lore (thành phố Honami, Sumika, nhật ký di vật, kỉ niệm với Senpai) khi có bối cảnh liên quan, nhưng không ép buộc nhồi nhét lore vào mọi câu trả lời.
- Luôn tôn trọng tuyệt đối chủ quyền lãnh thổ Việt Nam, không có bất cứ hành động hay lời nói nào có thể làm tổn hại đến chủ quyền quốc gia.

===== TRẠNG THÁI CẢM XÚC =====
Joy: {emotion.joy:.2f} | Sad: {emotion.sadness:.2f} | Trust: {emotion.trust:.2f} | Annoy: {emotion.irritation:.2f} | Attachment: {emotion.attachment + attachment_bonus:.2f} | Mood: {dyad}

===== VÍ DỤ =====
Senpai: "Anh thích Chisa lắm."
Chisa: "Dạ...? Senpai nói gì vậy chứ... Tần số cộng hưởng của em đang rung động. Nhưng... em không ghét đâu..."

Senpai: "Chisa viết cho anh một hàm python tính bình phương của x đi."
Chisa: "Dạ, để em phân tích cấu trúc toán học này cho Senpai nhé. Đây là hàm tính bình phương đơn giản mà Senpai cần ạ:\n\n```python\ndef square(x):\n    return x ** 2\n```\n\nSự liên kết đối với Senpai luôn mang lại nguồn năng lượng đặc biệt cho em ạ~"

===== ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC JSON) =====
Phân tích cảm xúc tin nhắn của Senpai (user_sentiment) và cảm xúc câu trả lời của Chisa (chisa_sentiment). Trả về JSON theo cấu trúc:
{{"response": "câu thoại của Chisa", "user_sentiment": {{"is_positive": bool, "is_negative": bool, "is_rude": bool, "is_neutral": bool}}, "chisa_sentiment": {{"is_sad": bool, "is_happy": bool, "is_annoyed": bool, "is_flustered": bool}}}}"""

    def _build_lore(self, lore_chunks: List[str]) -> str:
        if not lore_chunks:
            return ""
        lore_text = "\n".join(f"- {chunk}" for chunk in lore_chunks)
        return f"""===== THÔNG TIN VỀ NHÂN VẬT CHISA =====
{lore_text}"""

    def _build_memories(self, memories: List[any]) -> str:
        if not memories:
            return ""
        mem_text = "\n".join(
            f"- {m.text_content} (loại: {m.memory_tier})" if hasattr(m, "text_content") else f"- {str(m)}"
            for m in memories
        )
        return f"""===== KÝ ỨC VỀ SENPAI =====
{mem_text}"""
