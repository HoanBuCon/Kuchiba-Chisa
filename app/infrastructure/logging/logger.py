from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from app.config.settings import settings


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
        _drop_color_message_key,
    ]

    if settings.is_dev:
        # Pretty colored console output for development
        processors: list[Any] = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # Structured JSON for production log aggregators
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
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
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("backend.log", encoding="utf-8")
        ],
        level=logging.DEBUG if settings.is_dev else logging.INFO,
    )


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    Returns a structlog logger bound to a component name.
    Usage: log = get_logger(__name__)
    """
    return structlog.get_logger(name)
