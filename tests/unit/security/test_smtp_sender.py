"""SMTP adapter: TLS is mandatory and verified before credentials are sent."""

from __future__ import annotations

import ssl

import pytest

from app.infrastructure.email import smtp_sender
from app.infrastructure.email.smtp_sender import SmtpEmailSender


class RecordingSMTP:
    instances: list[RecordingSMTP] = []

    def __init__(self, host, port, timeout=None, context=None) -> None:
        self.calls: list[tuple] = [("connect", host, port, context)]
        RecordingSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append(("starttls", context))

    def login(self, username, password):
        self.calls.append(("login", username))

    def send_message(self, message):
        self.calls.append(("send", message["To"], message["From"], message["Subject"]))


def _sender(security: str) -> SmtpEmailSender:
    return SmtpEmailSender(
        host="smtp.example.test", port=587, security=security, username="mailer",
        password="secret-pass", sender="Chisa <no-reply@example.test>", timeout_seconds=5,
    )


@pytest.mark.asyncio
async def test_starttls_precedes_login_with_certificate_verification(monkeypatch) -> None:
    RecordingSMTP.instances.clear()
    monkeypatch.setattr(smtp_sender.smtplib, "SMTP", RecordingSMTP)
    await _sender("starttls").send(to="senpai@example.com", subject="S", text="body")

    calls = RecordingSMTP.instances[0].calls
    assert [c[0] for c in calls] == ["connect", "starttls", "login", "send"]
    context = calls[1][1]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert calls[3][1:] == ("senpai@example.com", "Chisa <no-reply@example.test>", "S")


@pytest.mark.asyncio
async def test_implicit_tls_mode_uses_verified_context(monkeypatch) -> None:
    RecordingSMTP.instances.clear()
    monkeypatch.setattr(smtp_sender.smtplib, "SMTP_SSL", RecordingSMTP)
    await _sender("ssl").send(to="senpai@example.com", subject="S", text="body")

    calls = RecordingSMTP.instances[0].calls
    assert [c[0] for c in calls] == ["connect", "login", "send"]
    assert calls[0][3].verify_mode == ssl.CERT_REQUIRED


def test_sender_is_disabled_without_host_or_from() -> None:
    assert not SmtpEmailSender(
        host="", port=587, security="starttls", username="", password="", sender="x@y.z",
        timeout_seconds=5,
    ).enabled
    assert _sender("starttls").enabled
