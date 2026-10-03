import json
import logging

import pytest
from fastapi.testclient import TestClient

from pulse_api.logging import JsonFormatter, configure_logging
from pulse_api.main import create_app


def test_structured_logs_redact_secrets() -> None:
    record = logging.LogRecord(
        name="pulse_api.security",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="received Bearer super-secret-token",
        args=(),
        exc_info=None,
    )
    record.password = "local-password"
    record.authorization = "Bearer another-token"
    record.nested = {"api_key": "key-value", "safe": "visible"}

    payload = json.loads(JsonFormatter().format(record))

    assert "super-secret-token" not in payload["message"]
    assert payload["password"] == "***"
    assert payload["authorization"] == "***"
    assert payload["nested"]["api_key"] == "***"
    assert payload["nested"]["safe"] == "visible"
    serialized = json.dumps(payload)
    assert "local-password" not in serialized
    assert "another-token" not in serialized
    assert "key-value" not in serialized


def test_connection_urls_and_oauth_query_values_are_redacted() -> None:
    record = logging.LogRecord(
        name="pulse_api.security",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=(
            "dsn postgresql+psycopg://pulse:inline-db-password@db:5432/pulse "
            "cache redis://:inline-redis-password@cache:6379/0 "
            "callback /oauth/callback?code=oauth-code-value&token=oauth-token-value"
        ),
        args=(),
        exc_info=None,
    )
    record.database_url = "postgresql+psycopg://pulse:field-db-password@db:5432/pulse"
    record.redis_url = "redis://:field-redis-password@cache:6379/0"
    record.DATABASE_URL = "postgresql://pulse:env-db-password@db:5432/pulse"
    record.REDIS_URL = "redis://default:env-redis-password@redis:6379/0"

    payload = json.loads(JsonFormatter().format(record))
    serialized = json.dumps(payload)

    for secret in (
        "inline-db-password",
        "inline-redis-password",
        "field-db-password",
        "field-redis-password",
        "env-db-password",
        "env-redis-password",
        "oauth-code-value",
        "oauth-token-value",
    ):
        assert secret not in serialized
    assert payload["database_url"] == "***"
    assert payload["redis_url"] == "***"
    assert payload["DATABASE_URL"] == "***"
    assert payload["REDIS_URL"] == "***"
    assert "postgresql+psycopg://***@db:5432/pulse" in payload["message"]
    assert "code=***" in payload["message"]
    assert "token=***" in payload["message"]


def test_uvicorn_access_log_strips_query_string() -> None:
    configure_logging("INFO")
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.setLevel(logging.INFO)
    access.propagate = False
    handler = _PlainHandler()
    access.addHandler(handler)

    access.info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1",
        "GET",
        "/oauth/callback?code=oauth-code-value&token=oauth-token-value",
        "1.1",
        302,
    )

    rendered = "\n".join(handler.lines)
    assert "/oauth/callback" in rendered
    assert "oauth-code-value" not in rendered
    assert "oauth-token-value" not in rendered
    assert "?" not in rendered


def test_request_logs_omit_authorization_header() -> None:
    handler = _capture_handler()
    logging.getLogger().addHandler(handler)

    with TestClient(create_app()) as client:
        logging.getLogger().addHandler(handler)
        response = client.get(
            "/health",
            headers={"Authorization": "Bearer request-token-value"},
        )

    assert response.status_code == 200
    rendered = "\n".join(handler.lines)
    assert "request-token-value" not in rendered
    assert "Bearer request-token-value" not in rendered


def test_readiness_errors_do_not_leak_connection_details(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "postgresql+psycopg://pulse:super-secret-db-password@db:5432/pulse"

    def fail(_url: str) -> None:
        raise RuntimeError(secret)

    monkeypatch.setattr("pulse_api.health.check_database", fail)
    monkeypatch.setattr("pulse_api.health.check_redis", lambda _url: None)

    with TestClient(create_app()) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert "super-secret-db-password" not in response.text
    assert secret not in response.text


class _PlainHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.setFormatter(JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def _capture_handler() -> _ListHandler:
    return _ListHandler()
