import json
import logging

import pytest
from fastapi.testclient import TestClient

from pulse_api.logging import JsonFormatter
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


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.setFormatter(JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def _capture_handler() -> _ListHandler:
    return _ListHandler()
