"""The attention inbox is authenticated and tenant-scoped."""

import logging

import pytest
from fastapi.testclient import TestClient
from tests.domain_app import DomainApp

from pulse_api.config import get_settings
from pulse_api.deps import get_session
from pulse_api.main import create_app
from pulse_api.models import AttentionStatus


def test_unauthenticated_inbox_and_resolve_are_rejected(
    domain: DomainApp,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("CLERK_ISSUER", "")
    monkeypatch.setenv("CLERK_SECRET_KEY", "")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_session] = domain.client.app.dependency_overrides[get_session]
    with caplog.at_level(logging.DEBUG), TestClient(app) as client:
        listed = client.get("/attention", headers={"Authorization": "Bearer inbox-token"})
        resolved = client.post(
            "/attention/00000000-0000-0000-0000-000000000001/resolve",
            headers={"Authorization": "Bearer inbox-token"},
        )

    assert listed.status_code == 401
    assert resolved.status_code == 401
    assert "inbox-token" not in listed.text
    assert "inbox-token" not in resolved.text
    assert "inbox-token" not in caplog.text


def test_other_tenant_cannot_list_or_resolve_known_items(domain: DomainApp) -> None:
    domain.login("user_a", "a@example.com", "Ada")
    assert domain.client.post("/tenants", json={"name": "Tenant A"}).status_code == 201
    created = domain.client.post(
        "/attention-items",
        json={"type": "manual", "priority": "HIGH", "title": "Tenant A only"},
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]

    domain.login("user_b", "b@example.com", "Bea")
    assert domain.client.post("/tenants", json={"name": "Tenant B"}).status_code == 201
    listed = domain.client.get("/attention")
    hidden = domain.client.post(f"/attention/{item_id}/resolve")
    direct = domain.client.get(f"/attention-items/{item_id}")

    assert listed.status_code == 200
    assert listed.json()["items"] == []
    assert "Tenant A only" not in listed.text
    assert hidden.status_code == 404
    assert direct.status_code == 404
    assert hidden.json()["detail"] == "not found"
    assert item_id not in hidden.text

    domain.login("user_a", "a@example.com", "Ada")
    still_open = domain.client.get(f"/attention-items/{item_id}")
    assert still_open.status_code == 200
    assert still_open.json()["status"] == AttentionStatus.OPEN
    inbox = domain.client.get("/attention")
    assert [item["id"] for item in inbox.json()["items"]] == [item_id]
