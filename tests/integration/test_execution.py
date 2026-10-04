"""Low-risk execution is idempotent and cannot send or pay."""

from sqlalchemy import func, select
from tests.domain_app import DomainApp
from tests.integration.test_attention_engine import _owner

from pulse_api.db import session_scope
from pulse_api.models import AttentionItem, AuditLog


def test_reminder_executes_once_for_the_same_key(domain: DomainApp) -> None:
    _owner(domain)
    created = domain.client.post(
        "/actions",
        json={
            "action_type": "create_reminder",
            "input": {"title": "Call Acme", "due_at": "2026-10-06T09:00:00+00:00"},
        },
    )
    assert created.status_code == 201, created.text
    action_id = created.json()["id"]
    body = {"idempotency_key": "reminder-1"}
    first = domain.client.post(f"/actions/{action_id}/execute", json=body)
    second = domain.client.post(f"/actions/{action_id}/execute", json=body)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "COMPLETED"
    assert second.json()["result"] == first.json()["result"]
    with session_scope(domain.factory) as session:
        assert session.scalar(select(func.count()).select_from(AttentionItem)) == 1
        audit = session.scalars(select(AuditLog)).all()
        assert len(audit) == 1
        assert audit[0].result_code == "completed"
        assert "Call Acme" not in str(audit[0].metadata_json)


def test_send_and_unapproved_draft_are_refused(domain: DomainApp) -> None:
    _owner(domain)
    send = domain.client.post("/actions", json={"action_type": "send_email", "input": {}})
    refused = domain.client.post(
        f"/actions/{send.json()['id']}/execute",
        json={"idempotency_key": "send-1"},
    )
    assert refused.status_code == 403
    draft = domain.client.post(
        "/actions",
        json={"action_type": "store_draft", "input": {"text": "Hello"}},
    )
    needs_approval = domain.client.post(
        f"/actions/{draft.json()['id']}/execute",
        json={"idempotency_key": "draft-1"},
    )
    assert needs_approval.status_code == 403
    approved = domain.client.post(
        f"/actions/{draft.json()['id']}/approvals",
        json={"status": "APPROVED"},
    )
    assert approved.status_code == 201
    stored = domain.client.post(
        f"/actions/{draft.json()['id']}/execute",
        json={"idempotency_key": "draft-1"},
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["result"]["draft"] == "Hello"
    assert stored.json()["status"] == "COMPLETED"
