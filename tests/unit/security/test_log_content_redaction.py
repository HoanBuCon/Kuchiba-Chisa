"""B-2 regression: production application logs never carry raw user content."""

from __future__ import annotations

import ast
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
import structlog

from app.config.settings import Settings, settings
from app.infrastructure.logging import logger as app_logger
from app.infrastructure.logging.log_redaction import redact_log_fields

SECRET_TEXT = "Senpai ơi số điện thoại của em là 0912345678"


def test_processor_redacts_content_and_credentials_but_keeps_metadata() -> None:
    event = redact_log_fields(
        None,
        "info",
        {
            "event": "Executing search query",
            "query": SECRET_TEXT,
            "user_message": SECRET_TEXT,
            "prev_context": ["a", "b"],
            "password": "hunter2-long-password",
            "client_secret": "abc",
            "refresh_token": "tok",
            "code": "4/0Aabc",
            "query_chars": 42,
            "input_tokens": 120,
            "has_prev_context": True,
            "user_id": "3f1e",
        },
    )

    rendered = json.dumps(event, ensure_ascii=False)
    assert SECRET_TEXT not in rendered
    assert "hunter2" not in rendered
    assert "4/0Aabc" not in rendered
    assert event["query"] == f"[redacted:{len(SECRET_TEXT)} chars]"
    assert event["prev_context"] == "[redacted:2 items]"
    assert event["query_chars"] == 42
    assert event["input_tokens"] == 120
    assert event["has_prev_context"] is True
    assert event["user_id"] == "3f1e"
    assert event["event"] == "Executing search query"


class _NamedLogger:
    name = "chisa.test"


def test_production_logging_pipeline_redacts_and_hides_frame_locals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "APP_LOG_FILE", "")
    try:
        app_logger.configure_logging()
        processors = structlog.get_config()["processors"]
        assert redact_log_fields in processors

        def failing_login(password: str) -> None:
            raise RuntimeError("boom")

        try:
            failing_login("p4ssw0rd-in-frame-local")
        except RuntimeError:
            event: object = {
                "event": "Login failed",
                "user_message": SECRET_TEXT,
                "query_chars": 3,
                "exc_info": True,
            }
            for processor in processors:
                event = processor(_NamedLogger(), "error", event)
        assert isinstance(event, str)
        assert SECRET_TEXT not in event
        assert "p4ssw0rd-in-frame-local" not in event
        assert "Login failed" in event
        assert "RuntimeError" in event
    finally:
        structlog.reset_defaults()


def test_backend_log_is_not_written_unbounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "APP_LOG_FILE", "")
    handlers = app_logger._log_handlers()
    assert [type(h) for h in handlers] == [logging.StreamHandler]

    log_file = tmp_path / "logs" / "backend.log"
    monkeypatch.setattr(settings, "APP_LOG_FILE", str(log_file))
    handlers = app_logger._log_handlers()
    rotating = [h for h in handlers if isinstance(h, RotatingFileHandler)]
    assert len(rotating) == 1
    assert rotating[0].maxBytes == settings.APP_LOG_MAX_BYTES > 0
    assert rotating[0].backupCount == settings.APP_LOG_BACKUP_COUNT
    assert not any(
        type(h) is logging.FileHandler for h in handlers
    ), "plain FileHandler grows without bound"
    for handler in handlers:
        handler.close()


def test_unsafe_content_debug_switch_is_rejected_outside_development() -> None:
    with pytest.raises(ValueError, match="only allowed in development"):
        Settings(APP_ENV="test", LOG_UNSAFE_CONTENT_DEBUG=True)


CONTENT_KEYWORDS = {
    "user_message",
    "raw_user_query",
    "current",
    "prev_context",
    "query",
    "search_query",
    "rewritten_query",
    "content",
    "text",
    "prompt",
    "history",
    "password",
    "token",
    "refresh_token",
    "id_token",
    "code",
    "email",
}
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
LOGGER_NAMES = {"log", "logger", "_log", "_dep_log", "_logger"}
# Offline ingestion/benchmark tooling logs public wiki titles and benchmark queries.
OFFLINE_PATHS = ("app/infrastructure/ingestion/",)


def test_runtime_log_calls_do_not_pass_raw_content_fields() -> None:
    offenders: list[str] = []
    for path in Path("app").rglob("*.py"):
        normalized = path.as_posix()
        if normalized.startswith(OFFLINE_PATHS):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in LOG_METHODS
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in LOGGER_NAMES
            ):
                continue
            leaked = sorted(k.arg for k in node.keywords if k.arg in CONTENT_KEYWORDS)
            if leaked:
                offenders.append(f"{normalized}:{node.lineno} {leaked}")
    assert offenders == []
