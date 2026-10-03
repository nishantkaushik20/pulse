"""Structured JSON logging with secret redaction."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_STANDARD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}

_SENSITIVE_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "database_url",
    "redis_url",
    "password",
    "secret",
    "token",
    "api_key",
)

_BEARER = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_URL_USERINFO = re.compile(r"([a-z][a-z0-9+.-]*://)[^\s/]*@", re.IGNORECASE)
_SENSITIVE_QUERY = re.compile(
    r"([?&](?:access_token|refresh_token|id_token|api_key|code|token|password|secret)=)[^&#\s]+",
    re.IGNORECASE,
)
_QUERY_STRING = re.compile(r"\?[^ \t\"']*")
_REDACTED = "***"


def _is_sensitive(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_PARTS)


def _redact_text(value: str) -> str:
    redacted = _BEARER.sub("Bearer ***", value)
    redacted = _URL_USERINFO.sub(r"\1***@", redacted)
    return _SENSITIVE_QUERY.sub(r"\1***", redacted)


def redact(value: Any, key: str | None = None) -> Any:
    if key is not None and _is_sensitive(key):
        return _REDACTED
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {
            str(item_key): redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class AccessQueryFilter(logging.Filter):
    """Remove query strings from Uvicorn access log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _QUERY_STRING.sub("", record.msg)
        record.args = _strip_query_args(record.args)
        return True


def _strip_query_args(args: Any) -> Any:
    if isinstance(args, tuple):
        return tuple(
            _QUERY_STRING.sub("", item) if isinstance(item, str) else item for item in args
        )
    if isinstance(args, dict):
        return {
            key: _QUERY_STRING.sub("", item) if isinstance(item, str) else item
            for key, item in args.items()
        }
    return args


def install_access_log_filter() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if any(isinstance(existing, AccessQueryFilter) for existing in access_logger.filters):
        return
    access_logger.addFilter(AccessQueryFilter())


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            payload[key] = redact(value, key)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    install_access_log_filter()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
