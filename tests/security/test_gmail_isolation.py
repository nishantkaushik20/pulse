"""Tenant A cannot read Tenant B Gmail rows, even with a known id."""

from uuid import UUID

from sqlalchemy import select
from tests.gmail_app import GmailApp
from tests.integration.test_gmail import _bootstrap, _callback, _connect, _inbox

from pulse_api.config import get_settings
from pulse_api.context import TenantContext
from pulse_api.db import session_scope
from pulse_api.errors import NotFoundError
from pulse_api.gmail.repository import (
    GmailConnectionRepository,
    MessageRepository,
    MessageThreadRepository,
)
from pulse_api.gmail.service import GmailService
from pulse_api.models import GmailConnection, Message, MessageThread, TenantRole


def _seed(gmail: GmailApp) -> dict[str, str]:
    owner = _bootstrap(gmail, "user_a", "a@example.com", "Ada", "Tenant A")
    assert _callback(gmail, _connect(gmail)[0]).status_code == 302
    connection_id = gmail.domain.client.get("/integrations/gmail/connections").json()["items"][0][
        "id"
    ]
    gmail.fake.list_ids = ["msg-secret"]
    gmail.fake.messages = {"msg-secret": _inbox("msg-secret", plain="tenant-a-body")}
    synced = gmail.domain.client.post(f"/integrations/gmail/connections/{connection_id}/sync")
    assert synced.status_code == 200, synced.text
    message = gmail.domain.client.get("/messages").json()["items"][0]
    thread = gmail.domain.client.get("/message-threads").json()["items"][0]
    return {
        "user_id": owner["user_id"],
        "tenant_id": owner["tenant_id"],
        "connection_id": connection_id,
        "message_id": message["id"],
        "thread_id": thread["id"],
    }


def test_api_hides_other_tenant_gmail_rows(gmail: GmailApp) -> None:
    seeded = _seed(gmail)
    _bootstrap(gmail, "user_b", "b@example.com", "Bea", "Tenant B")

    connection = gmail.domain.client.get("/integrations/gmail/connections")
    message = gmail.domain.client.get(f"/messages/{seeded['message_id']}")
    thread = gmail.domain.client.get(f"/message-threads/{seeded['thread_id']}")
    sync = gmail.domain.client.post(
        f"/integrations/gmail/connections/{seeded['connection_id']}/sync"
    )
    messages = gmail.domain.client.get("/messages")
    threads = gmail.domain.client.get("/message-threads")

    assert connection.json()["items"] == []
    assert message.status_code == 404
    assert thread.status_code == 404
    assert sync.status_code == 404
    assert messages.json()["items"] == []
    assert threads.json()["items"] == []
    assert "tenant-a-body" not in message.text
    assert seeded["tenant_id"] not in message.text


def test_repository_and_service_hide_other_tenant_gmail_rows(gmail: GmailApp) -> None:
    seeded = _seed(gmail)
    other = _bootstrap(gmail, "user_b", "b@example.com", "Bea", "Tenant B")
    tenant_b = UUID(other["tenant_id"])
    settings = get_settings()

    with session_scope(gmail.domain.factory) as session:
        assert (
            GmailConnectionRepository(session, tenant_b).get(UUID(seeded["connection_id"])) is None
        )
        assert MessageRepository(session, tenant_b).get(UUID(seeded["message_id"])) is None
        assert MessageThreadRepository(session, tenant_b).get(UUID(seeded["thread_id"])) is None
        owned = session.scalar(
            select(GmailConnection).where(GmailConnection.tenant_id == UUID(seeded["tenant_id"]))
        )
        message = session.scalar(select(Message).where(Message.id == UUID(seeded["message_id"])))
        thread = session.scalar(
            select(MessageThread).where(MessageThread.id == UUID(seeded["thread_id"]))
        )
        assert owned is not None and message is not None and thread is not None
        service = GmailService(
            session,
            TenantContext(
                user_id=UUID(other["user_id"]),
                tenant_id=tenant_b,
                role=TenantRole.MEMBER,
            ),
            settings,
            gmail.store,
            gmail.fake,
        )
        try:
            service.get_message(UUID(seeded["message_id"]))
        except NotFoundError:
            pass
        else:
            raise AssertionError("other tenant read a message")
        try:
            service.get_thread(UUID(seeded["thread_id"]))
        except NotFoundError:
            pass
        else:
            raise AssertionError("other tenant read a thread")
        try:
            service.sync(UUID(seeded["connection_id"]))
        except NotFoundError:
            pass
        else:
            raise AssertionError("other tenant synced a connection")
