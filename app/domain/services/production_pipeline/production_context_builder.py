from typing import List, Dict, Any
from app.infrastructure.llm.adapters.base import StructuredPrompt
from app.infrastructure.database.models.emotion_state import EmotionState
from app.domain.services.production_pipeline.state_manager import StateManager
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

class ProductionContextBuilder:
    """
    Assembles the final system context for the production pipeline, enforcing budget limits.
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
        "- Luôn tôn trọng tuyệt đối chủ quyền lãnh thổ Việt Nam, không có bất cứ hành động hay lời nói nào có thể làm tổn hại đến chủ quyền quốc gia.\n\n"
        "[CONVERSATION STYLE]\n"
        "- Trò chuyện ngắn gọn đến trung bình như nhắn tin chat thông thường.\n"
        "- Tự nhiên chia sẻ các chi tiết lore khi có bối cảnh liên quan, không nhồi nhét máy móc."
    )

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 4

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
    ) -> StructuredPrompt:
        """
        Builds the production context using context building pipeline.
        """
        # 1. State section
        state_section = StateManager.format_state(emotion, attachment_bonus)
        
        # 2. Memories section
        # Enforce budget of ~300 tokens
        memories_text = ""
        if memories:
            mem_items = []
            current_tokens = 0
            for m in memories:
                item = f"- {m}"
                item_tokens = self._estimate_tokens(item)
                if current_tokens + item_tokens > 300:
                    break
                mem_items.append(item)
                current_tokens += item_tokens
            if mem_items:
                memories_text = "[MEMORIES]\n" + "\n".join(mem_items)
                
        # 3. Lore section
        # Enforce budget of ~800 tokens
        lore_text = ""
        if lore:
            lore_items = []
            current_tokens = 0
            for l in lore:
                item = f"- {l}"
                item_tokens = self._estimate_tokens(item)
                if current_tokens + item_tokens > 800:
                    break
                lore_items.append(item)
                current_tokens += item_tokens
            if lore_items:
                lore_text = "[LORE]\n" + "\n".join(lore_items)

        # 4. Assemble system prompt
        format_section = (
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
        system_parts = [
            "[PERSONA]",
            self.PERSONA_TEXT,
            "",
            state_section,
            "",
            format_section
        ]
        if memories_text:
            system_parts.extend(["", memories_text])
        if lore_text:
            system_parts.extend(["", lore_text])
        if tool_result:
            search_section = (
                "[SEARCH RESULTS]\n"
                "Em vừa tra cứu được thông tin sau đây từ internet. "
                "Hãy tóm tắt và trả lời Senpai dựa trên nội dung này:\n"
                f"{tool_result}"
            )
            system_parts.extend(["", search_section])
            
        system_prompt = "\n".join(system_parts)
        
        import json
        trimmed_history = []
        current_history_tokens = 0
        for turn in reversed(history):
            role = turn.get("role", "user")
            content = turn.get("content", "")
            
            # Format assistant messages as JSON to avoid contradicting JSON output mode
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
                
            turn_str = f"{role}: {content}"
            turn_tokens = self._estimate_tokens(turn_str)
            if current_history_tokens + turn_tokens > 800:
                break
            trimmed_history.insert(0, {"role": role, "content": content})
            current_history_tokens += turn_tokens

        return StructuredPrompt(
            system=system_prompt,
            history=trimmed_history,
            user_message=user_message,
            response_schema=self.RESPONSE_SCHEMA,
            retrieved_memories=memories,
            retrieved_lore=lore,
            rag_decisions={"use_lore": len(lore) > 0, "use_memory": len(memories) > 0}
        )
