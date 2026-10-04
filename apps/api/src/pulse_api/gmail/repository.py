"""Tenant-scoped Gmail persistence. Message insert and EMAIL_RECEIVED share one transaction."""

from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from pulse_api.gmail.normalize import GMAIL_SOURCE, NormalizedMessage
from pulse_api.models import BusinessEvent, GmailConnection, Message, MessageThread, utcnow
from pulse_api.repositories import TenantRepository


class GmailConnectionRepository(TenantRepository[GmailConnection]):
    model = GmailConnection

    def get_by_mailbox(self, external_account_id: str) -> GmailConnection | None:
        statement = self._select().where(GmailConnection.external_account_id == external_account_id)
        return cast(GmailConnection | None, self._session.scalar(statement))

    def add(self, connection: GmailConnection) -> GmailConnection:
        return self._insert(connection)

    def other_tenant_owns_mailbox(self, external_account_id: str) -> bool:
        """True when some other tenant already connected this mailbox.

        The caller receives a boolean only. The other tenant id is not returned.
        """
        statement = (
            select(GmailConnection.id)
            .where(
                GmailConnection.external_account_id == external_account_id,
                GmailConnection.tenant_id != self._tenant_id,
            )
            .limit(1)
        )
        return self._session.scalar(statement) is not None


class MessageThreadRepository(TenantRepository[MessageThread]):
    model = MessageThread


class MessageRepository(TenantRepository[Message]):
    model = Message

    def get_many(self, message_ids: Sequence[UUID]) -> dict[UUID, Message]:
        if not message_ids:
            return {}
        statement = self._select().where(Message.id.in_(tuple(message_ids)))
        rows = self._session.scalars(statement).all()
        return {row.id: row for row in rows}

    def list_recent(self, *, limit: int, offset: int) -> Sequence[Message]:
        statement = (
            self._select()
            .order_by(Message.received_at.desc(), Message.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return cast(Sequence[Message], self._session.scalars(statement).all())

    def clear_bodies(self) -> int:
        count = self._session.scalar(
            select(func.count()).select_from(Message).where(Message.tenant_id == self._tenant_id)
        )
        self._session.execute(
            update(Message)
            .where(Message.tenant_id == self._tenant_id)
            .values(body_text="", snippet="")
        )
        self._session.flush()
        return int(count or 0)

    def ingest(self, message: NormalizedMessage) -> BusinessEvent | None:
        """Insert one inbox message and its EMAIL_RECEIVED event, or insert nothing.

        A conflict on (tenant_id, source, external_message_id) returns None and
        does not write a second event. The caller commits this unit of work.
        """
        thread_id = self._ensure_thread(message)
        message_id = uuid4()
        now = utcnow()
        statement = (
            _insert(self._session)(Message)
            .values(
                id=message_id,
                tenant_id=self._tenant_id,
                thread_id=thread_id,
                source=GMAIL_SOURCE,
                external_message_id=message.external_message_id,
                from_email=message.from_email,
                from_name=message.from_name,
                to_addresses=message.to_addresses,
                cc_addresses=message.cc_addresses,
                subject=message.subject,
                snippet=message.snippet,
                body_text=message.body_text,
                received_at=message.received_at,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "source", "external_message_id"])
            .returning(Message.id)
        )
        inserted = cast(UUID | None, self._session.execute(statement).scalar_one_or_none())
        if inserted is None:
            return None
        event = BusinessEvent(
            tenant_id=self._tenant_id,
            event_type="EMAIL_RECEIVED",
            entity_type="message",
            entity_id=inserted,
            source=GMAIL_SOURCE,
            occurred_at=message.received_at,
            data={
                "provider": GMAIL_SOURCE,
                "external_message_id": message.external_message_id,
                "external_thread_id": message.external_thread_id,
            },
        )
        self._session.add(event)
        self._session.flush()
        return event

    def _ensure_thread(self, message: NormalizedMessage) -> UUID:
        existing = self._find_thread(message.external_thread_id)
        if existing is not None:
            return existing.id
        thread_id = uuid4()
        now = utcnow()
        self._session.execute(
            _insert(self._session)(MessageThread)
            .values(
                id=thread_id,
                tenant_id=self._tenant_id,
                source=GMAIL_SOURCE,
                external_thread_id=message.external_thread_id,
                subject=message.subject,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "source", "external_thread_id"])
        )
        stored = self._find_thread(message.external_thread_id)
        if stored is None:
            raise RuntimeError("message thread was not stored")
        return stored.id

    def _find_thread(self, external_thread_id: str) -> MessageThread | None:
        statement = self._select_thread().where(
            MessageThread.external_thread_id == external_thread_id
        )
        return cast(MessageThread | None, self._session.scalar(statement))

    def _select_thread(self) -> Any:
        return select(MessageThread).where(
            MessageThread.tenant_id == self._tenant_id,
            MessageThread.source == GMAIL_SOURCE,
        )


def _insert(session: Session) -> Any:
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql_insert
    return sqlite_insert
