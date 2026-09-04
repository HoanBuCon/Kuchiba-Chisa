from typing import Any

from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.services.community.transcript_formatter import ChannelTranscriptFormatter
from app.domain.services.guardrails.pii_redaction import PiiRedactor
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class CommunityTopicSummarizer:
    """
    Background worker that maintains a rolling topic summary for community channels in Redis.
    Triggered every 30 messages in a community channel to preserve multi-turn discussion context.
    """

    SUMMARY_TTL_SECONDS = 7 * 24 * 3600  # 7 days
    BUFFER_MAX_MESSAGES = 60
    BUFFER_OVERLAP_MESSAGES = 10
    SUMMARIZE_INTERVAL = 30

    def __init__(
        self, llm: BaseLLMAdapter, cache: ICacheProvider, pii_redactor: PiiRedactor | None = None
    ):
        self.llm = llm
        self.cache = cache
        self.pii_redactor = pii_redactor or PiiRedactor()
        self.SUMMARY_SCHEMA = {
            "type": "object",
            "properties": {
                "topic_summary": {
                    "type": "string",
                    "description": "Concise standalone narrative summary in Vietnamese describing key topics, group decisions, and recent channel dynamics (50-80 words)."
                }
            },
            "required": ["topic_summary"]
        }

    @staticmethod
    def _channel_prefix(channel_id: str, guild_id: str | None = None) -> str:
        if guild_id:
            return f"chisa:guild:{guild_id}:channel:{channel_id}"
        return f"chisa:channel:{channel_id}"

    @classmethod
    def summary_cache_key(cls, channel_id: str, guild_id: str | None = None) -> str:
        return f"{cls._channel_prefix(channel_id, guild_id)}:topic_summary"

    def _counter_key(self, channel_id: str, guild_id: str | None = None) -> str:
        return f"{self._channel_prefix(channel_id, guild_id)}:msg_count"

    def _summary_key(self, channel_id: str, guild_id: str | None = None) -> str:
        return self.summary_cache_key(channel_id, guild_id)

    def _buffer_key(self, channel_id: str, guild_id: str | None = None) -> str:
        return f"{self._channel_prefix(channel_id, guild_id)}:rolling_buffer"

    @staticmethod
    def _channel_index_key(guild_id: str) -> str:
        return f"chisa:guild:{guild_id}:community_channels"

    async def increment_message_count(self, channel_id: str, guild_id: str | None = None) -> int:
        """Increment message counter for the channel in Redis."""
        key = self._counter_key(channel_id, guild_id)
        try:
            val = await self.cache.get(key)
            count = (int(val) if val else 0) + 1
            await self.cache.set(key, str(count), ttl=self.SUMMARY_TTL_SECONDS)
            return count
        except Exception as e:
            log.warning("Failed to increment channel message counter in Redis", channel_id=channel_id, error=str(e))
            return 1

    async def get_topic_summary(
        self, channel_id: str, guild_id: str | None = None
    ) -> str | None:
        """Fetch active topic summary from Redis."""
        if not channel_id:
            return None
        key = self._summary_key(channel_id, guild_id)
        try:
            summary = await self.cache.get(key)
            return summary.strip() if summary else None
        except Exception as e:
            log.warning("Failed to fetch channel topic summary from Redis", channel_id=channel_id, error=str(e))
            return None

    async def get_rolling_buffer(
        self, channel_id: str, guild_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch accumulated rolling message buffer from Redis."""
        if not channel_id:
            return []
        try:
            buf = await self.cache.get_json(self._buffer_key(channel_id, guild_id))
            return buf if isinstance(buf, list) else []
        except Exception as e:
            log.warning("Failed to fetch channel rolling buffer from Redis", channel_id=channel_id, error=str(e))
            return []

    async def append_messages(
        self,
        channel_id: str,
        messages: list[Any] | None = None,
        current_user_turn: dict[str, Any] | None = None,
        current_assistant_turn: dict[str, Any] | None = None,
        guild_id: str | None = None,
    ) -> None:
        """
        Appends new channel messages and the current conversation turn to the Redis Rolling Buffer.
        Deduplicates messages and caps buffer to BUFFER_MAX_MESSAGES.
        """
        if not channel_id:
            return

        try:
            buffer: list[dict[str, Any]] = await self.get_rolling_buffer(channel_id, guild_id)

            def _msg_sig(m: Any) -> tuple:
                if isinstance(m, dict):
                    spk = m.get("speaker_name", "")
                    content = (m.get("content", "") or "").strip()
                    created = str(m.get("created_at", ""))
                    return (spk, content, created)
                spk = getattr(m, "speaker_name", "")
                content = (getattr(m, "content", "") or "").strip()
                created = str(getattr(m, "created_at", ""))
                return (spk, content, created)

            seen_sigs = set(_msg_sig(m) for m in buffer)

            if messages:
                for m in messages:
                    raw_content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
                    is_bot = bool(m.get("is_bot", False)) if isinstance(m, dict) else bool(getattr(m, "is_bot", False))
                    speaker_name = m.get("speaker_name", "") if isinstance(m, dict) else getattr(m, "speaker_name", "")

                    # 1. Pre-filter bot commands, third-party bots, and spam noise
                    if ChannelTranscriptFormatter.is_noise_or_command(raw_content, is_bot=is_bot, speaker_name=speaker_name):
                        continue

                    sig = _msg_sig(m)
                    if sig[1] and sig not in seen_sigs:
                        clean_content = ChannelTranscriptFormatter.clean_message_content(raw_content)
                        clean_content = self.pii_redactor.redact(clean_content).value
                        if not clean_content:
                            continue
                        if isinstance(m, dict):
                            buffer.append({
                                "speaker_name": m.get("speaker_name", "User"),
                                "content": clean_content,
                                "is_bot": is_bot,
                                "created_at": m.get("created_at"),
                                "reply_to_speaker": m.get("reply_to_speaker"),
                            })
                        else:
                            buffer.append({
                                "speaker_name": getattr(m, "speaker_name", "User"),
                                "content": clean_content,
                                "is_bot": is_bot,
                                "created_at": getattr(m, "created_at", None),
                                "reply_to_speaker": getattr(m, "reply_to_speaker", None),
                            })
                        seen_sigs.add(sig)

            if current_user_turn and current_user_turn.get("content"):
                user_content = current_user_turn.get("content", "")
                if not ChannelTranscriptFormatter.is_noise_or_command(user_content, is_bot=False, speaker_name=current_user_turn.get("speaker_name", "User")):
                    sig = _msg_sig(current_user_turn)
                    if sig not in seen_sigs:
                        sanitized_user_turn = dict(current_user_turn)
                        sanitized_user_turn["content"] = self.pii_redactor.redact(
                            user_content
                        ).value
                        buffer.append(sanitized_user_turn)
                        seen_sigs.add(sig)

            if current_assistant_turn and current_assistant_turn.get("content"):
                asst_content = ChannelTranscriptFormatter.clean_message_content(current_assistant_turn.get("content", ""))
                if asst_content:
                    asst_turn = dict(current_assistant_turn)
                    asst_turn["content"] = self.pii_redactor.redact(asst_content).value
                    sig = _msg_sig(asst_turn)
                    if sig not in seen_sigs:
                        buffer.append(asst_turn)
                        seen_sigs.add(sig)

            if len(buffer) > self.BUFFER_MAX_MESSAGES:
                buffer = buffer[-self.BUFFER_MAX_MESSAGES:]

            await self.cache.set_json(
                self._buffer_key(channel_id, guild_id), buffer, ttl=self.SUMMARY_TTL_SECONDS
            )
            if guild_id:
                index_key = self._channel_index_key(guild_id)
                known_channels = await self.cache.get_json(index_key)
                channel_ids = known_channels if isinstance(known_channels, list) else []
                if channel_id not in channel_ids:
                    await self.cache.set_json(
                        index_key,
                        [*channel_ids, channel_id],
                        ttl=self.SUMMARY_TTL_SECONDS,
                    )
        except Exception as e:
            log.warning("Failed to append messages to Redis rolling buffer", channel_id=channel_id, error=str(e))

    async def summarize_channel_topic(
        self,
        channel_id: str,
        guild_id: str,
        messages: list[Any] | None = None,
        trace_id: str | None = None,
    ) -> str | None:
        """
        Background execution: Calls LLM to summarize channel topic with 3-tier context:
        1. Previous Topic Summary (Redis)
        2. Accumulated History Buffer (Redis Rolling Buffer)
        3. Live Recent Channel Messages (15 raw Discord messages)
        """
        rolling_buffer = await self.get_rolling_buffer(channel_id, guild_id)
        live_messages = messages or []

        if not rolling_buffer and not live_messages:
            return None

        # Separate older history from newest live messages to avoid redundant duplication in prompt
        live_count = len(live_messages) if live_messages else 0
        if rolling_buffer and live_count > 0 and len(rolling_buffer) > live_count:
            older_history_messages = rolling_buffer[:-live_count]
        elif rolling_buffer and not live_messages:
            older_history_messages = rolling_buffer
        else:
            older_history_messages = []

        # 1. Format Live Recent Transcript (Hot Context)
        formatted_live_transcript = ChannelTranscriptFormatter.format_transcript(
            messages=live_messages if live_messages else rolling_buffer,
            max_tokens=600,
            use_smart_compression=True
        )

        # 2. Format Accumulated History Buffer (Deep Context)
        formatted_history_transcript = ""
        if older_history_messages:
            formatted_history_transcript = ChannelTranscriptFormatter.format_transcript(
                messages=older_history_messages,
                max_tokens=800,
                use_smart_compression=True
            )

        if not formatted_live_transcript and not formatted_history_transcript:
            return None

        # 3. Fetch Previous Summary from Redis
        previous_summary = await self.get_topic_summary(channel_id, guild_id)

        # Build 3-Tier User Message Sections
        sections = []
        if previous_summary:
            sections.append(f"1. Previous topic summary (Bản tóm tắt chu kỳ trước):\n{previous_summary}")

        if formatted_history_transcript:
            sections.append(f"2. Accumulated channel history buffer (Lịch sử các đoạn thảo luận trước đó trong chu kỳ):\n{formatted_history_transcript}")

        if formatted_live_transcript:
            sections.append(f"3. Live recent channel context (Diễn biến 15 tin nhắn nóng hổi nhất hiện tại):\n{formatted_live_transcript}")

        user_message = "\n\n".join(sections)

        system_prompt = (
            "You are a Community Topic Summarizer for an anime AI Companion (Kuchiba Chisa) in a Discord Server.\n"
            "Your job is to synthesize a complete rolling channel discussion summary by integrating:\n"
            "1. The previous topic summary (if available).\n"
            "2. The accumulated history buffer of past discussions in this cycle.\n"
            "3. The latest live recent channel messages.\n\n"
            "CRITICAL RULES:\n"
            "1. Output a standalone, concise narrative in Vietnamese (50-80 words) describing: what members are discussing, shared gaming/life events, or group plans.\n"
            "2. Synthesize ongoing context across history while prioritizing the newest live discussions.\n"
            "3. Do not include individual timestamps or roleplay metadata. Focus on group topics.\n"
            "Return valid JSON matching schema: {\"topic_summary\": \"...\"}"
        )

        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=user_message,
            response_schema=self.SUMMARY_SCHEMA,
            temperature=0.3,
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={"use_deep_thinking": False}
        )

        try:
            from app.domain.context import llm_call_purpose
            llm_call_purpose.set("community_topic_summarize")
            response = await self.llm.generate(prompt)
            parsed = response.parsed or {}
            summary_text = self.pii_redactor.redact(
                str(parsed.get("topic_summary", "")).strip()
            ).value

            if summary_text:
                await self.cache.set(
                    self._summary_key(channel_id, guild_id),
                    summary_text,
                    ttl=self.SUMMARY_TTL_SECONDS
                )
                
                # Trim rolling buffer to retain last BUFFER_OVERLAP_MESSAGES for subsequent continuity
                if rolling_buffer and len(rolling_buffer) > self.BUFFER_OVERLAP_MESSAGES:
                    trimmed = rolling_buffer[-self.BUFFER_OVERLAP_MESSAGES:]
                    await self.cache.set_json(
                        self._buffer_key(channel_id, guild_id),
                        trimmed,
                        ttl=self.SUMMARY_TTL_SECONDS,
                    )

                sample_transcript = (formatted_live_transcript or formatted_history_transcript)[:300]
                log.info("Community topic summary updated in Redis", channel_id=channel_id, summary_length=len(summary_text))
                self._record_pipeline_step(
                    status="success",
                    topic_summary=summary_text,
                    channel_id=channel_id,
                    previous_summary=previous_summary,
                    transcript_sample=sample_transcript,
                    trace_id=trace_id
                )
                return summary_text
            else:
                sample_transcript = (formatted_live_transcript or formatted_history_transcript)[:300]
                log.warning("Topic summarizer produced empty summary", channel_id=channel_id)
                self._record_pipeline_step(
                    status="empty",
                    topic_summary="",
                    channel_id=channel_id,
                    previous_summary=previous_summary,
                    transcript_sample=sample_transcript,
                    trace_id=trace_id
                )
                return None
        except Exception as e:
            sample_transcript = (formatted_live_transcript or formatted_history_transcript)[:300] if 'formatted_live_transcript' in locals() else ""
            log.error("Failed to summarize community topic", channel_id=channel_id, error=str(e))
            self._record_pipeline_step(
                status="failed",
                topic_summary="",
                channel_id=channel_id,
                previous_summary=previous_summary,
                transcript_sample=sample_transcript,
                trace_id=trace_id
            )
            return None

    def _record_pipeline_step(
        self,
        status: str,
        topic_summary: str,
        channel_id: str,
        previous_summary: str | None = None,
        transcript_sample: str = "",
        trace_id: str | None = None
    ) -> None:
        try:
            from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
            word_count = len(topic_summary.split()) if topic_summary else 0
            pipeline_tracker.add_step(
                name="summarize_channel_topic",
                stage_id="stage_10_bg",
                depth=1,
                category="task",
                title="10.2 [BG] Tóm tắt Mạch Kênh Cộng đồng",
                subtitle=f"{word_count} từ tóm tắt ({status})",
                trace_id=trace_id,
                data={
                    "status": status,
                    "channel_id": channel_id,
                    "topic_summary": topic_summary,
                    "previous_summary": previous_summary,
                    "transcript_sample": transcript_sample,
                    "word_count": word_count,
                }
            )
        except Exception:
            pass
