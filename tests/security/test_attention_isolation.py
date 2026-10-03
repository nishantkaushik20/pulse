"""Tenant A events cannot create or reveal attention items for Tenant B."""

from uuid import UUID

from sqlalchemy import func, select
from tests.gmail_app import GmailApp
from tests.integration.test_attention_engine import _connection, _sync_one

from pulse_api.attention_engine import AttentionEngine
from pulse_api.context import TenantContext
from pulse_api.db import session_scope
from pulse_api.models import AttentionItem, BusinessEvent, Message, TenantRole


def test_other_tenant_cannot_read_or_derive_an_email_attention_item(gmail: GmailApp) -> None:
    connection_id = _connection(gmail)
    _sync_one(gmail, connection_id)
    owner = gmail.domain.client.get("/me").json()
    item_id = gmail.domain.client.get("/attention-items").json()["items"][0]["id"]

    gmail.domain.login("user_b", "b@example.com", "Bea")
    assert gmail.domain.client.get("/me").status_code == 200
    created = gmail.domain.client.post("/tenants", json={"name": "Tenant B"})
    assert created.status_code == 201, created.text
    intruder = gmail.domain.client.get("/me").json()

    hidden = gmail.domain.client.get(f"/attention-items/{item_id}")
    listed = gmail.domain.client.get("/attention-items")
    assert hidden.status_code == 404
    assert listed.json()["items"] == []
    assert "Hello subject" not in hidden.text
    assert "SECRET-BODY-TEXT" not in hidden.text

    with session_scope(gmail.domain.factory) as session:
        event = session.scalar(select(BusinessEvent))
        message = session.scalar(select(Message))
        assert event is not None and message is not None
        intruder_engine = AttentionEngine(
            session,
            TenantContext(
                user_id=UUID(intruder["user"]["id"]),
                tenant_id=UUID(intruder["tenant"]["id"]),
                role=TenantRole.OWNER,
            ),
        )
        assert intruder_engine.apply(event) == []
        forged = BusinessEvent(
            tenant_id=UUID(intruder["tenant"]["id"]),
            event_type="EMAIL_RECEIVED",
            entity_type="message",
            entity_id=message.id,
            source="gmail",
            occurred_at=event.occurred_at,
            data={"provider": "gmail", "external_message_id": "msg-inbox"},
        )
        assert intruder_engine.apply(forged) == []
        assert session.scalar(select(func.count()).select_from(AttentionItem)) == 1
        only = session.scalar(select(AttentionItem))
        assert only is not None
        assert only.tenant_id == UUID(owner["tenant"]["id"])
        assert only.entity_id == message.id
