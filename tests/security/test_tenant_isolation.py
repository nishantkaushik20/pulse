"""Tenant A cannot read Tenant B, even with a known resource id."""

import logging
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from tests.domain_app import DomainApp
from tests.records import record_attention, record_event

from pulse_api.context import TenantContext
from pulse_api.db import session_scope
from pulse_api.deps import get_identity, get_session
from pulse_api.errors import NotFoundError
from pulse_api.main import create_app
from pulse_api.models import Customer, Tenant, TenantRole, TenantUser, User
from pulse_api.repositories import CustomerRepository
from pulse_api.services import (
    ActionService,
    AttentionService,
    BusinessEventService,
    CustomerService,
)


def test_source_has_no_auth_disabled_switch() -> None:
    root = Path(__file__).resolve().parents[2] / "apps" / "api" / "src"
    for path in root.rglob("*.py"):
        assert "AUTH_DISABLED" not in path.read_text(encoding="utf-8")


def test_unauthenticated_requests_rejected(
    domain: DomainApp,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("CLERK_ISSUER", "")
    monkeypatch.setenv("CLERK_SECRET_KEY", "")
    from pulse_api.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_session] = domain.client.app.dependency_overrides[get_session]
    with caplog.at_level(logging.DEBUG), TestClient(app) as client:
        health = client.get("/health")
        denied = client.get(
            "/me",
            headers={"Authorization": "Bearer super-secret-clerk-token"},
        )

    assert health.status_code == 200
    assert denied.status_code == 401
    assert "super-secret-clerk-token" not in denied.text
    assert "super-secret-clerk-token" not in caplog.text


def test_tenant_a_cannot_read_tenant_b_records_by_known_id(
    domain: DomainApp,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    owner = _bootstrap(domain, "user_a", "a@example.com", "Ada", "Tenant A")
    customer = domain.client.post(
        "/customers",
        json={
            "name": "Secret Customer",
            "phone": "555-0100-SECRET",
            "email": "secret@tenant-a.example",
            "tenant_id": str(uuid4()),
        },
    )
    assert customer.status_code == 201
    customer_id = customer.json()["id"]
    assert "tenant_id" not in customer.json()

    contact = domain.client.post(
        f"/customers/{customer_id}/contacts",
        json={"name": "Pat", "email": "Pat@Example.com"},
    )
    assert contact.status_code == 201
    assert contact.json()["email"] == "pat@example.com"
    contact_id = contact.json()["id"]

    attention_id = record_attention(domain, title="Call back", item_type="follow_up")
    event_id = record_event(domain, entity_id=UUID(customer_id))

    action = domain.client.post(
        "/actions",
        json={"action_type": "send_note", "status": "COMPLETED", "input": {"text": "hidden"}},
    )
    assert action.status_code == 201
    assert action.json()["status"] == "PENDING"
    assert action.json()["requested_by"] == owner["user_id"]
    action_id = action.json()["id"]
    approval = domain.client.post(f"/actions/{action_id}/approvals", json={"status": "APPROVED"})
    assert approval.status_code == 201
    assert approval.json()["approved_at"] is not None
    approval_id = approval.json()["id"]

    assert "555-0100-SECRET" not in caplog.text
    assert "secret@tenant-a.example" not in caplog.text

    domain.login("user_b", "b@example.com", "Bea")
    intruder = _bootstrap(domain, "user_b", "b@example.com", "Bea", "Tenant B")
    assert intruder["tenant_id"] != owner["tenant_id"]

    assert domain.client.get(f"/customers/{customer_id}").status_code == 404
    assert (
        domain.client.patch(f"/customers/{customer_id}", json={"name": "Stolen"}).status_code == 404
    )
    assert domain.client.delete(f"/customers/{customer_id}").status_code == 404
    assert domain.client.get(f"/contacts/{contact_id}").status_code == 404
    assert domain.client.get(f"/attention-items/{attention_id}").status_code == 404
    assert domain.client.get(f"/business-events/{event_id}").status_code == 404
    assert domain.client.get(f"/actions/{action_id}").status_code == 404
    assert domain.client.get(f"/actions/{action_id}/approvals/{approval_id}").status_code == 404
    listed = domain.client.get("/customers", params={"tenant_id": owner["tenant_id"]})
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    intruder_tenant = TenantContext(
        user_id=UUID(intruder["user_id"]),
        tenant_id=UUID(intruder["tenant_id"]),
        role=TenantRole.MEMBER,
    )
    with session_scope(domain.factory) as session:
        visible = CustomerRepository(session, intruder_tenant.tenant_id).get(UUID(customer_id))
        stored = session.scalar(select(Customer).where(Customer.id == UUID(customer_id)))
        assert visible is None
        assert stored is not None
        assert stored.tenant_id == UUID(owner["tenant_id"])
        with pytest.raises(NotFoundError):
            CustomerService(session, intruder_tenant).get(UUID(customer_id))
        with pytest.raises(NotFoundError):
            AttentionService(session, intruder_tenant).get(UUID(attention_id))
        with pytest.raises(NotFoundError):
            BusinessEventService(session, intruder_tenant).get(UUID(event_id))
        with pytest.raises(NotFoundError):
            ActionService(session, intruder_tenant).get(UUID(action_id))


def test_repository_overwrites_client_tenant_id(domain: DomainApp) -> None:
    owner = _bootstrap(domain, "user_a", "a@example.com", "Ada", "Tenant A")
    domain.login("user_b", "b@example.com", "Bea")
    intruder = _bootstrap(domain, "user_b", "b@example.com", "Bea", "Tenant B")
    with session_scope(domain.factory) as session:
        repo = CustomerRepository(session, UUID(intruder["tenant_id"]))
        saved = repo._insert(
            Customer(
                tenant_id=UUID(owner["tenant_id"]),
                name="Forced",
                status="ACTIVE",
            )
        )
        assert saved.tenant_id == UUID(intruder["tenant_id"])
        changed = repo.apply_update(saved, {"tenant_id": UUID(owner["tenant_id"]), "name": "Kept"})
        assert changed.tenant_id == UUID(intruder["tenant_id"])
        assert changed.name == "Kept"


def test_membership_rules_and_uniqueness(domain: DomainApp) -> None:
    owner = _bootstrap(domain, "user_a", "a@example.com", "Ada", "Tenant A")
    domain.login("user_c", "c@example.com", "Cam")
    invited = domain.client.get("/me")
    assert invited.status_code == 200
    invited_id = invited.json()["user"]["id"]
    assert invited.json()["tenant"] is None
    assert domain.client.get("/customers").status_code == 403

    domain.login("user_a", "a@example.com", "Ada")
    created = domain.client.post(
        "/tenant/members",
        json={"user_id": invited_id, "role": "MEMBER", "tenant_id": str(uuid4())},
    )
    assert created.status_code == 201
    duplicate = domain.client.post(
        "/tenant/members", json={"user_id": invited_id, "role": "MEMBER"}
    )
    assert duplicate.status_code == 409
    unknown = domain.client.post(
        "/tenant/members", json={"user_id": str(uuid4()), "role": "MEMBER"}
    )
    assert unknown.status_code == 404

    domain.login("user_c", "c@example.com", "Cam")
    me = domain.client.get("/me")
    assert me.json()["tenant"]["id"] == owner["tenant_id"]
    assert me.json()["tenant"]["role"] == "MEMBER"
    assert domain.client.patch("/tenant", json={"name": "Hijack"}).status_code == 403
    assert (
        domain.client.post("/tenant/members", json={"user_id": owner["user_id"]}).status_code == 403
    )
    own_customer = domain.client.post("/customers", json={"name": "Member customer"})
    assert own_customer.status_code == 201

    domain.login("user_a", "a@example.com", "Ada")
    renamed = domain.client.patch("/tenant", json={"name": "Tenant A renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Tenant A renamed"
    second = domain.client.post("/tenants", json={"name": "Another"})
    assert second.status_code == 409


def test_customer_delete_is_blocked_while_contacts_exist(domain: DomainApp) -> None:
    _bootstrap(domain, "user_a", "a@example.com", "Ada", "Tenant A")
    customer = domain.client.post("/customers", json={"name": "Kept"})
    customer_id = customer.json()["id"]
    domain.client.post(f"/customers/{customer_id}/contacts", json={"name": "Pat"})
    blocked = domain.client.delete(f"/customers/{customer_id}")
    assert blocked.status_code == 409
    domain.client.delete(
        f"/contacts/{domain.client.get(f'/customers/{customer_id}/contacts').json()['items'][0]['id']}"
    )
    assert domain.client.delete(f"/customers/{customer_id}").status_code == 204


def test_database_rejects_duplicate_membership_and_bad_role(domain: DomainApp) -> None:
    with session_scope(domain.factory) as session:
        user = User(clerk_user_id="db_user", email="db@example.com", name="Db")
        tenant = Tenant(name="Db tenant")
        session.add_all([user, tenant])
        session.flush()
        session.add(TenantUser(tenant_id=tenant.id, user_id=user.id, role="OWNER"))

    with pytest.raises(IntegrityError):
        with session_scope(domain.factory) as session:
            user = session.scalar(select(User).where(User.clerk_user_id == "db_user"))
            tenant = session.scalar(select(Tenant).where(Tenant.name == "Db tenant"))
            assert user is not None and tenant is not None
            session.add(TenantUser(tenant_id=tenant.id, user_id=user.id, role="MEMBER"))
            session.flush()

    with pytest.raises(IntegrityError):
        with session_scope(domain.factory) as session:
            user = session.scalar(select(User).where(User.clerk_user_id == "db_user"))
            tenant = session.scalar(select(Tenant).where(Tenant.name == "Db tenant"))
            assert user is not None and tenant is not None
            session.add(TenantUser(tenant_id=tenant.id, user_id=user.id, role="ADMIN"))
            session.flush()


def _bootstrap(
    domain: DomainApp,
    clerk_user_id: str,
    email: str,
    name: str,
    tenant_name: str,
) -> dict[str, str]:
    domain.login(clerk_user_id, email, name)
    me = domain.client.get("/me")
    assert me.status_code == 200, me.text
    created = domain.client.post("/tenants", json={"name": tenant_name})
    assert created.status_code == 201, created.text
    me = domain.client.get("/me")
    assert me.status_code == 200
    assert me.json()["tenant"]["name"] == tenant_name
    return {
        "user_id": me.json()["user"]["id"],
        "tenant_id": me.json()["tenant"]["id"],
    }


def test_identity_override_is_not_the_production_dependency() -> None:
    assert get_identity.__module__ == "pulse_api.deps"
    assert get_session.__module__ == "pulse_api.deps"
