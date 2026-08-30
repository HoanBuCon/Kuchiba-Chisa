from typing import List, Optional, Any
from app.domain.entities.community import CommunityMessage
from app.domain.services.context_budget_manager import TokenEstimator


class ChannelTranscriptFormatter:
    """
    Formats multi-user community chat messages into a structured,
    speaker-aware dialogue transcript for LLM context injection.
    """

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
    def format_transcript(
        cls,
        messages: List[CommunityMessage],
        max_tokens: int = 1200,
        token_estimator: Optional[TokenEstimator] = None,
    ) -> str:
        """
        Format a sequence of community messages into a rolling transcript,
        trimming from the oldest turns if exceeding the token budget.
        """
        if not messages:
            return ""

        estimator = token_estimator or TokenEstimator
        formatted_lines = [cls.format_message(m) for m in messages]

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
