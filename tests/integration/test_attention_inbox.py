"""Open attention inbox: ordering, resolve, and safe Gmail context."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from tests.domain_app import DomainApp
from tests.gmail_app import GmailApp
from tests.integration.test_attention_engine import _connection, _owner, _sync_one
from tests.records import record_attention

from pulse_api.db import session_scope
from pulse_api.models import AttentionItem, AttentionStatus


def test_inbox_orders_open_items_and_hides_resolved(domain: DomainApp) -> None:
    _owner(domain)
    high = record_attention(domain, priority="HIGH", title="Confirm the delivery")
    medium_old = record_attention(domain, priority="MEDIUM", title="Read the older note")
    medium_new = record_attention(domain, priority="MEDIUM", title="Read the newer note")
    low = record_attention(domain, priority="LOW", title="File the receipt")
    resolved = record_attention(domain, priority="HIGH", title="Already handled")
    _stamp(
        domain,
        {
            high: datetime(2026, 1, 15, tzinfo=UTC),
            medium_old: datetime(2026, 1, 1, tzinfo=UTC),
            medium_new: datetime(2026, 2, 2, tzinfo=UTC),
            low: datetime(2026, 3, 3, tzinfo=UTC),
            resolved: datetime(2026, 3, 4, tzinfo=UTC),
        },
    )
    assert domain.client.post(f"/attention/{resolved}/resolve").status_code == 200

    listed = domain.client.get("/attention", params={"tenant_id": str(uuid4())})
    assert listed.status_code == 200, listed.text
    titles = [item["title"] for item in listed.json()["items"]]
    assert titles == [
        "Confirm the delivery",
        "Read the newer note",
        "Read the older note",
        "File the receipt",
    ]
    assert listed.json()["items"][0]["priority"] == "HIGH"
    assert "tenant_id" not in listed.text
    again = domain.client.get("/attention")
    assert again.json() == listed.json()


def test_resolve_is_idempotent_and_keeps_the_row(domain: DomainApp) -> None:
    _owner(domain)
    item_id = record_attention(domain, title="New email needs review")

    first = domain.client.post(
        f"/attention/{item_id}/resolve",
        json={"tenant_id": str(uuid4()), "status": "OPEN"},
    )
    second = domain.client.post(f"/attention/{item_id}/resolve")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == AttentionStatus.RESOLVED
    assert second.json()["id"] == item_id
    assert second.json()["status"] == AttentionStatus.RESOLVED
    assert "tenant_id" not in first.json()
    assert domain.client.get("/attention").json()["items"] == []
    stored = domain.client.get(f"/attention-items/{item_id}")
    assert stored.status_code == 200
    assert stored.json()["status"] == AttentionStatus.RESOLVED
    with session_scope(domain.factory) as session:
        assert session.scalar(select(func.count()).select_from(AttentionItem)) == 1
        row = session.get(AttentionItem, UUID(item_id))
        assert row is not None
        assert row.status == AttentionStatus.RESOLVED


def test_email_inbox_returns_sender_and_subject_without_the_body(gmail: GmailApp) -> None:
    connection_id = _connection(gmail)
    _sync_one(gmail, connection_id)

    listed = gmail.domain.client.get("/attention")
    assert listed.status_code == 200, listed.text
    item = listed.json()["items"][0]
    assert item["type"] == "email_review"
    assert item["title"] == "New email needs review"
    assert item["priority"] == "MEDIUM"
    assert item["status"] == "OPEN"
    assert item["source"] == "gmail"
    assert "thread_id" in item
    assert item["customer_name"] is None
    assert item["match_method"] is None
    assert "From: Pat <pat@example.com>" in item["description"]
    assert "Subject: Hello subject" in item["description"]
    assert "SECRET-BODY-TEXT" not in listed.text
    assert "SECRET-HTML" not in listed.text
    assert "ada@gmail.com" not in listed.text
    assert "snippet text" not in listed.text
    assert "body_text" not in listed.text
    assert "external_message_id" not in listed.text
    assert "access_token" not in listed.text
    assert "refresh_token" not in listed.text
    assert "tenant_id" not in listed.text


def test_briefing_returns_at_most_five_open_items(domain: DomainApp) -> None:
    _owner(domain)
    for index in range(6):
        record_attention(domain, title=f"Item {index}")
    listed = domain.client.get("/briefing")
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 5
    assert "body_text" not in listed.text


def test_dismiss_hides_the_item_and_keeps_the_row(domain: DomainApp) -> None:
    _owner(domain)
    item_id = record_attention(domain, title="Newsletter")
    first = domain.client.post(f"/attention/{item_id}/dismiss", json={"reason": "not_relevant"})
    second = domain.client.post(f"/attention/{item_id}/dismiss", json={"reason": "not_relevant"})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["dismiss_reason"] == "not_relevant"
    assert second.json()["id"] == first.json()["id"]
    assert domain.client.get("/attention").json()["items"] == []
    stored = domain.client.get(f"/attention-items/{item_id}")
    assert stored.json()["status"] == AttentionStatus.RESOLVED
    assert stored.json()["dismiss_reason"] == "not_relevant"


def _stamp(domain: DomainApp, moments: dict[str, datetime]) -> None:
    with session_scope(domain.factory) as session:
        for item_id, moment in moments.items():
            row = session.get(AttentionItem, UUID(item_id))
            assert row is not None
            row.created_at = moment
            row.updated_at = moment
