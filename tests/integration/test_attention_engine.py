"""Deterministic EMAIL_RECEIVED attention rule."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from tests.domain_app import DomainApp
from tests.gmail_app import GmailApp
from tests.integration.test_gmail import _bootstrap, _callback, _connect, _inbox
from tests.records import record_attention

from pulse_api.attention_engine import AttentionEngine
from pulse_api.context import TenantContext
from pulse_api.db import session_scope
from pulse_api.errors import ConflictError
from pulse_api.models import (
    AttentionItem,
    BusinessEvent,
    Message,
    TenantRole,
    utcnow,
)
from pulse_api.repositories import AttentionRepository


def _connection(gmail: GmailApp) -> str:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    assert _callback(gmail, _connect(gmail)[0]).status_code == 302
    return str(gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0]["id"])


def _sync_one(gmail: GmailApp, connection_id: str) -> None:
    gmail.fake.list_ids = ["msg-inbox"]
    gmail.fake.messages = {"msg-inbox": _inbox("msg-inbox", plain="SECRET-BODY-TEXT")}
    synced = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")
    assert synced.status_code == 200, synced.text


def test_repeat_evaluation_does_not_duplicate(gmail: GmailApp) -> None:
    connection_id = _connection(gmail)
    _sync_one(gmail, connection_id)
    me = gmail.domain.client.get("/me").json()

    with session_scope(gmail.domain.factory) as session:
        event = session.scalar(select(BusinessEvent))
        assert event is not None
        created = AttentionEngine(
            session,
            TenantContext(
                user_id=UUID(me["user"]["id"]),
                tenant_id=UUID(me["tenant"]["id"]),
                role=TenantRole.OWNER,
            ),
        ).apply(event)
        assert created == []

    with session_scope(gmail.domain.factory) as session:
        assert session.scalar(select(func.count()).select_from(AttentionItem)) == 1


def test_unrelated_event_creates_no_attention_item(domain: DomainApp) -> None:
    created = UUID(_owner(domain))
    with session_scope(domain.factory) as session:
        event = BusinessEvent(
            tenant_id=created,
            event_type="NOTE_ADDED",
            entity_type="customer",
            entity_id=uuid4(),
            source="api",
            occurred_at=utcnow(),
            data={"note": "hello"},
        )
        session.add(event)
        session.flush()
        created_ids = AttentionEngine(
            session,
            TenantContext(user_id=uuid4(), tenant_id=created, role=TenantRole.MEMBER),
        ).apply(event)
        assert created_ids == []
        assert session.scalar(select(func.count()).select_from(AttentionItem)) == 0


def test_failed_attention_insert_rolls_back_the_message_and_event(
    gmail: GmailApp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_id = _connection(gmail)

    def fail(self: AttentionRepository, **_kwargs: object) -> None:
        raise RuntimeError("attention failed")

    monkeypatch.setattr(AttentionRepository, "insert_idempotent", fail)
    gmail.fake.list_ids = ["msg-inbox"]
    gmail.fake.messages = {"msg-inbox": _inbox("msg-inbox", plain="SECRET-BODY-TEXT")}

    with pytest.raises(RuntimeError, match="attention failed"):
        gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")
    with session_scope(gmail.domain.factory) as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 0
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
        assert session.scalar(select(func.count()).select_from(AttentionItem)) == 0


def test_public_attention_and_event_writes_are_closed(domain: DomainApp) -> None:
    _owner(domain)
    entity_id = str(uuid4())
    attention = domain.client.post(
        "/attention-items",
        json={"type": "manual", "title": "Call back", "tenant_id": str(uuid4())},
    )
    event = domain.client.post(
        "/business-events",
        json={
            "event_type": "EMAIL_RECEIVED",
            "entity_type": "message",
            "entity_id": entity_id,
            "source": "gmail",
            "data": {},
        },
    )
    assert attention.status_code == 403
    assert event.status_code == 403
    assert domain.client.get("/attention").json()["items"] == []


def test_duplicate_service_source_is_a_conflict(domain: DomainApp) -> None:
    _owner(domain)
    entity_id = uuid4()
    record_attention(
        domain,
        title="New email needs review",
        item_type="email_review",
        entity_type="message",
        entity_id=entity_id,
    )
    with pytest.raises(ConflictError):
        record_attention(
            domain,
            title="New email needs review",
            item_type="email_review",
            entity_type="message",
            entity_id=entity_id,
        )
    listed = domain.client.get("/attention-items")
    assert len(listed.json()["items"]) == 1


def test_exact_email_matches_a_customer_and_unknown_senders_stay_unmatched(
    gmail: GmailApp,
) -> None:
    connection_id = _connection(gmail)
    created = gmail.domain.client.post(
        "/customers",
        json={"name": "Pat Co", "email": "Pat@Example.com"},
    )
    assert created.status_code == 201, created.text
    _sync_one(gmail, connection_id)
    item = gmail.domain.client.get("/attention").json()["items"][0]
    assert item["customer_name"] == "Pat Co"
    assert item["match_method"] == "exact_email"
    assert item["customer_id"] == created.json()["id"]
    assert "Customer: Pat Co" in item["description"]
    assert "SECRET-BODY-TEXT" not in gmail.domain.client.get("/attention").text
    customers = gmail.domain.client.get("/customers").json()["items"]
    assert len(customers) == 1


def test_sync_does_not_invent_a_customer_for_an_unknown_sender(gmail: GmailApp) -> None:
    connection_id = _connection(gmail)
    _sync_one(gmail, connection_id)
    item = gmail.domain.client.get("/attention").json()["items"][0]
    assert item["customer_name"] is None
    assert item["match_method"] is None
    assert gmail.domain.client.get("/customers").json()["items"] == []


def _owner(domain: DomainApp) -> str:
    domain.login("user_a", "a@example.com", "Ada")
    assert domain.client.get("/me").status_code == 200
    created = domain.client.post("/tenants", json={"name": "Tenant A"})
    assert created.status_code == 201, created.text
    me = domain.client.get("/me")
    return me.json()["tenant"]["id"]
