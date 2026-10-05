"""Admission control for LLM-backed chat requests (A-03) and the workload trust boundary.

Daily quotas (UTC day) are charged once per accepted chat request, before any LLM
call, so provider retries inside the gateway never consume extra quota. Counters
are partitioned so abuse of one surface cannot exhaust the others:

* pool ``web_anon``    — global pool + per subject + per client IP
* pool ``web_account`` — global pool + per verified-account subject
* pool ``discord``     — global pool + per Discord subject + per guild (tenant)

Per-IP counters apply to the web only: every Discord request reaches Core from the
bot's single address. A request is admitted only if *every* counter has room, and
then all are incremented atomically. If the quota store is unavailable the request
is refused (fail-closed). A request rejected because the subject already has a chat
in flight (the existing per-subject chat lock) is refunded.

Discord workload credentials are trusted to act for Discord subjects only. Core
refuses a workload principal whose target subject is a registered web account, so
a leaked or misused bot secret cannot read, write or erase web-account state.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.logging.logger import get_logger
from app.shared.utils.user_identity import normalize_user_id

log = get_logger(__name__)

QuotaPool = Literal["web_anon", "web_account", "discord"]
_DAY_SECONDS = 86_400
_COUNTER_TTL_SECONDS = 2 * _DAY_SECONDS


class QuotaExceededError(Exception):
    def __init__(self, scope: str, retry_after: int) -> None:
        super().__init__(scope)
        self.scope = scope
        self.retry_after = retry_after


class QuotaUnavailableError(Exception):
    """The quota store could not be consulted; the request must be refused."""


class WorkloadTargetDeniedError(Exception):
    """A workload principal targeted a registered web account."""


class DailyQuotaStore(Protocol):
    async def consume_daily_quota(self, keys: list[str], limits: list[int], ttl: int) -> int: ...

    async def refund_daily_quota(self, keys: list[str]) -> None: ...


@dataclass(frozen=True, slots=True)
class ChatQuotaLimits:
    web_anon_per_subject: int
    web_anon_per_ip: int
    web_account_per_subject: int
    discord_per_subject: int
    discord_per_guild: int
    pool_web_anon: int
    pool_web_account: int
    pool_discord: int

    @classmethod
    def from_settings(cls, settings: Any) -> ChatQuotaLimits:
        return cls(
            web_anon_per_subject=settings.QUOTA_WEB_ANON_PER_SUBJECT_DAILY,
            web_anon_per_ip=settings.QUOTA_WEB_ANON_PER_IP_DAILY,
            web_account_per_subject=settings.QUOTA_WEB_ACCOUNT_PER_SUBJECT_DAILY,
            discord_per_subject=settings.QUOTA_DISCORD_PER_SUBJECT_DAILY,
            discord_per_guild=settings.QUOTA_DISCORD_PER_GUILD_DAILY,
            pool_web_anon=settings.QUOTA_POOL_WEB_ANON_DAILY,
            pool_web_account=settings.QUOTA_POOL_WEB_ACCOUNT_DAILY,
            pool_discord=settings.QUOTA_POOL_DISCORD_DAILY,
        )


@dataclass(frozen=True, slots=True)
class QuotaReservation:
    keys: tuple[str, ...]


AccountExists = Callable[[Any, uuid.UUID], Awaitable[bool]]


def quota_pool(principal: PrincipalContext) -> QuotaPool:
    if principal.source == "discord":
        return "discord"
    return "web_account" if principal.authentication == "account" else "web_anon"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


class ChatAdmissionControl:
    def __init__(
        self,
        *,
        store: DailyQuotaStore,
        limits: ChatQuotaLimits,
        enabled: bool,
        account_exists: AccountExists,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._limits = limits
        self._enabled = enabled
        self._account_exists = account_exists
        self._clock = clock

    def counters(
        self, principal: PrincipalContext, client_ip: str | None, now: float
    ) -> list[tuple[str, str, int]]:
        """Return (scope, key, limit) for every counter this request must fit in."""
        day = time.strftime("%Y%m%d", time.gmtime(now))
        prefix = f"chisa:quota:v1:{day}"
        pool = quota_pool(principal)
        subject = _digest(str(normalize_user_id(principal.subject_id)))
        limits = self._limits
        if pool == "discord":
            counters = [
                ("pool", f"{prefix}:pool:discord", limits.pool_discord),
                ("subject", f"{prefix}:subject:discord:{subject}", limits.discord_per_subject),
            ]
            if principal.tenant_id:
                counters.append(
                    (
                        "guild",
                        f"{prefix}:guild:{_digest(principal.tenant_id)}",
                        limits.discord_per_guild,
                    )
                )
            return counters
        if pool == "web_account":
            return [
                ("pool", f"{prefix}:pool:web_account", limits.pool_web_account),
                (
                    "subject",
                    f"{prefix}:subject:web_account:{subject}",
                    limits.web_account_per_subject,
                ),
            ]
        counters = [
            ("pool", f"{prefix}:pool:web_anon", limits.pool_web_anon),
            ("subject", f"{prefix}:subject:web_anon:{subject}", limits.web_anon_per_subject),
        ]
        if client_ip:
            counters.append(("ip", f"{prefix}:ip:{_digest(client_ip)}", limits.web_anon_per_ip))
        return counters

    async def admit(
        self, principal: PrincipalContext, client_ip: str | None
    ) -> QuotaReservation | None:
        """Charge one chat against every applicable daily counter, or raise."""
        if not self._enabled:
            return None
        now = self._clock()
        counters = self.counters(principal, client_ip, now)
        keys = [key for _, key, _ in counters]
        try:
            exceeded = await self._store.consume_daily_quota(
                keys, [limit for _, _, limit in counters], _COUNTER_TTL_SECONDS
            )
        except Exception as error:
            log.warning("Chat quota store unavailable; refusing request",
                        error_type=type(error).__name__)
            raise QuotaUnavailableError from error
        if exceeded:
            scope = counters[exceeded - 1][0]
            log.warning("Chat daily quota exceeded", pool=quota_pool(principal), scope=scope)
            raise QuotaExceededError(scope, _seconds_until_next_utc_day(now))
        return QuotaReservation(tuple(keys))

    async def refund(self, reservation: QuotaReservation | None) -> None:
        if reservation is None:
            return
        try:
            await self._store.refund_daily_quota(list(reservation.keys))
        except Exception as error:
            log.warning("Chat quota refund failed", error_type=type(error).__name__)

    async def ensure_workload_target_allowed(
        self, session: Any, principal: PrincipalContext, target_subject: str
    ) -> None:
        """Deny Discord workload access to any registered web account subject."""
        if principal.kind != "workload":
            return
        if await self._account_exists(session, normalize_user_id(target_subject)):
            log.warning("Workload credential targeted a web account; denied")
            raise WorkloadTargetDeniedError


def _seconds_until_next_utc_day(now: float) -> int:
    return max(1, _DAY_SECONDS - int(now) % _DAY_SECONDS)
