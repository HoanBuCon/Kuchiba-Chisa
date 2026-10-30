"""Compose and deliver account e-mails (verification, password reset, claim).

Links carry the secret in the URL *fragment* (``#verify-email=…``): browsers never
send fragments to servers or in ``Referer`` headers, so the token cannot leak into
proxy/access logs or third-party requests. The SPA reads and removes it, then POSTs
it to the API.

Delivery is bounded by an application-wide daily ceiling kept in Redis. If that
counter is unavailable the e-mail is not sent (fail-closed); the per-account
cooldown still lets the user retry later. Tokens and addresses are never logged.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.domain.interfaces.accounts import IEmailSender
from app.domain.models.account import OutboundAccountEmail
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

_SUBJECTS = {
    "verify_email": "Chisa — Xác minh email của bạn",
    "password_reset": "Chisa — Đặt lại mật khẩu",
    "existing_account": "Chisa — Email này đã có tài khoản",
    "claim_account": "Chisa — Xác nhận quyền sở hữu email",
}

_BODIES = {
    "verify_email": (
        "Chào bạn,\n\nCó người vừa tạo tài khoản Chisa bằng email này. Nếu đó là bạn, "
        "hãy mở liên kết dưới đây trong {hours} giờ để xác minh email:\n\n{link}\n\n"
        "Nếu bạn không đăng ký, đừng mở liên kết; tài khoản sẽ không dùng được."
    ),
    "password_reset": (
        "Chào bạn,\n\nCó yêu cầu đặt lại mật khẩu Chisa cho email này. Liên kết dưới "
        "đây chỉ dùng được một lần, trong {minutes} phút:\n\n{link}\n\n"
        "Đặt lại mật khẩu sẽ đăng xuất mọi thiết bị. Nếu bạn không yêu cầu, hãy bỏ qua."
    ),
    "existing_account": (
        "Chào bạn,\n\nCó người vừa thử đăng ký Chisa bằng email này, nhưng email đã có "
        "tài khoản. Nếu đó là bạn và bạn quên mật khẩu, hãy đặt mật khẩu mới trong "
        "{minutes} phút bằng liên kết:\n\n{link}\n\nNếu không, hãy bỏ qua email này."
    ),
    "claim_account": (
        "Chào bạn,\n\nEmail này đang gắn với một tài khoản Chisa chưa được xác minh. "
        "Nếu bạn là chủ email, hãy đặt mật khẩu của riêng bạn trong {minutes} phút "
        "bằng liên kết dưới đây. Việc này xác minh email, thay mật khẩu cũ và đăng "
        "xuất mọi phiên:\n\n{link}\n\nNếu bạn không yêu cầu, hãy bỏ qua email này."
    ),
}

_FRAGMENTS = {
    "verify_email": "verify-email",
    "password_reset": "reset-password",
    "existing_account": "reset-password",
    "claim_account": "reset-password",
}

DailyCounter = Callable[[str, int], Awaitable[int]]


def account_email_link(public_app_url: str, outbound: OutboundAccountEmail) -> str:
    return f"{public_app_url.rstrip('/')}/#{_FRAGMENTS[outbound.kind]}={outbound.token}"


class AccountEmailDispatcher:
    def __init__(
        self,
        *,
        sender: IEmailSender,
        public_app_url: str,
        daily_counter: DailyCounter,
        daily_limit: int,
        verification_ttl_hours: int,
        reset_ttl_minutes: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sender = sender
        self._public_app_url = public_app_url
        self._daily_counter = daily_counter
        self._daily_limit = daily_limit
        self._hours = verification_ttl_hours
        self._minutes = reset_ttl_minutes
        self._clock = clock

    @property
    def enabled(self) -> bool:
        return self._sender.enabled

    def compose(self, outbound: OutboundAccountEmail) -> tuple[str, str]:
        link = account_email_link(self._public_app_url, outbound)
        body = _BODIES[outbound.kind].format(link=link, hours=self._hours, minutes=self._minutes)
        return _SUBJECTS[outbound.kind], body

    async def deliver(self, outbound: OutboundAccountEmail) -> bool:
        """Send one e-mail; never raises (runs as a post-response background task)."""
        if not self.enabled:
            return False
        day = self._clock().strftime("%Y%m%d")
        try:
            sent_today = await self._daily_counter(f"chisa:account-email:v1:{day}", 2 * 86_400)
        except Exception as error:
            log.warning("Account e-mail blocked: quota store unavailable",
                        error_type=type(error).__name__)
            return False
        if sent_today > self._daily_limit:
            log.warning("Account e-mail blocked: daily ceiling reached", kind=outbound.kind)
            return False
        subject, body = self.compose(outbound)
        try:
            await self._sender.send(to=outbound.to, subject=subject, text=body)
        except Exception as error:
            log.warning("Account e-mail delivery failed", kind=outbound.kind,
                        error_type=type(error).__name__)
            return False
        log.info("Account e-mail sent", kind=outbound.kind, recipient_ref=_ref(outbound.to))
        return True


def _ref(address: str) -> str:
    """Short, non-reversible correlation id for support (not the address)."""
    return hashlib.sha256(address.encode("utf-8")).hexdigest()[:12]
