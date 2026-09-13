from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

_REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "proxy_authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "connection_string",
    "connectionstring",
    "database_url",
    "redis_url",
    "dsn",
)

_AUTHORIZATION_PATTERN = re.compile(
    r"(?i)(\b(?:proxy-)?authorization(?:\s*[:=]\s*|\s+))"
    r"(?:(?:bearer|basic)\s+)?[^\s,;]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\b(?:bearer|basic)\s+[^\s,;]+")
_COOKIE_PATTERN = re.compile(r"(?i)(\bcookies?(?:\s*[:=]\s*|\s+))[^\r\n]+")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:password|passwd|pwd|secret|token|access_token|refresh_token|"
    r"id_token|api[_-]?key|connection_string|database_url|redis_url|dsn)\s*[:=]\s*)[^\s,;]+"
)
_CONNECTION_STRING_PATTERN = re.compile(
    r"(?i)\b(?:postgres(?:ql)?(?:\+[^:/\s]+)?|redis(?:s)?|mysql(?:\+[^:/\s]+)?|"
    r"sqlite(?:\+[^:/\s]+)?|mongodb(?:\+[^:/\s]+)?|amqp(?:\+[^:/\s]+)?|"
    r"https?)://[^\s\"']+"
)
_CREDENTIAL_URL_PATTERN = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s]+@[^\s\"']+"
)

_STANDARD_LOG_RECORD_FIELDS = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def _is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _redact_string(value: str) -> str:
    value = _CREDENTIAL_URL_PATTERN.sub(_REDACTED, value)
    value = _CONNECTION_STRING_PATTERN.sub(_REDACTED, value)
    value = _AUTHORIZATION_PATTERN.sub(rf"\1{_REDACTED}", value)
    value = _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    value = _COOKIE_PATTERN.sub(rf"\1{_REDACTED}", value)
    return _SECRET_ASSIGNMENT_PATTERN.sub(rf"\1{_REDACTED}", value)


def redact_sensitive_data(value: Any, *, key: object | None = None) -> Any:
    """Recursively redact credentials and connection details from log data."""

    if _is_sensitive_key(key):
        return _REDACTED
    if isinstance(value, Mapping):
        return {
            item_key: redact_sensitive_data(item_value, key=item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if isinstance(value, set):
        return {_redact_string(str(item)) for item in value}
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _redact_record(record: logging.LogRecord) -> None:
    try:
        message = record.getMessage()
    except Exception:  # noqa: BLE001 - logging must never break application flow
        message = str(record.msg)
    record.msg = redact_sensitive_data(message)
    record.args = ()

    for field_name, field_value in record.__dict__.items():
        if field_name in _STANDARD_LOG_RECORD_FIELDS:
            continue
        setattr(record, field_name, redact_sensitive_data(field_value, key=field_name))

    # Exception text can contain a password or connection string. The
    # generic application error handler logs a safe event instead.
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None


class RedactingFilter(logging.Filter):
    """Remove sensitive values before records reach any configured handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        _redact_record(record)
        return True


class StructuredJsonFormatter(logging.Formatter):
    """Format log records as JSON objects with redacted fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_data(record.getMessage()),
        }
        extras = {
            field_name: field_value
            for field_name, field_value in record.__dict__.items()
            if field_name not in _STANDARD_LOG_RECORD_FIELDS
        }
        payload.update(redact_sensitive_data(extras))
        safe_payload = redact_sensitive_data(payload)
        return json.dumps(
            safe_payload,
            default=lambda item: redact_sensitive_data(str(item)),
            ensure_ascii=False,
            separators=(",", ":"),
        )


JsonFormatter = StructuredJsonFormatter
SensitiveDataFilter = RedactingFilter


def configure_logging(level: int | str = logging.INFO) -> None:
    """Configure process logging with JSON output and redaction."""

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    formatter = StructuredJsonFormatter()

    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler(sys.stdout))

    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
        if not any(isinstance(item, RedactingFilter) for item in handler.filters):
            handler.addFilter(RedactingFilter())
