"""structlog configuration -- JSON in prod, colored console in dev.

trace_id / span_id are merged in via the OpenTelemetry processor, which
no-ops cleanly if OTel is not initialized. request_id / mcp_context_id
are stamped onto contextvars by app.observability.middleware.

Call configure_logging() exactly once during app startup.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


def _otel_inject(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add trace_id / span_id from the active OTel span, if any.

    Imported lazily so the module doesn't fail when OTel is uninstalled.
    """
    try:
        from opentelemetry import trace  # type: ignore
    except ImportError:  # pragma: no cover -- OTel always pinned in requirements
        return event_dict
    span = trace.get_current_span()
    if span is None:
        return event_dict
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return event_dict
    event_dict["trace_id"] = format(ctx.trace_id, "032x")
    event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def configure_logging(*, json_output: bool | None = None, level: str | None = None) -> None:
    """Idempotent structlog setup.

    Args:
      json_output: force JSON renderer; default = True unless DEV=1.
      level: root log level; default = $LOG_LEVEL or 'INFO'.
    """
    if json_output is None:
        json_output = os.getenv("DEV", "").lower() not in ("1", "true", "yes")
    level_str = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    level_int = getattr(logging, level_str, logging.INFO)

    # Route stdlib logging through structlog so uvicorn/sqlalchemy logs are
    # also JSON-formatted with the same context fields.
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=level_int, force=True
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _otel_inject,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level_int),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
