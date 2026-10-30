"""SMTP transport for account e-mail (works with any transactional provider's SMTP relay).

The standard-library client runs in a worker thread so the event loop never blocks.
TLS is mandatory (STARTTLS or implicit TLS) with certificate verification. Nothing
here logs recipients, subjects or bodies; callers log only the outcome.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from app.domain.interfaces.accounts import IEmailSender


class SmtpEmailSender(IEmailSender):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        security: str,
        username: str,
        password: str,
        sender: str,
        timeout_seconds: float,
    ) -> None:
        self._host = host.strip()
        self._port = port
        self._security = security
        self._username = username
        self._password = password
        self._sender = sender.strip()
        self._timeout = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._host and self._sender)

    async def send(self, *, to: str, subject: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if self._security == "ssl":
            smtp = smtplib.SMTP_SSL(
                self._host, self._port, timeout=self._timeout, context=context
            )
        else:
            smtp = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
        with smtp:
            if self._security != "ssl":
                smtp.starttls(context=context)
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)
