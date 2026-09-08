"""Atomic Redis implementation of guild/channel shared state."""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import cast

import redis.asyncio as aioredis

from app.domain.interfaces.community_state import ICommunityStateStore
from app.domain.models.community_state import (
    CommunityMutationResult,
    CommunityStateSnapshot,
    CommunityTurn,
)


class RedisCommunityStateStore(ICommunityStateStore):
    _APPLY_TURN_LUA = """
    if redis.call('SISMEMBER', KEYS[5], ARGV[1]) == 1 then
        return {0, tonumber(redis.call('GET', KEYS[2]) or '0')}
    end
    local buffer = {}
    local raw_buffer = redis.call('GET', KEYS[1])
    if raw_buffer then buffer = cjson.decode(raw_buffer) end
    table.insert(buffer, cjson.decode(ARGV[2]))
    table.insert(buffer, cjson.decode(ARGV[3]))
    local max_messages = tonumber(ARGV[6])
    while #buffer > max_messages do table.remove(buffer, 1) end

    local count = redis.call('INCR', KEYS[2])
    redis.call('SET', KEYS[1], cjson.encode(buffer), 'EX', tonumber(ARGV[5]))
    redis.call('EXPIRE', KEYS[2], tonumber(ARGV[5]))
    redis.call('SADD', KEYS[5], ARGV[1])
    redis.call('EXPIRE', KEYS[5], tonumber(ARGV[5]))

    local channels = {}
    local raw_channels = redis.call('GET', KEYS[4])
    if raw_channels then channels = cjson.decode(raw_channels) end
    local found = false
    for _, channel in ipairs(channels) do
        if channel == ARGV[4] then found = true end
    end
    if not found then table.insert(channels, ARGV[4]) end
    redis.call('SET', KEYS[4], cjson.encode(channels), 'EX', tonumber(ARGV[5]))

    local delta = cjson.decode(ARGV[7])
    local ambient = {
        joy=0.15, sadness=0.0, irritation=0.0, shyness=0.0,
        curiosity=0.10, comfort=0.50
    }
    local ambient_revision = 0
    local raw_ambient = redis.call('GET', KEYS[3])
    if raw_ambient then
        ambient = cjson.decode(raw_ambient)
        ambient_revision = tonumber(ambient['state_revision'] or '0')
    end
    for _, name in ipairs({'joy','sadness','irritation','shyness','curiosity','comfort'}) do
        local raw_name = 'raw_' .. name
        local current_raw = tonumber(ambient[raw_name] or ambient[name])
        local change = tonumber(delta[name] or '0')
        local new_raw = current_raw + change
        ambient[raw_name] = new_raw
        ambient[name] = math.max(0, math.min(1, new_raw))
    end
    ambient['state_revision'] = ambient_revision + 1
    local redis_time = redis.call('TIME')
    ambient['last_updated_at'] = tonumber(redis_time[1])
    redis.call('SET', KEYS[3], cjson.encode(ambient), 'EX', tonumber(ARGV[8]))
    return {1, count}
    """

    _PUBLISH_SUMMARY_LUA = """
    local current = tonumber(redis.call('GET', KEYS[2]) or '0')
    local channel_revision = tonumber(redis.call('GET', KEYS[3]) or '0')
    local incoming = tonumber(ARGV[2])
    if current >= incoming or channel_revision ~= incoming then return 0 end
    redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[3]))
    redis.call('SET', KEYS[2], ARGV[2], 'EX', tonumber(ARGV[3]))
    return 1
    """

    def __init__(
        self,
        client: aioredis.Redis,
        *,
        ttl_seconds: int = 7 * 24 * 3600,
        ambient_ttl_seconds: int = 2 * 3600,
        max_messages: int = 60,
    ) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._ambient_ttl_seconds = ambient_ttl_seconds
        self._max_messages = max_messages

    @staticmethod
    def _prefix(guild_id: str, channel_id: str) -> str:
        return f"chisa:guild:{guild_id}:channel:{channel_id}"

    async def apply_turn(
        self, *, guild_id: str, channel_id: str, turn: CommunityTurn
    ) -> CommunityMutationResult:
        prefix = self._prefix(guild_id, channel_id)
        result = await cast(
            Awaitable[list[int]],
            self._client.eval(
                self._APPLY_TURN_LUA,
                5,
                f"{prefix}:rolling_buffer",
                f"{prefix}:msg_count",
                f"chisa:guild:{guild_id}:ambient_mood",
                f"chisa:guild:{guild_id}:community_channels",
                f"{prefix}:processed_events",
                turn.event_id,
                json.dumps(turn.user_message, ensure_ascii=False),
                json.dumps(turn.assistant_message, ensure_ascii=False),
                channel_id,
                str(self._ttl_seconds),
                str(self._max_messages),
                json.dumps(turn.ambient_delta),
                str(self._ambient_ttl_seconds),
            ),
        )
        applied, count = int(result[0]), int(result[1])
        return CommunityMutationResult(
            applied=bool(applied),
            state_revision=count,
            message_count=count,
        )

    async def snapshot(
        self, *, guild_id: str, channel_id: str
    ) -> CommunityStateSnapshot:
        prefix = self._prefix(guild_id, channel_id)
        values = await cast(
            Awaitable[list[str | None]],
            self._client.mget(
                f"{prefix}:msg_count",
                f"{prefix}:rolling_buffer",
                f"{prefix}:topic_summary",
                f"{prefix}:topic_summary:revision",
            ),
        )
        count = int(values[0] or 0)
        raw_messages = json.loads(values[1]) if values[1] else []
        messages = raw_messages if isinstance(raw_messages, list) else []
        return CommunityStateSnapshot(
            state_revision=count,
            message_count=count,
            messages=messages,
            topic_summary=values[2],
            topic_summary_revision=int(values[3] or 0),
        )

    async def publish_summary(
        self,
        *,
        guild_id: str,
        channel_id: str,
        source_revision: int,
        summary: str,
    ) -> bool:
        prefix = self._prefix(guild_id, channel_id)
        result = await cast(
            Awaitable[int],
            self._client.eval(
                self._PUBLISH_SUMMARY_LUA,
                3,
                f"{prefix}:topic_summary",
                f"{prefix}:topic_summary:revision",
                f"{prefix}:msg_count",
                summary,
                str(source_revision),
                str(self._ttl_seconds),
            ),
        )
        return bool(result)
