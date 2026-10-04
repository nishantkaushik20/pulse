import pytest
from fastapi.testclient import TestClient

from pulse_api.main import create_app


def test_health_is_alive() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_when_dependencies_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pulse_api.health.check_database", lambda _url: None)
    monkeypatch.setattr("pulse_api.health.check_redis", lambda _url: None)

    with TestClient(create_app()) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok"},
    }


def test_ready_fails_when_database_check_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_url: str) -> None:
        raise ConnectionError("database unavailable")

    monkeypatch.setattr("pulse_api.health.check_database", fail)
    monkeypatch.setattr("pulse_api.health.check_redis", lambda _url: None)

    with TestClient(create_app()) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["checks"]["database"] == "error"
    assert response.json()["checks"]["redis"] == "ok"


def test_ready_fails_when_redis_check_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_url: str) -> None:
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr("pulse_api.health.check_database", lambda _url: None)
    monkeypatch.setattr("pulse_api.health.check_redis", fail)

    with TestClient(create_app()) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == "error"


def test_response_carries_a_request_id() -> None:
    with TestClient(create_app()) as client:
        generated = client.get("/health")
        echoed = client.get("/health", headers={"X-Request-ID": "req-1"})
        rejected = client.get("/health", headers={"X-Request-ID": "Bearer secret"})

    assert generated.headers["X-Request-ID"]
    assert echoed.headers["X-Request-ID"] == "req-1"
    assert rejected.headers["X-Request-ID"] != "Bearer secret"
