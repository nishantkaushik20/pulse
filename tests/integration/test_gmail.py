"""Gmail connect, callback, and bounded sync."""

import base64
import json
import logging
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.gmail_app import TEST_KEY, GmailApp
from tests.gmail_fakes import AUTH_CODE, PLAINTEXT_ACCESS, PLAINTEXT_REFRESH

from pulse_api.config import get_settings
from pulse_api.crypto import decrypt_token
from pulse_api.db import session_scope
from pulse_api.deps import get_identity, get_session
from pulse_api.gmail.client import GMAIL_READONLY_SCOPE, SYNC_MAX_MESSAGES, SYNC_QUERY
from pulse_api.gmail.deps import get_gmail_client, get_oauth_state_store
from pulse_api.gmail.service import _pkce_challenge
from pulse_api.logging import JsonFormatter
from pulse_api.main import create_app
from pulse_api.models import AttentionItem, BusinessEvent, GmailConnection, Message, utcnow


def _encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _inbox(
    message_id: str,
    *,
    thread_id: str = "thread-1",
    labels: list[str] | None = None,
    plain: str = "Hello plain",
    internal_date: object = "1710000000000",
) -> dict[str, object]:
    return {
        "id": message_id,
        "threadId": thread_id,
        "labelIds": ["INBOX"] if labels is None else labels,
        "snippet": "snippet text",
        "internalDate": internal_date,
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "Pat <Pat@Example.com>"},
                {"name": "To", "value": "Ada <ada@gmail.com>"},
                {"name": "Subject", "value": "Hello subject"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _encoded(plain)}},
                {"mimeType": "text/html", "body": {"data": _encoded("<b>SECRET-HTML</b>")}},
                {
                    "mimeType": "application/pdf",
                    "filename": "invoice.pdf",
                    "body": {"attachmentId": "att-1", "data": _encoded("ATTACH-BYTES")},
                },
            ],
        },
    }


def _bootstrap(
    gmail: GmailApp, clerk_user_id: str, email: str, name: str, tenant: str
) -> dict[str, str]:
    gmail.domain.login(clerk_user_id, email, name)
    assert gmail.domain.client.get("/me").status_code == 200
    created = gmail.domain.client.post("/tenants", json={"name": tenant})
    assert created.status_code == 201, created.text
    me = gmail.domain.client.get("/me")
    assert me.status_code == 200
    return {"user_id": me.json()["user"]["id"], "tenant_id": me.json()["tenant"]["id"]}


def _connect(gmail: GmailApp) -> tuple[str, str]:
    started = gmail.domain.client.post("/integrations/gmail/connect")
    assert started.status_code == 200, started.text
    parsed = urlparse(started.json()["authorization_url"])
    query = parse_qs(parsed.query)
    return query["state"][0], query["code_challenge"][0]


def _callback(gmail: GmailApp, state: str, **extra: str) -> object:
    params = {"code": AUTH_CODE, "state": state, **extra}
    return gmail.domain.client.get(
        "/integrations/gmail/callback",
        params=params,
        follow_redirects=False,
    )


def _log_handler() -> logging.Handler:
    handler = logging.Handler()
    handler.setFormatter(JsonFormatter())
    lines: list[str] = []

    def emit(record: logging.LogRecord) -> None:
        lines.append(handler.format(record))

    handler.emit = emit  # type: ignore[method-assign]
    handler.lines = lines  # type: ignore[attr-defined]
    logging.getLogger().addHandler(handler)
    return handler


def test_connect_stores_state_and_uses_pkce(gmail: GmailApp) -> None:
    owner = _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    handler = _log_handler()
    state, challenge = _connect(gmail)
    raw, _expires = gmail.store.items[state]
    stored = json.loads(raw)

    assert stored["user_id"] == owner["user_id"]
    assert stored["tenant_id"] == owner["tenant_id"]
    assert challenge == _pkce_challenge(stored["pkce_verifier"])
    assert "access_token" not in stored
    assert "refresh_token" not in stored

    response = _callback(gmail, state)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location == "http://localhost:3000/?gmail=connected"
    assert AUTH_CODE not in location
    assert state not in location
    assert gmail.fake.exchanged[0][0] == AUTH_CODE
    assert gmail.fake.exchanged[0][1] == stored["pkce_verifier"]
    logged = "\n".join(handler.lines)  # type: ignore[attr-defined]
    assert AUTH_CODE not in logged
    assert state not in logged
    assert PLAINTEXT_ACCESS not in logged
    assert PLAINTEXT_REFRESH not in logged
    assert stored["pkce_verifier"] not in logged
    assert TEST_KEY not in logged
    logging.getLogger().removeHandler(handler)


def test_state_is_single_use_and_missing_or_invalid_state_is_rejected(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    state, _challenge = _connect(gmail)
    first = _callback(gmail, state)
    second = _callback(gmail, state)
    missing = gmail.domain.client.get("/integrations/gmail/callback", follow_redirects=False)
    invalid = gmail.domain.client.get(
        "/integrations/gmail/callback",
        params={"code": AUTH_CODE, "state": "not-a-real-state"},
        follow_redirects=False,
    )

    assert first.status_code == 302
    assert second.headers["location"].endswith("reason=invalid_state")
    assert missing.headers["location"].endswith("reason=invalid_state")
    assert invalid.headers["location"].endswith("reason=invalid_state")
    assert AUTH_CODE not in second.headers["location"]
    assert AUTH_CODE not in invalid.headers["location"]


def test_state_expires(gmail: GmailApp) -> None:
    clock = {"now": 0.0}
    from pulse_api.gmail.state_store import MemoryOAuthStateStore

    store = MemoryOAuthStateStore(clock=lambda: clock["now"])
    gmail.domain.client.app.dependency_overrides[get_oauth_state_store] = lambda: store
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    state, _challenge = _connect(gmail)
    clock["now"] = 601.0

    response = _callback(gmail, state)

    assert response.headers["location"].endswith("reason=invalid_state")
    assert gmail.fake.exchanged == []


def test_callback_binds_stored_tenant_not_query_tenant(gmail: GmailApp) -> None:
    owner = _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    state, _challenge = _connect(gmail)
    other = _bootstrap(gmail, "user_b", "b@example.com", "Bea", "Tenant B")
    response = _callback(
        gmail,
        state,
        tenant_id=other["tenant_id"],
        user_id=other["user_id"],
    )

    assert response.headers["location"].endswith("gmail=connected")
    assert other["tenant_id"] not in response.headers["location"]
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        assert row is not None
        assert str(row.tenant_id) == owner["tenant_id"]
        assert str(row.connected_by) == owner["user_id"]
    gmail.domain.login("user_b", "b@example.com", "Bea")
    listed = gmail.domain.client.get("/integrations/gmail/connections")
    assert listed.status_code == 200
    assert listed.json()["items"] == []


def test_callback_does_not_require_clerk(gmail: GmailApp) -> None:
    app = create_app()
    app.dependency_overrides[get_session] = gmail.domain.client.app.dependency_overrides[
        get_session
    ]
    app.dependency_overrides[get_oauth_state_store] = lambda: gmail.store
    app.dependency_overrides[get_gmail_client] = lambda: gmail.fake
    with TestClient(app) as client:
        response = client.get(
            "/integrations/gmail/callback",
            params={"code": AUTH_CODE, "state": "missing-state"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"].endswith("reason=invalid_state")
    assert get_identity not in app.dependency_overrides


def test_denied_and_google_error_consume_state(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    denied_state, _challenge = _connect(gmail)
    denied = gmail.domain.client.get(
        "/integrations/gmail/callback",
        params={"state": denied_state, "error": "access_denied"},
        follow_redirects=False,
    )
    replay = _callback(gmail, denied_state)
    failed_state, _challenge = _connect(gmail)
    failed = gmail.domain.client.get(
        "/integrations/gmail/callback",
        params={"state": failed_state, "error": "server_error_with_secret"},
        follow_redirects=False,
    )

    assert denied.headers["location"].endswith("reason=denied")
    assert "access_denied" not in denied.headers["location"]
    assert replay.headers["location"].endswith("reason=invalid_state")
    assert failed.headers["location"].endswith("reason=failed")
    assert "server_error_with_secret" not in failed.headers["location"]


def test_other_tenant_mailbox_is_generic_conflict(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    state, _challenge = _connect(gmail)
    assert _callback(gmail, state).headers["location"].endswith("gmail=connected")

    _bootstrap(gmail, "user_b", "b@example.com", "Bea", "Tenant B")
    gmail.fake.profile = gmail.fake.profile.__class__(email="ada@gmail.com", history_id="other")
    state_b, _challenge = _connect(gmail)
    conflict = _callback(gmail, state_b)

    assert conflict.headers["location"].endswith("reason=conflict")
    assert "Tenant A" not in conflict.headers["location"]
    gmail.domain.login("user_b", "b@example.com", "Bea")
    assert gmail.domain.client.get("/integrations/gmail/connections").json()["items"] == []


def test_same_tenant_reconnect_updates_one_row(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    _callback(gmail, _connect(gmail)[0])
    gmail.fake.access_token = "second-access-token"
    gmail.fake.refresh_token = "second-refresh-token"
    _callback(gmail, _connect(gmail)[0])

    with session_scope(gmail.domain.factory) as session:
        rows = session.scalars(select(GmailConnection)).all()
        assert len(rows) == 1
        assert rows[0].status == "ACTIVE"
        assert (
            decrypt_token(TEST_KEY, rows[0].encrypted_refresh_token or b"")
            == "second-refresh-token"
        )


def test_tokens_are_encrypted_at_rest(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    _callback(gmail, _connect(gmail)[0])
    listed = gmail.domain.client.get("/integrations/gmail/connections")

    assert PLAINTEXT_REFRESH not in listed.text
    assert PLAINTEXT_ACCESS not in listed.text
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        assert row is not None
        assert row.encrypted_refresh_token is not None
        assert PLAINTEXT_REFRESH.encode() not in row.encrypted_refresh_token
        assert decrypt_token(TEST_KEY, row.encrypted_refresh_token) == PLAINTEXT_REFRESH
        assert row.scopes == GMAIL_READONLY_SCOPE
        assert row.history_id == "hist-connect"


def test_member_cannot_connect_or_disconnect_and_can_sync(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    gmail.domain.login("user_m", "m@example.com", "Mo")
    assert gmail.domain.client.get("/me").status_code == 200
    member_id = gmail.domain.client.get("/me").json()["user"]["id"]
    gmail.domain.login("user_a", "a@example.com", "Ada")
    added = gmail.domain.client.post(
        "/tenant/members",
        json={"user_id": member_id, "role": "MEMBER"},
    )
    assert added.status_code == 201, added.text
    response = _callback(gmail, _connect(gmail)[0])
    assert response.status_code == 302
    connection_id = gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0][
        "id"
    ]

    gmail.domain.login("user_m", "m@example.com", "Mo")
    assert gmail.domain.client.post("/integrations/gmail/connect").status_code == 403
    denied = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/disconnect")
    assert denied.status_code == 403
    synced = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")
    assert synced.status_code == 200
    assert synced.json()["examined"] == 0


def test_sync_ingests_inbox_once_and_skips_sent(
    gmail: GmailApp,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    _callback(gmail, _connect(gmail)[0])
    connection_id = gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0][
        "id"
    ]
    gmail.fake.list_ids = ["msg-inbox", "msg-sent", "msg-other"]
    gmail.fake.messages = {
        "msg-inbox": _inbox("msg-inbox", plain="SECRET-BODY-TEXT"),
        "msg-sent": _inbox("msg-sent", labels=["SENT", "INBOX"], plain="sent body"),
        "msg-other": _inbox("msg-other", labels=["CATEGORY_PROMOTIONS"], plain="promo"),
    }
    caplog.set_level(logging.INFO)
    first = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")
    second = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")

    assert first.status_code == 200, first.text
    assert first.json() == {"examined": 3, "ingested": 1, "skipped": 2}
    assert second.json()["ingested"] == 0
    assert gmail.fake.last_query == SYNC_QUERY
    assert gmail.fake.last_limit == SYNC_MAX_MESSAGES
    assert gmail.fake.refresh_calls == 0
    assert "SECRET-BODY-TEXT" not in caplog.text
    assert "SECRET-HTML" not in caplog.text
    listed = gmail.domain.client.get("/messages")
    assert "SECRET-BODY-TEXT" not in listed.text
    detail = gmail.domain.client.get(f"/messages/{listed.json()['items'][0]['id']}")
    assert detail.json()["body_text"] == "SECRET-BODY-TEXT"
    assert "SECRET-HTML" not in detail.json()["body_text"]
    assert "ATTACH-BYTES" not in detail.json()["body_text"]
    with session_scope(gmail.domain.factory) as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 1
        events = session.scalars(select(BusinessEvent)).all()
        assert len(events) == 1
        assert events[0].event_type == "EMAIL_RECEIVED"
        assert events[0].entity_type == "message"
        assert events[0].source == "gmail"
        assert events[0].entity_id == UUID(detail.json()["id"])
        assert events[0].data == {
            "provider": "gmail",
            "external_message_id": "msg-inbox",
            "external_thread_id": "thread-1",
        }
        items = session.scalars(select(AttentionItem)).all()
        assert len(items) == 1
        assert items[0].status == "OPEN"
        assert items[0].priority == "MEDIUM"
        assert items[0].item_type == "email_review"
        assert items[0].entity_type == "message"
        assert items[0].entity_id == events[0].entity_id
        assert items[0].title == "New email needs review"
        assert items[0].description is not None
        assert "SECRET-BODY-TEXT" not in items[0].description
        assert "Hello subject" in items[0].description
    listed_attention = gmail.domain.client.get("/attention-items")
    assert listed_attention.status_code == 200
    assert len(listed_attention.json()["items"]) == 1
    assert "SECRET-BODY-TEXT" not in listed_attention.text
    assert "SECRET-BODY-TEXT" not in caplog.text


def test_refresh_keeps_existing_refresh_token(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    _callback(gmail, _connect(gmail)[0])
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        assert row is not None
        row.access_token_expires_at = utcnow() + timedelta(seconds=30)
    connection_id = gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0][
        "id"
    ]
    synced = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")

    assert synced.status_code == 200, synced.text
    assert gmail.fake.refresh_calls == 1
    assert gmail.fake.listed_access == ["refreshed-access-token"]
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        assert row is not None
        assert decrypt_token(TEST_KEY, row.encrypted_refresh_token or b"") == PLAINTEXT_REFRESH
        assert (
            decrypt_token(TEST_KEY, row.encrypted_access_token or b"") == "refreshed-access-token"
        )


def test_invalid_grant_revokes_without_retry(
    gmail: GmailApp, caplog: pytest.LogCaptureFixture
) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    _callback(gmail, _connect(gmail)[0])
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        assert row is not None
        row.access_token_expires_at = utcnow() + timedelta(seconds=10)
    gmail.fake.fail_refresh = True
    connection_id = gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0][
        "id"
    ]
    caplog.set_level(logging.DEBUG)
    failed = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")
    again = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")

    assert failed.status_code == 409
    assert failed.json()["detail"] == "gmail authorization expired"
    assert again.status_code == 409
    assert gmail.fake.refresh_calls == 1
    assert gmail.fake.list_calls == 0
    assert "SUPER-GOOGLE-BODY" not in caplog.text
    assert PLAINTEXT_REFRESH not in caplog.text
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        assert row is not None
        assert row.status == "REVOKED"
        assert row.encrypted_access_token is None
        assert row.encrypted_refresh_token is None


def test_unavailable_keeps_committed_messages_and_sync_cursor(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    _callback(gmail, _connect(gmail)[0])
    connection_id = gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0][
        "id"
    ]
    gmail.fake.list_ids = ["msg-ok", "msg-fail"]
    gmail.fake.messages = {"msg-ok": _inbox("msg-ok", plain="kept")}
    gmail.fake.unavailable_on_get.add("msg-fail")

    failed = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")

    assert failed.status_code == 503
    assert failed.json()["detail"] == "gmail is unavailable"
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        messages = session.scalars(select(Message)).all()
        assert row is not None
        assert row.last_synced_at is None
        assert row.history_id == "hist-connect"
        assert row.status == "ACTIVE"
        assert row.last_error_code == "unavailable"
        assert len(messages) == 1
        assert messages[0].external_message_id == "msg-ok"


def test_bad_message_stops_without_dropping_earlier_rows(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    _callback(gmail, _connect(gmail)[0])
    connection_id = gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0][
        "id"
    ]
    gmail.fake.list_ids = ["msg-ok", "msg-bad", "msg-later"]
    gmail.fake.messages = {
        "msg-ok": _inbox("msg-ok"),
        "msg-bad": {"id": "", "threadId": "thread-1", "labelIds": ["INBOX"]},
        "msg-later": _inbox("msg-later"),
    }

    failed = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")

    assert failed.status_code == 409
    assert failed.json()["detail"] == "gmail message could not be stored"
    assert gmail.fake.get_calls == ["msg-ok", "msg-bad"]
    with session_scope(gmail.domain.factory) as session:
        ids = [row.external_message_id for row in session.scalars(select(Message)).all()]
        row = session.scalar(select(GmailConnection))
        assert ids == ["msg-ok"]
        assert row is not None
        assert row.last_synced_at is None


def test_disconnect_clears_tokens_and_keeps_messages(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    _callback(gmail, _connect(gmail)[0])
    connection_id = gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0][
        "id"
    ]
    gmail.fake.list_ids = ["msg-inbox"]
    gmail.fake.messages = {"msg-inbox": _inbox("msg-inbox")}
    assert (
        gmail.domain.client.post(
            f"/integrations/gmail/connections/{connection_id}/sync"
        ).status_code
        == 200
    )
    gmail.fake.fail_revoke = True

    disconnected = gmail.domain.client.post(
        f"/integrations/gmail/connections/{connection_id}/disconnect"
    )

    assert disconnected.status_code == 200
    assert disconnected.json()["status"] == "REVOKED"
    assert PLAINTEXT_REFRESH not in disconnected.text
    assert gmail.fake.revoked == [PLAINTEXT_REFRESH]
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        assert row is not None
        assert row.encrypted_refresh_token is None
        assert row.encrypted_access_token is None
        assert session.scalar(select(func.count()).select_from(Message)) == 1


def test_missing_encryption_key_returns_503(
    gmail: GmailApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    monkeypatch.delenv("INTEGRATION_ENCRYPTION_KEY")
    get_settings.cache_clear()

    response = gmail.domain.client.post("/integrations/gmail/connect")

    assert response.status_code == 503
    assert response.json()["detail"] == "gmail is not configured"
    assert AUTH_CODE not in response.text


def _connected(gmail: GmailApp) -> str:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    assert _callback(gmail, _connect(gmail)[0]).status_code == 302
    connection_id = gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0][
        "id"
    ]
    return str(connection_id)


def test_gmail_401_refreshes_once_and_retries_the_request(gmail: GmailApp) -> None:
    connection_id = _connected(gmail)
    gmail.fake.unauthorized_list = 1
    gmail.fake.list_ids = ["msg-inbox"]
    gmail.fake.messages = {"msg-inbox": _inbox("msg-inbox", plain="kept-after-refresh")}

    synced = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")

    assert synced.status_code == 200, synced.text
    assert synced.json()["ingested"] == 1
    assert gmail.fake.refresh_calls == 1
    assert gmail.fake.list_calls == 2
    assert gmail.fake.listed_access == [PLAINTEXT_ACCESS, "refreshed-access-token"]
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        assert row is not None
        assert row.status == "ACTIVE"
        assert row.encrypted_refresh_token is not None
        assert row.encrypted_access_token is not None


def test_repeated_gmail_401_does_not_revoke(gmail: GmailApp) -> None:
    connection_id = _connected(gmail)
    gmail.fake.unauthorized_list = 5

    failed = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")

    assert failed.status_code == 503
    assert failed.json()["detail"] == "gmail is unavailable"
    assert gmail.fake.refresh_calls == 1
    assert gmail.fake.list_calls == 2
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        assert row is not None
        assert row.status == "ACTIVE"
        assert row.last_synced_at is None
        assert row.encrypted_refresh_token is not None
        assert decrypt_token(TEST_KEY, row.encrypted_refresh_token) == PLAINTEXT_REFRESH


def test_gmail_401_then_invalid_grant_revokes_once(gmail: GmailApp) -> None:
    connection_id = _connected(gmail)
    gmail.fake.unauthorized_get.add("msg-inbox")
    gmail.fake.fail_refresh = True
    gmail.fake.list_ids = ["msg-inbox"]
    gmail.fake.messages = {"msg-inbox": _inbox("msg-inbox")}

    failed = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")

    assert failed.status_code == 409
    assert failed.json()["detail"] == "gmail authorization expired"
    assert gmail.fake.refresh_calls == 1
    assert gmail.fake.get_calls == ["msg-inbox"]
    with session_scope(gmail.domain.factory) as session:
        row = session.scalar(select(GmailConnection))
        assert row is not None
        assert row.status == "REVOKED"
        assert row.encrypted_access_token is None
        assert row.encrypted_refresh_token is None


def test_owner_can_purge_message_bodies(gmail: GmailApp) -> None:
    _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    _callback(gmail, _connect(gmail)[0])
    connection_id = gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0][
        "id"
    ]
    gmail.fake.list_ids = ["msg-inbox"]
    gmail.fake.messages = {"msg-inbox": _inbox("msg-inbox", plain="SECRET-BODY-TEXT")}
    synced = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")
    assert synced.status_code == 200
    message_id = gmail.domain.client.get("/messages").json()["items"][0]["id"]

    gmail.domain.login("user_m", "m@example.com", "Mo")
    assert gmail.domain.client.get("/me").status_code == 200
    member_id = gmail.domain.client.get("/me").json()["user"]["id"]
    gmail.domain.login("user_a", "a@example.com", "Ada")
    added = gmail.domain.client.post(
        "/tenant/members",
        json={"user_id": member_id, "role": "MEMBER"},
    )
    assert added.status_code == 201
    gmail.domain.login("user_m", "m@example.com", "Mo")
    denied = gmail.domain.client.post("/integrations/gmail/messages/purge")
    assert denied.status_code == 403

    gmail.domain.login("user_a", "a@example.com", "Ada")
    purged = gmail.domain.client.post("/integrations/gmail/messages/purge")
    assert purged.status_code == 200
    assert purged.json() == {"cleared": 1}
    detail = gmail.domain.client.get(f"/messages/{message_id}")
    assert detail.json()["body_text"] == ""
    assert detail.json()["snippet"] == ""
    assert "SECRET-BODY-TEXT" not in detail.text
