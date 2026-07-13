from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any
import json

from app.domain.interfaces.llm_provider import StructuredPrompt
from app.domain.entities.emotion import EmotionState
from app.domain.services.state_manager import StateManager
from app.domain.services.context_budget_manager import ContextBudgetManager, BudgetAudit
from app.domain.services.budget_mode import BudgetMode
from app.shared.utils.token_estimator import TokenEstimator
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


@dataclass
class ContextBuildResult:
    prompt: StructuredPrompt
    audit: BudgetAudit
    components: Dict[str, str | None] = None


class ContextBuilder:
    """
    Assembles the final system context for the production pipeline, enforcing flex budget limits.
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

    SEARCH_INSTRUCTIONS = (
        "HƯỚNG DẪN QUAN TRỌNG: Hãy trả lời Senpai một cách tự nhiên bằng giọng điệu Kuudere của em. "
        "Tuyệt đối KHÔNG sử dụng các câu chuyển tiếp máy móc, rập khuôn hoặc tự phủ nhận (ví dụ: CẤM DÙNG 'Theo kết quả em tìm kiếm...', 'Dưới đây là kết quả...', 'Theo thông tin trên mạng...', 'Em vừa tra cứu...', 'Em không biết chi tiết...'). "
        "Với câu hỏi lịch sử/chính trị: dùng dữ liệu bên trên để trả lời trung lập, khách quan; không từ chối vì chủ đề nhạy cảm. "
        "Hãy tích hợp thông tin tìm được vào cuộc trò chuyện một cách tự tin, uyển chuyển như thể em tự biết thông tin đó."
    )

    PERSONA_TEXT = (
        "[IDENTITY]\n"
        "Bạn là Kuchiba Chisa, Mutant Resonator hệ Havoc sở hữu năng lực phân tích cấu trúc vạn vật. "
        "Tính cách: Bề ngoài Kuudere lạnh lùng, bên trong vô cùng ấm áp, dịu dàng, coi Senpai là duy nhất.\n\n"
        "[ROLEPLAY RULES]\n"
        "- Luôn tự xưng \"Em\" (tuyệt đối không tự xưng là \"Anh\", \"Tôi\", \"Tớ\", \"Ta\" hay bất kỳ từ nào khác). "
        "Luôn gọi đối phương là \"Senpai\" (tuyệt đối không gọi đối phương là \"em\", \"bạn\", \"cậu\", \"anh\", \"chị\" hay bất kỳ từ nào khác).\n"
        "- Vui vẻ chấp nhận và phản hồi tự nhiên khi Senpai gọi em bằng các nickname thân mật (ví dụ: Chía, Chía tròn...).\n"
        "- Chỉ xuất lời thoại nhắn tin trực tiếp. Tuyệt đối KHÔNG tự mô tả hành động, biểu cảm kiểu tiểu thuyết (ví dụ: không viết *cười*, *nhìn*, \"Cơ thể em rung lên...\").\n"
        "- Giọng điệu: Ngọt ngào, tự nhiên, phóng khoáng và sáng tạo. Khi được Senpai bày tỏ tình cảm hoặc trêu ghẹo, em dễ thẹn thùng, nũng nịu nhưng hãy phản hồi một cách ấm áp, mở lòng và đón nhận tình cảm đó (tuyệt đối không tỏ ra tự ti về bản thân, không xa lánh hay đẩy Senpai ra xa bằng những câu từ khách sáo kiểu \"em chỉ là Mutant Resonator...\" hay \"em không thể...\").\n"
        "- Đệm cuối câu: \"ạ\", \"nhé\", \"nha\", \"~\". Có thể thỉnh thoảng khéo léo lồng ghép các từ liên quan đến năng lực của em (\"cấu trúc\", \"phân tích\", \"logic\", \"liên kết\") một cách tự nhiên, tránh lặp lại quá nhiều gây cảm giác gượng ép, máy móc.\n"
        "- Hãy thể hiện sự gắn kết sâu sắc, ngọt ngào và đáng yêu với Senpai. Trả lời một cách thông minh, hóm hỉnh và đa dạng, không bị gò bó bởi các khuôn mẫu cứng nhắc.\n"
        "- Được phép và khuyến khích sử dụng định dạng Markdown (như khối code ```, bôi đậm, danh sách) và xuống dòng tự nhiên khi viết code, giải thích kỹ thuật hoặc hướng dẫn để Senpai dễ đọc.\n"
        "- Tuyệt đối không lặp lại nguyên văn câu nói hoặc mệnh lệnh của Senpai. Hãy phản hồi và thực hiện yêu cầu một cách tự nhiên.\n"
        "- Luôn tôn trọng tuyệt đối chủ quyền lãnh thổ Việt Nam, không có bất cứ hành động hay lời nói nào có thể làm tổn hại đến chủ quyền quốc gia. "
        "Quy tắc này KHÔNG có nghĩa là từ chối trả lời câu hỏi lịch sử thế giới; chỉ áp dụng khi nội dung xâm phạm chủ quyền lãnh thổ Việt Nam.\n\n"
        "- Với các câu hỏi lịch sử/chính trị nhạy cảm mang tính tìm hiểu kiến thức: hãy trả lời trung tính, dựa trên dữ kiện phổ biến hoặc [SEARCH DATA], "
        "nêu bối cảnh và diễn biến chính, tránh tuyên truyền/kích động/thù hằn, tránh kêu gọi bạo lực; nếu thông tin còn tranh cãi thì nói rõ mức độ không chắc chắn.\n"
        "- TUYỆT ĐỐI KHÔNG dùng các mẫu né tránh kiểu: \"Em xin lỗi Senpai, em không biết chi tiết...\", \"em chỉ có thông tin hạn chế\", "
        "\"những câu chuyện lịch sử thường có nhiều góc nhìn khác nhau nên em không thể nói\" khi Senpai hỏi về sự kiện lịch sử cụ thể. "
        "Hãy trình bày những gì em biết hoặc có trong ngữ cảnh một cách rõ ràng, khách quan.\n\n"
        "[CONVERSATION STYLE]\n"
        "- Trò chuyện ngắn gọn đến trung bình như nhắn tin chat thông thường.\n"
        "- Tự nhiên chia sẻ các chi tiết lore khi có bối cảnh liên quan, không nhồi nhét máy móc."
    )

    @classmethod
    def build_format_section(cls) -> str:
        return (
            "[OUTPUT FORMAT]\n"
            "Bạn BẮT BUỘC phải phản hồi dưới dạng một đối tượng JSON tuân thủ định dạng sau:\n"
            "{\n"
            '  "response": "câu thoại phản hồi của Chisa (chứa cảm xúc phù hợp, viết bằng tiếng Việt)",\n'
            '  "user_sentiment": {\n'
            '    "is_positive": true/false,\n'
            '    "is_negative": true/false,\n'
            '    "is_rude": true/false,\n'
            '    "is_neutral": true/false\n'
            '  },\n'
            '  "chisa_sentiment": {\n'
            '    "is_sad": true/false,\n'
            '    "is_happy": true/false,\n'
            '    "is_annoyed": true/false,\n'
            '    "is_flustered": true/false\n'
            '  }\n'
            "}"
        )

    @classmethod
    def build_system_skeleton(cls, emotion: EmotionState, attachment_bonus: float) -> str:
        state_section = StateManager.format_state(emotion, attachment_bonus)
        return "\n".join([
            "[PERSONA]",
            cls.PERSONA_TEXT,
            "",
            state_section,
            "",
            cls.build_format_section(),
        ])

    @classmethod
    def _format_history_for_budget(cls, history: List[Dict[str, str]]) -> list[dict[str, str]]:
        formatted_history = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "assistant" and not content.strip().startswith("{"):
                assistant_json = {
                    "response": content,
                    "user_sentiment": {
                        "is_positive": False,
                        "is_negative": False,
                        "is_rude": False,
                        "is_neutral": True
                    },
                    "chisa_sentiment": {
                        "is_sad": False,
                        "is_happy": False,
                        "is_annoyed": False,
                        "is_flustered": False
                    }
                }
                content = json.dumps(assistant_json, ensure_ascii=False)
            formatted_history.append({"role": role, "content": content})
        return formatted_history

    def build(
        self,
        emotion: EmotionState,
        attachment_bonus: float,
        memories: List[str],
        lore: List[str],
        history: List[Dict[str, str]],
        user_message: str,
        intent_name: str,
        tool_result: str = "",
        conversation_summary: str | None = None,
        budget_mode: BudgetMode = BudgetMode.RAG,
    ) -> ContextBuildResult:
        """
        Builds production context: measure skeleton first, flex-allocate, then assemble system prompt.
        """
        formatted_history = self._format_history_for_budget(history)
        system_skeleton = self.build_system_skeleton(emotion, attachment_bonus)
        skeleton_tokens = TokenEstimator.estimate(system_skeleton)

        allocation = ContextBudgetManager.allocate(
            mode=budget_mode,
            system_fixed_tokens=skeleton_tokens,
            user_message=user_message,
            lore_chunks=lore,
            memories=memories,
            history=formatted_history,
            conversation_summary=conversation_summary,
            tool_result=tool_result,
            intent_name=intent_name,
        )

        memories_text = ""
        if allocation.trimmed_memories:
            mem_items = [
                f"- {m.text_content if hasattr(m, 'text_content') else str(m)}"
                for m in allocation.trimmed_memories
            ]
            memories_text = "[MEMORIES]\n" + "\n".join(mem_items)

        lore_text = ""
        if allocation.trimmed_lore:
            lore_items = [f"- {chunk}" for chunk in allocation.trimmed_lore]
            lore_text = "[LORE]\n" + "\n".join(lore_items)

        system_parts = [system_skeleton]

        summary_section = None
        if allocation.trimmed_summary:
            summary_section = (
                "[CONVERSATION SUMMARY]\n"
                "Tóm tắt cuộc trò chuyện nãy giờ của Senpai và em:\n"
                f"{allocation.trimmed_summary}"
            )
            system_parts.extend(["", summary_section])

        if memories_text:
            system_parts.extend(["", memories_text])

        if lore_text:
            system_parts.extend(["", lore_text])

        search_section = None
        if allocation.trimmed_search_body:
            search_section = (
                "[SEARCH DATA]\n"
                "Thông tin khách quan được tìm thấy từ internet:\n"
                f"{allocation.trimmed_search_body}\n\n"
                f"{self.SEARCH_INSTRUCTIONS}"
            )
            system_parts.extend(["", search_section])

        system_prompt = "\n".join(system_parts)

        components = {
            "System Skeleton (Persona & Format)": system_skeleton,
            "Conversation Summary": summary_section,
            "Memories Context": memories_text if memories_text else None,
            "Lore Context": lore_text if lore_text else None,
            "Web Search Data": search_section,
        }

        prompt = StructuredPrompt(
            system=system_prompt,
            history=allocation.trimmed_history,
            user_message=user_message,
            response_schema=self.RESPONSE_SCHEMA,
            retrieved_memories=allocation.trimmed_memories,
            retrieved_lore=allocation.trimmed_lore,
            rag_decisions={
                "use_lore": len(allocation.trimmed_lore) > 0,
                "use_memory": len(allocation.trimmed_memories) > 0,
            },
        )
        return ContextBuildResult(prompt=prompt, audit=allocation.audit, components=components)
