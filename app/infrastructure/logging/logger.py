from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from opentelemetry import trace
from structlog.tracebacks import ExceptionDictTransformer
from structlog.types import EventDict, WrappedLogger

from app.config.settings import settings
from app.infrastructure.logging.log_redaction import redact_log_fields

# Reconfigure Windows stdout/stderr to UTF-8 to prevent charmap encoding errors with Vietnamese/Unicode
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def _add_service_info(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Inject service-level metadata into every log record."""
    event_dict["service"] = "chisa-api"
    event_dict["env"] = settings.APP_ENV
    return event_dict


def _drop_color_message_key(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Remove uvicorn's 'color_message' field (redundant noise)."""
    event_dict.pop("color_message", None)
    return event_dict


def _add_trace_context(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Correlate logs with sampled traces without creating metric dimensions."""
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event_dict["trace_id"] = format(context.trace_id, "032x")
        event_dict["span_id"] = format(context.span_id, "016x")
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog for the entire application.
    - Development: colored, human-readable console output
    - Production/Test: JSON output for log aggregation systems
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _add_service_info,
        _add_trace_context,
        _drop_color_message_key,
    ]
    # B-2: raw conversation, query, credential and OAuth fields never reach a
    # log sink. Only an explicit development-only switch may disable this.
    if not (settings.is_dev and settings.LOG_UNSAFE_CONTENT_DEBUG):
        shared_processors.append(redact_log_fields)

    if settings.is_dev:
        # Pretty colored console output for development
        processors: list[Any] = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # Structured JSON for production log aggregators
        processors = shared_processors + [
            # Never serialize frame locals: they may hold passwords, tokens or
            # conversation text from the failing request.
            structlog.processors.ExceptionRenderer(
                ExceptionDictTransformer(show_locals=False)
            ),
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,  # type: ignore[arg-type]
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging to route through structlog
    logging.basicConfig(
        format="%(message)s",
        handlers=_log_handlers(),
        level=logging.DEBUG if settings.is_dev else logging.INFO,
    )


def _log_handlers() -> list[logging.Handler]:
    """Stdout always; an optional size-bounded file (B-2: no unbounded backend.log).

    Production containers log to stdout only (Docker json-file rotation owns
    retention). A local file is opt-in through ``APP_LOG_FILE``.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    log_file = (settings.APP_LOG_FILE or "").strip()
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                path,
                maxBytes=settings.APP_LOG_MAX_BYTES,
                backupCount=settings.APP_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
        )
    return handlers


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    Returns a structlog logger bound to a component name.
    Usage: log = get_logger(__name__)
    """
    return structlog.get_logger(name)
