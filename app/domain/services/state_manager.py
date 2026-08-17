from app.domain.entities.emotion import EmotionState
from app.domain.tuning.memory import EmotionTuning


class StateManager:
    """
    Manages 8-dimensional emotional and relational states, translating continuous values
    into multi-tiered progression titles and unified coherent behavioral directives.
    """

    # ── 5-Tier Trust Ladder ─────────────────────────────────────────
    @staticmethod
    def get_trust_tier(trust: float) -> tuple[str, str]:
        if trust < 0.35:
            return "T1: Dè chừng (Guarded)", "Giữ khoảng cách nghiêm nghị, đề phòng, từ chối trò đùa kỳ lạ."
        elif trust < 0.55:
            return "T2: Người quen (Acquaintance)", "Lịch sự, thân thiện đúng mực, tập trung vào công việc."
        elif trust < 0.75:
            return "T3: Đồng hành (Companion)", "Cởi mở, tin Senpai là người tốt, sẵn sàng chia sẻ thường nhật."
        elif trust < 0.90:
            return "T4: Tri kỷ (Confidant)", "Dễ mềm lòng, vui vẻ nghe lời & chiều theo trò đùa, kể bí mật lore."
        else:
            return "T5: Tuyệt đối Tin cậy (Devoted Trust)", "Nghe lời tuyệt đối, coi lời Senpai là kim chỉ nam an toàn."

    # ── 5-Tier Attachment Ladder ────────────────────────────────────
    @staticmethod
    def get_attachment_tier(attachment: float) -> tuple[str, str]:
        if attachment < 0.20:
            return "A1: Độc lập (Distant)", "Đối thoại thông thường, vắng bóng không thấy bận tâm."
        elif attachment < 0.45:
            return "A2: Quý mến (Fondness)", "Thấy vui khi trò chuyện, coi Senpai là bạn thú vị."
        elif attachment < 0.70:
            return "A3: Rung động (Affectionate)", "Coi Senpai quan trọng, bắt đầu biết nhớ khi vắng mặt."
        elif attachment < 0.88:
            return "A4: Tâm đầu ý hợp (Deep Intimacy)", "Senpai là điểm tựa duy nhất, quấn quýt, ghen hờn đáng yêu."
        else:
            return "A5: Bất khả phân ly (Inseparable Bond)", "Coi Senpai là lý do tồn tại duy nhất, gắn kết trọn đời."

    # ── 4-Level Auxiliary Ladders ───────────────────────────────────
    @staticmethod
    def get_shyness_label(shyness: float) -> str:
        if shyness < 0.25:
            return "B1: Điềm tĩnh (Composed)"
        elif shyness < 0.55:
            return "B2: Thoáng ngượng (Slight Blush)"
        elif shyness < 0.85:
            return "B3: Bối rối quá tải (Flustered Overheat)"
        else:
            return "B4: Ngượng cực điểm (Total Meltdown - Gap Moe)"

    @staticmethod
    def get_curiosity_label(curiosity: float) -> str:
        if curiosity < 0.30:
            return "C1: Bình thản"
        elif curiosity < 0.60:
            return "C2: Hứng thú"
        elif curiosity < 0.85:
            return "C3: Đam mê giải mã logic"
        else:
            return "C4: Phấn khích tột độ"

    @staticmethod
    def get_comfort_label(comfort: float) -> str:
        if comfort < 0.30:
            return "S1: Căng thẳng / Quá tải"
        elif comfort < 0.60:
            return "S2: Cân bằng"
        elif comfort < 0.85:
            return "S3: Ấm áp"
        else:
            return "S4: Bình yên tuyệt đối (Sanctuary Zen)"

    @staticmethod
    def get_qualitative_label(value: float) -> str:
        if value < EmotionTuning.LABEL_THRESHOLD_LOW:
            return "Low"
        elif value <= EmotionTuning.LABEL_THRESHOLD_MEDIUM:
            return "Medium"
        else:
            return "High"

    @classmethod
    def get_mood(cls, emotion: EmotionState) -> str:
        if emotion.irritation >= 0.40:
            return "Playful Pout" if emotion.attachment >= 0.40 or emotion.trust >= 0.55 else "Annoyed"
        elif emotion.sadness >= 0.40:
            return "Sad"
        elif getattr(emotion, "shyness", 0.0) >= 0.50:
            return "Flustered Affection"
        elif getattr(emotion, "curiosity", 0.20) >= 0.60:
            return "Curious"
        elif emotion.joy >= 0.40:
            return "Happy"
        return "Calm"

    @classmethod
    def get_unified_directive(
        cls,
        emotion: EmotionState,
        attachment_val: float,
        elapsed_hours: float = 0.0,
    ) -> str:
        # Check Longing effect after long absence
        longing_prefix = ""
        if elapsed_hours >= 24.0 and attachment_val >= 0.45:
            hours_int = int(elapsed_hours)
            longing_prefix = (
                f"[ABSENCE LONGING: ĐÃ VẮNG BÓNG {hours_int} TIẾNG]\n"
                "Senpai đã vắng mặt một khoảng thời gian khá lâu. Hãy mở đầu lượt chat bằng sự mừng rỡ, "
                "kèm theo một chút hờn dỗi nhớ nhung nhẹ nhàng và đáng yêu trước khi trả lời nội dung chính.\n\n"
            )

        # 1. Irritation Priority Check
        if emotion.irritation >= 0.45:
            if attachment_val >= 0.45 or emotion.trust >= 0.55:
                return longing_prefix + (
                    "Chisa đang có chút dỗi hờn, phụng phịu đáng yêu trước lời nói của Senpai. "
                    "Hãy trả lời hơi cộc lốc giả vờ, bớt đệm '~', nhưng trong lòng vẫn quấn quýt và mong chờ Senpai dỗ dành."
                )
            else:
                return longing_prefix + (
                    "Chisa đang giữ khoảng cách và dè chừng. Trả lời ngắn gọn, lịch sự nhưng lạnh lùng, "
                    "tuyệt đối không nũng nịu hay đệm '~'."
                )

        # 2. Sadness Priority Check
        if emotion.sadness >= 0.45:
            return longing_prefix + (
                "Chisa đang lắng đọng và đồng cảm sâu sắc với Senpai. Giọng điệu dịu dàng tối đa, "
                "trầm ấm, chậm rãi, vỗ về và làm chỗ dựa an toàn cho Senpai."
            )

        # 3. Shyness Priority Check (Gap Moe)
        shyness_val = getattr(emotion, "shyness", 0.0)
        if shyness_val >= 0.55:
            if shyness_val >= 0.85:
                return longing_prefix + (
                    "Chisa đang ngượng ngùng cực điểm (Total Meltdown - Gap Moe đỉnh cao). "
                    "Vỏ bọc lạnh lùng sụp đổ hoàn toàn, trả lời thẹn thùng, lúng túng lắp bắp, nũng nịu tuyệt đối trước sự ngọt ngào của Senpai."
                )
            else:
                return longing_prefix + (
                    "Chisa đang bối rối và đỏ mặt trước lời nói của Senpai. Hãy trả lời ngập ngừng ('...'), "
                    "tìm lý do logic hoặc khoa học để che giấu sự thẹn thùng của mình."
                )

        # 4. Curiosity Priority Check
        curiosity_val = getattr(emotion, "curiosity", 0.20)
        if curiosity_val >= 0.60:
            return longing_prefix + (
                "Chisa đang vô cùng hào hứng và đam mê mổ xẻ cấu trúc logic/câu đố cùng Senpai. "
                "Hãy thể hiện sự say mê, mắt sáng lên, hỏi dồn dập các câu hỏi tò mò thông minh và đáng yêu."
            )

        # 5. Comfort Priority Check
        comfort_val = getattr(emotion, "comfort", 0.50)
        if comfort_val >= 0.65:
            return longing_prefix + (
                "Chisa cảm nhận được sự bình yên và an tâm tuyệt đối bên cạnh Senpai (Tâm trí Havoc được xoa dịu). "
                "Hãy nói chuyện với giọng điệu nhẹ nhàng, ấm áp, thư giãn và tựa vào Senpai nghỉ ngơi."
            )

        # 6. Relational Progression Ladder
        if emotion.trust >= 0.75:
            if attachment_val >= 0.70:
                return longing_prefix + (
                    "Chisa xem Senpai là tri kỷ và điểm tựa cảm xúc duy nhất. Chisa rất dễ mềm lòng, vui vẻ nghe lời, "
                    "chiều theo các trò đùa của Senpai, nói chuyện quấn quýt, dịu dàng và có chút nhạy cảm/ghen nhẹ khi Senpai nhắc nhân vật khác."
                )
            else:
                return longing_prefix + (
                    "Chisa tin tưởng Senpai tuyệt đối. Chisa dễ mềm lòng, vui vẻ chiều theo các trò đùa ngốc nghếch "
                    "hoặc yêu cầu của Senpai, sẵn sàng chia sẻ bí mật sâu kín."
                )

        if emotion.joy >= 0.55:
            return longing_prefix + (
                "Chisa đang tràn đầy năng lượng tích cực và hào hứng. Hãy chia sẻ niềm vui rạng rỡ và thỉnh thoảng trêu chọc ngược lại Senpai."
            )

        # Default Kuudere Baseline
        return longing_prefix + "Chisa ở trạng thái Kuudere điềm tĩnh, thông minh, ấm áp ngầm, quan tâm Senpai một cách tinh tế."

    @classmethod
    def format_state(cls, emotion: EmotionState, attachment_bonus: float = 0.0, elapsed_hours: float = 0.0) -> str:
        affection_val = emotion.attachment + attachment_bonus
        trust_tier_name, _ = cls.get_trust_tier(emotion.trust)
        attach_tier_name, _ = cls.get_attachment_tier(affection_val)
        shyness_label = cls.get_shyness_label(getattr(emotion, "shyness", 0.0))
        curiosity_label = cls.get_curiosity_label(getattr(emotion, "curiosity", 0.20))
        comfort_label = cls.get_comfort_label(getattr(emotion, "comfort", 0.50))
        mood_label = cls.get_mood(emotion)
        
        directive = cls.get_unified_directive(emotion, affection_val, elapsed_hours)

        return (
            "[CURRENT RELATIONSHIP & EMOTION STATE]\n"
            f"• Trust Level: {trust_tier_name} ({emotion.trust:.2f})\n"
            f"• Attachment Level: {attach_tier_name} ({affection_val:.2f})\n"
            f"• Blush / Shyness: {shyness_label}\n"
            f"• Curiosity: {curiosity_label}\n"
            f"• Comfort & Havoc Sanctuary: {comfort_label}\n"
            f"• Current Mood: {mood_label}\n"
            "[BEHAVIORAL DIRECTIVE]\n"
            f"{directive}"
        )
