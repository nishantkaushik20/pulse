"""Gmail API responses. Ciphertext and OAuth tokens are not fields."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from pulse_api.models import GmailConnection, Message, MessageThread


class GmailConnectOut(BaseModel):
    authorization_url: str


class GmailConnectionOut(BaseModel):
    id: UUID
    external_account_id: str
    status: str
    scopes: str
    history_id: str | None
    last_synced_at: datetime | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: GmailConnection) -> "GmailConnectionOut":
        return cls(
            id=row.id,
            external_account_id=row.external_account_id,
            status=row.status,
            scopes=row.scopes,
            history_id=row.history_id,
            last_synced_at=row.last_synced_at,
            last_error_code=row.last_error_code,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class GmailConnectionList(BaseModel):
    items: list[GmailConnectionOut]


class GmailSyncOut(BaseModel):
    examined: int
    ingested: int
    skipped: int


class MessageThreadOut(BaseModel):
    id: UUID
    source: str
    external_thread_id: str
    subject: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: MessageThread) -> "MessageThreadOut":
        return cls(
            id=row.id,
            source=row.source,
            external_thread_id=row.external_thread_id,
            subject=row.subject,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class MessageThreadList(BaseModel):
    items: list[MessageThreadOut]


class MessageSummary(BaseModel):
    id: UUID
    thread_id: UUID
    source: str
    external_message_id: str
    from_email: str | None
    from_name: str | None
    subject: str
    snippet: str
    received_at: datetime
    created_at: datetime

    @classmethod
    def from_row(cls, row: Message) -> "MessageSummary":
        return cls(
            id=row.id,
            thread_id=row.thread_id,
            source=row.source,
            external_message_id=row.external_message_id,
            from_email=row.from_email,
            from_name=row.from_name,
            subject=row.subject,
            snippet=row.snippet,
            received_at=row.received_at,
            created_at=row.created_at,
        )


class MessageList(BaseModel):
    items: list[MessageSummary]


class MessageDetail(MessageSummary):
    to_addresses: list[dict[str, str]]
    cc_addresses: list[dict[str, str]]
    body_text: str

    @classmethod
    def from_row(cls, row: Message) -> "MessageDetail":
        summary = MessageSummary.from_row(row)
        return cls(
            **summary.model_dump(),
            to_addresses=_addresses(row.to_addresses),
            cc_addresses=_addresses(row.cc_addresses),
            body_text=row.body_text,
        )


def _addresses(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        cleaned = {
            str(key): item_value for key, item_value in item.items() if isinstance(item_value, str)
        }
        rows.append(cleaned)
    return rows
