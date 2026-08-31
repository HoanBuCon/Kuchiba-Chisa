import time
from typing import List, Optional, Any, Dict
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.services.community.transcript_formatter import ChannelTranscriptFormatter
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

    def __init__(self, llm: BaseLLMAdapter, cache: ICacheProvider):
        self.llm = llm
        self.cache = cache
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

    def _counter_key(self, channel_id: str) -> str:
        return f"chisa:channel:{channel_id}:msg_count"

    def _summary_key(self, channel_id: str) -> str:
        return f"chisa:channel:{channel_id}:topic_summary"

    def _buffer_key(self, channel_id: str) -> str:
        return f"chisa:channel:{channel_id}:rolling_buffer"

    async def increment_message_count(self, channel_id: str) -> int:
        """Increment message counter for the channel in Redis."""
        key = self._counter_key(channel_id)
        try:
            val = await self.cache.get(key)
            count = (int(val) if val else 0) + 1
            await self.cache.set(key, str(count), ttl=self.SUMMARY_TTL_SECONDS)
            return count
        except Exception as e:
            log.warning("Failed to increment channel message counter in Redis", channel_id=channel_id, error=str(e))
            return 1

    async def get_topic_summary(self, channel_id: str) -> Optional[str]:
        """Fetch active topic summary from Redis."""
        if not channel_id:
            return None
        key = self._summary_key(channel_id)
        try:
            summary = await self.cache.get(key)
            return summary.strip() if summary else None
        except Exception as e:
            log.warning("Failed to fetch channel topic summary from Redis", channel_id=channel_id, error=str(e))
            return None

    async def get_rolling_buffer(self, channel_id: str) -> List[Dict[str, Any]]:
        """Fetch accumulated rolling message buffer from Redis."""
        if not channel_id:
            return []
        try:
            buf = await self.cache.get_json(self._buffer_key(channel_id))
            return buf if isinstance(buf, list) else []
        except Exception as e:
            log.warning("Failed to fetch channel rolling buffer from Redis", channel_id=channel_id, error=str(e))
            return []

    async def append_messages(
        self,
        channel_id: str,
        messages: Optional[List[Any]] = None,
        current_user_turn: Optional[Dict[str, Any]] = None,
        current_assistant_turn: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Appends new channel messages and the current conversation turn to the Redis Rolling Buffer.
        Deduplicates messages and caps buffer to BUFFER_MAX_MESSAGES.
        """
        if not channel_id:
            return

        try:
            buffer: List[Dict[str, Any]] = await self.get_rolling_buffer(channel_id)

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
                    sig = _msg_sig(m)
                    if sig[1] and sig not in seen_sigs:
                        if isinstance(m, dict):
                            buffer.append({
                                "speaker_name": m.get("speaker_name", "User"),
                                "content": m.get("content", ""),
                                "is_bot": bool(m.get("is_bot", False)),
                                "created_at": m.get("created_at"),
                                "reply_to_speaker": m.get("reply_to_speaker"),
                            })
                        else:
                            buffer.append({
                                "speaker_name": getattr(m, "speaker_name", "User"),
                                "content": getattr(m, "content", ""),
                                "is_bot": bool(getattr(m, "is_bot", False)),
                                "created_at": getattr(m, "created_at", None),
                                "reply_to_speaker": getattr(m, "reply_to_speaker", None),
                            })
                        seen_sigs.add(sig)

            if current_user_turn and current_user_turn.get("content"):
                sig = _msg_sig(current_user_turn)
                if sig not in seen_sigs:
                    buffer.append(current_user_turn)
                    seen_sigs.add(sig)

            if current_assistant_turn and current_assistant_turn.get("content"):
                sig = _msg_sig(current_assistant_turn)
                if sig not in seen_sigs:
                    buffer.append(current_assistant_turn)
                    seen_sigs.add(sig)

            if len(buffer) > self.BUFFER_MAX_MESSAGES:
                buffer = buffer[-self.BUFFER_MAX_MESSAGES:]

            await self.cache.set_json(self._buffer_key(channel_id), buffer, ttl=self.SUMMARY_TTL_SECONDS)
        except Exception as e:
            log.warning("Failed to append messages to Redis rolling buffer", channel_id=channel_id, error=str(e))

    async def summarize_channel_topic(
        self,
        channel_id: str,
        guild_id: str,
        messages: Optional[List[Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Background execution: Calls LLM to summarize accumulated rolling discussion buffer, merging with prior summary.
        """
        rolling_buffer = await self.get_rolling_buffer(channel_id)
        effective_messages = rolling_buffer if rolling_buffer else (messages or [])

        if not effective_messages:
            return None

        log.info(
            "Starting community topic summarization with rolling buffer...",
            channel_id=channel_id,
            guild_id=guild_id,
            message_count=len(effective_messages),
        )
        formatted_transcript = ChannelTranscriptFormatter.format_transcript(
            messages=effective_messages,
            max_tokens=1200,
            use_smart_compression=True
        )

        if not formatted_transcript:
            return None

        previous_summary = await self.get_topic_summary(channel_id)

        if previous_summary:
            system_prompt = (
                "You are a Community Topic Summarizer for an anime AI Companion (Kuchiba Chisa) in a Discord Server.\n"
                "Your job is to UPDATE the rolling channel discussion summary by integrating new conversation messages into the previous summary.\n\n"
                "CRITICAL RULES:\n"
                "1. Output a standalone, concise narrative in Vietnamese (50-80 words) describing: what members are discussing, shared gaming/life events, or group plans.\n"
                "2. Retain important ongoing context from the previous summary while prioritizing newest discussions.\n"
                "3. Do not include individual timestamps or roleplay metadata. Focus on group topics.\n"
                "Return valid JSON matching schema: {\"topic_summary\": \"...\"}"
            )
            user_message = f"Previous summary:\n{previous_summary}\n\nNew recent channel messages:\n{formatted_transcript}"
        else:
            system_prompt = (
                "You are a Community Topic Summarizer for an anime AI Companion (Kuchiba Chisa) in a Discord Server.\n"
                "Analyze the channel discussion transcript and provide a concise narrative summary in Vietnamese (50-80 words).\n\n"
                "CRITICAL RULES:\n"
                "1. Summarize the key topics members are discussing, any ongoing banter, game matches, or server plans.\n"
                "2. Output must be a clear, standalone paragraph in Vietnamese.\n"
                "Return valid JSON matching schema: {\"topic_summary\": \"...\"}"
            )
            user_message = f"Channel messages transcript:\n{formatted_transcript}"

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
            summary_text = str(parsed.get("topic_summary", "")).strip()

            if summary_text:
                await self.cache.set(
                    self._summary_key(channel_id),
                    summary_text,
                    ttl=self.SUMMARY_TTL_SECONDS
                )
                
                # Trim rolling buffer to retain last BUFFER_OVERLAP_MESSAGES for subsequent continuity
                if rolling_buffer and len(rolling_buffer) > self.BUFFER_OVERLAP_MESSAGES:
                    trimmed = rolling_buffer[-self.BUFFER_OVERLAP_MESSAGES:]
                    await self.cache.set_json(self._buffer_key(channel_id), trimmed, ttl=self.SUMMARY_TTL_SECONDS)

                log.info("Community topic summary updated in Redis", channel_id=channel_id, summary_length=len(summary_text))
                self._record_pipeline_step(
                    status="success",
                    topic_summary=summary_text,
                    channel_id=channel_id,
                    previous_summary=previous_summary,
                    transcript_sample=formatted_transcript[:300],
                    trace_id=trace_id
                )
                return summary_text
            else:
                log.warning("Topic summarizer produced empty summary", channel_id=channel_id)
                self._record_pipeline_step(
                    status="empty",
                    topic_summary="",
                    channel_id=channel_id,
                    previous_summary=previous_summary,
                    transcript_sample=formatted_transcript[:300],
                    trace_id=trace_id
                )
                return None
        except Exception as e:
            log.error("Failed to summarize community topic", channel_id=channel_id, error=str(e))
            self._record_pipeline_step(
                status="failed",
                topic_summary="",
                channel_id=channel_id,
                previous_summary=previous_summary,
                transcript_sample=formatted_transcript[:300],
                trace_id=trace_id
            )
            return None

    def _record_pipeline_step(
        self,
        status: str,
        topic_summary: str,
        channel_id: str,
        previous_summary: Optional[str] = None,
        transcript_sample: str = "",
        trace_id: Optional[str] = None
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
