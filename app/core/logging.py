"""
Structured JSON logging powered by structlog.

Every log line produced by the gateway is a valid JSON object containing at
minimum: ``request_id``, ``tenant_id``, ``endpoint``, ``timestamp``,
``level``, and ``event``.  The ``request_id``, ``tenant_id``, and
``endpoint`` are stored in ``contextvars`` that are set by the
correlation-ID middleware and are automatically injected into every log
call within that request scope.

Usage:
    from app.core.logging import setup_logging, get_logger

    setup_logging("INFO")
    logger = get_logger(__name__)
    logger.info("document_ingested", doc_id="abc123", chunks=42)
"""

from __future__ import annotations

import contextvars
import logging
import sys
from typing import Any

import structlog

# =============================================================================
# Context variables
# =============================================================================
# These are set once per request by CorrelationIdMiddleware and are
# transparently available to every log call in the same async context.

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
tenant_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "tenant_id", default="-"
)

# Endpoint (URL path) of the current request.  Set by CorrelationIdMiddleware
# so that even deep service-layer log calls include the endpoint without
# callers needing to pass it explicitly.
endpoint_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "endpoint", default="-"
)


# =============================================================================
# Custom structlog processors
# =============================================================================


def _inject_context_vars(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Structlog processor that copies request-scoped context vars into every
    log event dict so callers don't have to pass them explicitly.

    Injected fields:
    - ``request_id`` — unique correlation ID for the request.
    - ``tenant_id``  — tenant performing the request.
    - ``endpoint``   — URL path of the request.
    """
    # Only inject if not already set (allow manual override)
    event_dict.setdefault("request_id", request_id_ctx.get())
    event_dict.setdefault("tenant_id", tenant_id_ctx.get())
    event_dict.setdefault("endpoint", endpoint_ctx.get())
    return event_dict


def _add_log_level_upper(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Normalise the ``level`` key to uppercase (INFO, ERROR, …)."""
    event_dict["level"] = method_name.upper()
    return event_dict


# =============================================================================
# Public API
# =============================================================================


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structlog + stdlib logging for structured JSON output.

    Call this **once** at application startup (inside the lifespan handler).

    Args:
        log_level: Python logging level name (DEBUG, INFO, WARNING, …).
    """
    # Resolve the numeric level early so we fail fast on typos
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # --- Shared processors used by both structlog and stdlib bridge --------
    shared_processors: list[structlog.types.Processor] = [
        # Inject request_id / tenant_id from contextvars
        _inject_context_vars,
        # Normalise level string
        _add_log_level_upper,
        # Add caller information (module, function, line number)
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.MODULE,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
        # Add ISO-8601 timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Format stack traces
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # --- Configure structlog -----------------------------------------------
    structlog.configure(
        processors=[
            # Filter by level early to avoid unnecessary work
            structlog.stdlib.filter_by_level,
            # Standard-lib integration
            structlog.stdlib.add_log_level,
            *shared_processors,
            # Prepare event dict for the standard library formatter
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        # Use stdlib's LoggerFactory so structlog respects stdlib filters
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # --- Configure the root stdlib logger ----------------------------------
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any existing handlers to prevent duplicate output
    root_logger.handlers.clear()

    # Stream handler → stderr (structured JSON via structlog)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(numeric_level)

    # Use structlog's formatter so stdlib loggers also emit JSON
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(ensure_ascii=False),
        foreign_pre_chain=shared_processors,
    ))

    root_logger.addHandler(handler)

    # Quieten noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore", "asyncio", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a structlog bound logger scoped to *name*.

    The logger automatically includes ``request_id``, ``tenant_id``, and
    ``endpoint`` from context vars thanks to the ``_inject_context_vars``
    processor.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A structlog ``BoundLogger`` instance.
    """
    return structlog.get_logger(name)
