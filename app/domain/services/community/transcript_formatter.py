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

    BOT_COMMAND_PREFIXES = ("!", "c!", "/", ".", "$", "%", "++", ";;", "-")
    KNOWN_BOT_COMMANDS = {
        "!play", "!skip", "!p", "!stop", "!queue", "!loop", "!nowplaying", "!np",
        "!rank", "!level", "!profile", "!daily", "!rep", "!help", "c!help", "c!setup",
        "c!docs", "!ping", "!ban", "!kick", "!mute", "!clear", "!purge"
    }

    @classmethod
    def is_noise_or_command(cls, content: str) -> bool:
        """Check if message is a bot command, bot invocation, or pure spam noise."""
        if not content:
            return True
        stripped = content.strip()
        if not stripped:
            return True
            
        first_word = stripped.split()[0].lower()
        if first_word in cls.KNOWN_BOT_COMMANDS:
            return True
            
        # Check prefixes for commands with length > 1
        if any(stripped.startswith(prefix) for prefix in cls.BOT_COMMAND_PREFIXES) and len(stripped) > 1:
            # Exclude regular single-punctuation or emoji
            if not stripped.startswith("...") and not stripped.startswith("?!"):
                return True

        return False

    @staticmethod
    def format_message(msg: Any) -> str:
        """Format a single message turn with timestamp, speaker and reply context."""
        if isinstance(msg, dict):
            created_at = msg.get("created_at")
            speaker_name = msg.get("speaker_name", "User")
            reply_to_speaker = msg.get("reply_to_speaker")
            content = msg.get("content", "")
        else:
            created_at = getattr(msg, "created_at", None)
            speaker_name = getattr(msg, "speaker_name", "User")
            reply_to_speaker = getattr(msg, "reply_to_speaker", None)
            content = getattr(msg, "content", "")

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
            content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
            if cls.is_noise_or_command(content):
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
                content = m.get("content", "").strip()
                created_at = m.get("created_at")
            else:
                speaker = getattr(m, "speaker_name", "User")
                reply_to = getattr(m, "reply_to_speaker", None)
                content = getattr(m, "content", "").strip()
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
