import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variables for distributed/asynchronous tracing
_log_context: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)

# Card number regex: matches 13 to 19 continuous digits or separated by dashes/spaces
CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def mask_sensitive_data(text: str) -> str:
    """Mask potential credit card numbers or long sensitive numeric strings."""

    def _mask_match(match: re.Match) -> str:
        s = match.group(0)
        digits_only = re.sub(r"\D", "", s)
        # Check if length qualifies as payment card (13-19 digits)
        if 13 <= len(digits_only) <= 19:
            # Preserve first 4 and last 4, mask middle with X
            if len(s) > 8:
                return s[:4] + ("*" * (len(s) - 8)) + s[-4:]
            return "*" * len(s)
        return s

    return CARD_REGEX.sub(_mask_match, text)


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for production observability."""

    def format(self, record: logging.LogRecord) -> str:
        now = datetime.now(UTC).isoformat()
        log_payload: dict[str, Any] = {
            "timestamp": now,
            "level": record.levelname,
            "logger": record.name,
            "message": mask_sensitive_data(record.getMessage()),
        }

        # Include contextual fields
        context = _log_context.get()
        if context:
            log_payload.update(context)

        # Include custom extra fields passed on record
        for key, val in record.__dict__.items():
            if key not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "id",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            ):
                if isinstance(val, str):
                    log_payload[key] = mask_sensitive_data(val)
                else:
                    log_payload[key] = val

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload, default=str)


def set_log_context(**kwargs: Any) -> None:
    """Set contextual keys (e.g. document_id, job_id, worker_id)."""
    current = (_log_context.get() or {}).copy()
    current.update(kwargs)
    _log_context.set(current)


def clear_log_context() -> None:
    """Reset log context."""
    _log_context.set(None)


def setup_logging(level: str = "INFO") -> None:
    """Initialize root and app loggers with JSONFormatter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)
