import re
from typing import List, Optional, Any, Tuple, Dict
from app.domain.entities.community import CommunityMessage
from app.domain.services.context_budget_manager import TokenEstimator


class ChannelTranscriptFormatter:
    """
    Formats multi-user community chat messages into a structured,
    speaker-aware dialogue transcript for LLM context injection.
    Features Smart Compression (bot command filtering, message coalescing, noise trimming).
    """

    BOT_COMMAND_PREFIXES = ("c!", "!", "/", "$", "%", "++", ";;", "-", "?", ".", "~", "&", ">")
    KNOWN_BOT_COMMANDS = {
        "!play", "!skip", "!p", "!stop", "!queue", "!loop", "!nowplaying", "!np",
        "!rank", "!level", "!profile", "!daily", "!rep", "!help", "c!help", "c!setup",
        "c!docs", "!ping", "!ban", "!kick", "!mute", "!clear", "!purge", "m!help", "p!help"
    }

    SYSTEM_ANNOUNCEMENT_KEYWORDS = (
        "nuke server",
        "đã xóa ký ức",
        "toàn bộ ký ức",
        "chỉ số cảm xúc",
        "mốc thời gian ngắt",
        "cutoff",
        "bảng hướng dẫn",
        "hướng dẫn sử dụng",
        "danh sách lệnh",
        "thiết lập kênh",
        "đã thiết lập thành công",
        "cổng kết nối tại các kênh",
        "xin lỗi senpai, chisa không thể trả lời lúc này",
        "bạn đang gửi quá nhanh",
        "chisa chưa tạo được phản hồi",
        "chisa sẽ xem toàn bộ server",
        "dùng c!ask",
        "dùng /ask",
        "yêu cầu quyền quản trị",
        "tùy chọn mode:",
        "quyền admin/mod",
    )

    @classmethod
    def clean_message_content(cls, content: str) -> str:
        """Strip emotion breakdown blocks and trailing codeblocks from past bot messages."""
        if not content:
            return ""
        # 1. Remove **[Trạng thái Cảm xúc]** / **[Emotion State]** and everything after it
        cleaned = re.sub(r"\*\*\[(?:Trạng thái Cảm xúc|Emotion State)\]\*\*[\s\S]*", "", content, flags=re.IGNORECASE)
        # 2. Remove isolated emotion codeblocks
        cleaned = re.sub(r"```[\s\S]*?(?:Tin tưởng|Trust|Attachment|Gắn bó|Hiếu kỳ|Bình yên)[\s\S]*?```", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    @classmethod
    def is_noise_or_command(cls, content: str, is_bot: bool = False, speaker_name: str = "") -> bool:
        """Check if message is a bot command, third-party bot message, system notice, or pure spam noise."""
        if not content:
            return True
        stripped = cls.clean_message_content(content).strip()
        if not stripped:
            return True

        # 1. Exclude third-party bots completely (only allow human members or Chisa)
        spk_lower = speaker_name.lower().strip() if speaker_name else ""
        if is_bot and spk_lower not in ("chisa", "kuchiba chisa", "assistant"):
            return True

        lower = stripped.lower()

        # 2. Exclude system notices and command announcement templates of Chisa
        if any(keyword in lower for keyword in cls.SYSTEM_ANNOUNCEMENT_KEYWORDS):
            return True

        # 3. Exclude messages starting with command banner markers or emojis
        if any(stripped.startswith(sym) for sym in ("💥", "🧹", "ℹ️", "⚙️", "🚫", "⏳", "❌", "☢️", "🔒", "🌐", "**NUKE", "**ĐÃ XÓA", "**BẢNG")):
            return True

        first_word = stripped.split()[0].lower()
        if first_word in cls.KNOWN_BOT_COMMANDS:
            return True

        # 4. Check prefixes for user commands (e.g. c!clear, !play, /ask, $command)
        if any(stripped.startswith(prefix) for prefix in cls.BOT_COMMAND_PREFIXES) and len(stripped) > 1:
            # Exclude regular single-punctuation or emoji
            if not stripped.startswith("...") and not stripped.startswith("?!"):
                return True

        return False

    @classmethod
    def format_message(cls, msg: Any) -> str:
        """Format a single message turn with timestamp, speaker and reply context."""
        if isinstance(msg, dict):
            created_at = msg.get("created_at")
            speaker_name = msg.get("speaker_name", "User")
            reply_to_speaker = msg.get("reply_to_speaker")
            raw_content = msg.get("content", "")
        else:
            created_at = getattr(msg, "created_at", None)
            speaker_name = getattr(msg, "speaker_name", "User")
            reply_to_speaker = getattr(msg, "reply_to_speaker", None)
            raw_content = getattr(msg, "content", "")

        content = cls.clean_message_content(raw_content)

        time_str = "Now"
        if created_at:
            if hasattr(created_at, "strftime"):
                time_str = created_at.strftime("%H:%M")
            elif isinstance(created_at, str):
                time_str = created_at[-8:-3] if len(created_at) >= 8 and ":" in created_at else created_at[:5]

        speaker_tag = f"<{speaker_name}>"

        reply_info = ""
        if reply_to_speaker:
            reply_info = f" [Replying to @{reply_to_speaker}]"

        return f"[{time_str}] {speaker_tag}{reply_info}: {content}"

    @classmethod
    def compress_messages(cls, messages: List[Any]) -> Tuple[List[str], Dict[str, Any]]:
        """
        Compresses raw messages by:
        1. Filtering bot commands and spam.
        2. Coalescing consecutive messages from the same speaker.
        """
        if not messages:
            return [], {"raw_count": 0, "compressed_count": 0, "filtered_commands": 0}

        cleaned_msgs = []
        filtered_commands = 0

        for m in messages:
            if isinstance(m, dict):
                content = m.get("content", "")
                is_bot = bool(m.get("is_bot", False))
                speaker_name = m.get("speaker_name", "")
            else:
                content = getattr(m, "content", "")
                is_bot = bool(getattr(m, "is_bot", False))
                speaker_name = getattr(m, "speaker_name", "")

            if cls.is_noise_or_command(content, is_bot=is_bot, speaker_name=speaker_name):
                filtered_commands += 1
                continue
            cleaned_msgs.append(m)

        if not cleaned_msgs:
            return [], {"raw_count": len(messages), "compressed_count": 0, "filtered_commands": filtered_commands}

        # Coalesce consecutive messages from the same speaker
        coalesced_lines: List[str] = []
        curr_speaker = None
        curr_reply = None
        curr_time = "Now"
        curr_contents: List[str] = []

        for m in cleaned_msgs:
            if isinstance(m, dict):
                speaker = m.get("speaker_name", "User")
                reply_to = m.get("reply_to_speaker")
                content = cls.clean_message_content(m.get("content", ""))
                created_at = m.get("created_at")
            else:
                speaker = getattr(m, "speaker_name", "User")
                reply_to = getattr(m, "reply_to_speaker", None)
                content = cls.clean_message_content(getattr(m, "content", ""))
                created_at = getattr(m, "created_at", None)
                created_at = getattr(m, "created_at", None)

            time_str = "Now"
            if created_at:
                if hasattr(created_at, "strftime"):
                    time_str = created_at.strftime("%H:%M")
                elif isinstance(created_at, str):
                    time_str = created_at[-8:-3] if len(created_at) >= 8 and ":" in created_at else created_at[:5]

            # If same speaker and same reply target, merge content
            if speaker == curr_speaker and reply_to == curr_reply:
                curr_contents.append(content)
            else:
                if curr_speaker is not None:
                    reply_tag = f" [Replying to @{curr_reply}]" if curr_reply else ""
                    merged_text = "\n  ".join(curr_contents)
                    coalesced_lines.append(f"[{curr_time}] <{curr_speaker}>{reply_tag}: {merged_text}")

                curr_speaker = speaker
                curr_reply = reply_to
                curr_time = time_str
                curr_contents = [content]

        if curr_speaker is not None:
            reply_tag = f" [Replying to @{curr_reply}]" if curr_reply else ""
            merged_text = "\n  ".join(curr_contents)
            coalesced_lines.append(f"[{curr_time}] <{curr_speaker}>{reply_tag}: {merged_text}")

        stats = {
            "raw_count": len(messages),
            "compressed_count": len(coalesced_lines),
            "filtered_commands": filtered_commands
        }
        return coalesced_lines, stats

    @classmethod
    def format_transcript(
        cls,
        messages: List[Any],
        max_tokens: int = 1200,
        token_estimator: Optional[TokenEstimator] = None,
        use_smart_compression: bool = True,
    ) -> str:
        """
        Format a sequence of community messages into a rolling transcript,
        trimming from the oldest turns if exceeding the token budget.
        """
        if not messages:
            return ""

        estimator = token_estimator or TokenEstimator

        if use_smart_compression:
            formatted_lines, _ = cls.compress_messages(messages)
        else:
            formatted_lines = [cls.format_message(m) for m in messages]

        if not formatted_lines:
            return ""

        # Check total tokens and trim oldest messages if necessary
        full_text = "\n".join(formatted_lines)
        if estimator.estimate(full_text) <= max_tokens:
            return full_text

        # Trim oldest turns while preserving newest turns
        trimmed_lines: List[str] = []
        running_token_count = 0

        for line in reversed(formatted_lines):
            line_tokens = estimator.estimate(line + "\n")
            if running_token_count + line_tokens > max_tokens:
                break
            trimmed_lines.insert(0, line)
            running_token_count += line_tokens

        return "\n".join(trimmed_lines)
