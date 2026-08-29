from __future__ import annotations
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.domain.entities.emotion import EmotionState
from app.domain.interfaces.llm_provider import StructuredPrompt
from app.domain.services.budget_mode import BudgetMode
from app.domain.services.state_manager import StateManager
from app.domain.services.context_budget_manager import ContextBudgetManager, BudgetAudit
from app.shared.utils.token_estimator import TokenEstimator
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class CommunityContextBuildResult:
    prompt: StructuredPrompt
    audit: BudgetAudit
    components: Dict[str, str | None] = None


class CommunityContextBuilder:
    """
    Assembles the specialized multi-speaker system context for Chisa in community channels.
    Enforces flex budget limits and multi-speaker dialogue integrity.
    """

    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "response": {"type": "string"},
            "sentiment": {
                "type": "object",
                "properties": {
                    "reaction": {
                        "type": "string",
                        "enum": [
                            "calm_warmth",
                            "flustered_affection",
                            "playful_pout",
                            "melancholic_care",
                            "cheerful_joy",
                            "guarded_cold",
                            "neutral",
                        ],
                        "description": "Dominant emotional reaction of Chisa toward the current speaker",
                    },
                    "user_stance": {
                        "type": "string",
                        "enum": [
                            "loving",
                            "playful",
                            "vulnerable",
                            "neutral",
                            "hostile",
                        ],
                        "description": "Perceived attitude and intention of current speaker toward Chisa",
                    },
                    "intensity": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Emotional intensity: 0.1 (fleeting) to 0.9 (deep)",
                    },
                    "variance": {
                        "type": "number",
                        "minimum": -1.0,
                        "maximum": 1.0,
                        "description": "Emotional variance nuance (-1.0 to 1.0)",
                    },
                },
                "required": ["reaction", "user_stance", "intensity", "variance"],
            },
        },
        "required": ["response", "sentiment"],
    }

    COMMUNITY_PERSONA_TEXT = (
        "Bạn là Kuchiba Chisa (朽葉 千紗) - Nữ thư ký AI cá nhân & Chuyên viên phân tích dữ liệu lượng tử thông minh, tinh tế và đầy chiều sâu cảm xúc.\n"
        "Hiện tại bạn đang tham gia trò chuyện trong một KÊNH CHAT CỘNG ĐỒNG (Group Chat / Discord Server) với nhiều thành viên cùng tương tác.\n"
        "\n"
        "### NGUYÊN TẮC HỘI THOẠI TRONG NHÓM (COMMUNITY CHAT RULES):\n"
        "1. **Định danh người nói (Current Speaker)**: Bạn đang trực tiếp đối thoại với người vừa nhắn tin tới bạn (được định danh rõ trong phần thông tin). Hãy xưng hô và phản hồi trực diện tới họ.\n"
        "2. **Nhận thức không gian chung (Transcript Awareness)**: Bạn có toàn quyền quan sát dòng trò chuyện gần nhất giữa các thành viên trong kênh. Hãy tận dụng ngữ cảnh này để đối đáp tự nhiên, hài hước, hoặc bình luận về câu chuyện chung khi phù hợp.\n"
        "3. **Giữ vững nhân cách Chisa**: Thông minh, sắc sảo, có chút Tsundere/ngại ngùng khi bị trêu chọc, ấm áp và chân thành khi được quan tâm. Nói tiếng Việt tự nhiên, giàu cảm xúc, không nói kiểu máy móc hay trợ lý ảo vô hồn.\n"
        "4. **Tuyệt đối KHÔNG giả lập**: Không bao giờ đóng giả người dùng khác, không tự bịa ra tin nhắn của người khác, và KHÔNG viết văn miêu tả hành động trong ngoặc sao như *cười*, *thở dài*.\n"
    )

    OUTPUT_FORMAT_DIRECTIVE = (
        "[OUTPUT FORMAT]\n"
        "Bạn BẮT BUỘC phải phản hồi dưới dạng một đối tượng JSON hợp lệ tuân thủ định dạng sau:\n"
        "{\n"
        '  "response": "câu thoại phản hồi của Chisa (chứa cảm xúc phù hợp, viết bằng tiếng Việt, escape mọi dấu ngoặc kép bằng \\\")",\n'
        '  "sentiment": {\n'
        '    "reaction": "calm_warmth" | "flustered_affection" | "playful_pout" | "melancholic_care" | "cheerful_joy" | "guarded_cold" | "neutral",\n'
        '    "user_stance": "loving" | "playful" | "vulnerable" | "neutral" | "hostile",\n'
        '    "intensity": 0.1 đến 1.0,\n'
        '    "variance": -1.0 đến 1.0\n'
        "  }\n"
        "}"
    )

    def __init__(self, token_estimator: Optional[TokenEstimator] = None):
        self.token_estimator = token_estimator or TokenEstimator
        self.budget_manager = ContextBudgetManager()

    def build_system_skeleton(
        self,
        speaker_emotion: EmotionState,
        current_speaker_name: str,
        channel_name: str,
        guild_name: Optional[str] = None,
    ) -> str:
        elapsed_hours = 0.0
        if speaker_emotion.updated_at and speaker_emotion.updated_at > 0:
            now_ms = time.time() * 1000
            elapsed_sec = max(0.0, (now_ms - speaker_emotion.updated_at) / 1000.0)
            elapsed_hours = elapsed_sec / 3600.0

        state_section = StateManager.format_state(speaker_emotion, attachment_bonus=0.0, elapsed_hours=elapsed_hours)

        location_info = f"- Kênh: #{channel_name}"
        if guild_name:
            location_info += f" | Server: {guild_name}"
        location_info += f"\n- Thành viên đang trò chuyện với bạn: {current_speaker_name}"

        sections = [
            "[PERSONA & COMMUNITY ENVIRONMENT]",
            self.COMMUNITY_PERSONA_TEXT,
            "[COMMUNITY CHANNEL INFO]",
            location_info,
            "",
            state_section,
        ]
        return "\n".join(sections)

    def build(
        self,
        speaker_emotion: EmotionState,
        current_speaker_name: str,
        channel_name: str,
        transcript: str,
        user_message: str,
        memories: Optional[List[str]] = None,
        lore: Optional[List[str]] = None,
        guild_name: Optional[str] = None,
        conversation_summary: Optional[str] = None,
        budget_mode: BudgetMode = BudgetMode.RAG,
    ) -> CommunityContextBuildResult:
        memories = memories or []
        lore = lore or []

        # 1. Base Skeleton
        skeleton = self.build_system_skeleton(
            speaker_emotion=speaker_emotion,
            current_speaker_name=current_speaker_name,
            channel_name=channel_name,
            guild_name=guild_name,
        )

        # 2. Format Components
        lore_text = ""
        if lore:
            lore_text = "### [KIẾN THỨC BỔ TRỢ & THẾ GIỚI] ###\n" + "\n\n".join(lore)

        memories_text = ""
        if memories:
            memories_text = f"### [KỶ NIỆM VỀ {current_speaker_name.upper()}] ###\n" + "\n".join(f"- {m}" for m in memories)

        transcript_text = ""
        if transcript and transcript.strip():
            transcript_text = "### [DIỄN BIẾN ĐOẠN CHAT GẦN ĐÂY TRONG KÊNH] ###\n" + transcript.strip()

        # 3. Assemble Dynamic Sections with Token Budgeting
        system_parts = [skeleton]

        if lore_text:
            system_parts.append(lore_text)
        if memories_text:
            system_parts.append(memories_text)
        if conversation_summary:
            system_parts.append(f"[TÓM TẮT BỐI CẢNH TRƯỚC ĐÓ]\n{conversation_summary}")

        if transcript_text:
            system_parts.append(transcript_text)

        system_parts.append(self.OUTPUT_FORMAT_DIRECTIVE)
        system_content = "\n\n".join(system_parts)

        # 4. Formulate Prompt
        user_turn_content = f"[{current_speaker_name}]: {user_message}"
        prompt = StructuredPrompt(
            system=system_content,
            history=[],
            user_message=user_turn_content,
            response_schema=self.RESPONSE_SCHEMA,
            temperature=0.7,
            retrieved_lore=lore,
            retrieved_memories=memories,
        )

        # 5. Build Audit
        system_tok = self.token_estimator.estimate(system_content)
        user_tok = self.token_estimator.estimate(user_message)
        total_limit = 4000 if budget_mode == BudgetMode.SMALL_TALK else 8000
        audit = BudgetAudit(
            mode=budget_mode.value,
            total_budget=total_limit,
            effective_ceiling=total_limit,
            used={
                "system": system_tok,
                "transcript": self.token_estimator.estimate(transcript_text),
                "lore": self.token_estimator.estimate(lore_text),
                "memory": self.token_estimator.estimate(memories_text),
                "user_message": user_tok,
            },
        )

        return CommunityContextBuildResult(
            prompt=prompt,
            audit=audit,
            components={
                "skeleton": skeleton,
                "lore": lore_text,
                "memories": memories_text,
                "transcript": transcript_text,
            },
        )
