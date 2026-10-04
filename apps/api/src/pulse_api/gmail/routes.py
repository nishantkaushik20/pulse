"""Gmail HTTP routes. Raw OAuth tokens stay in the service."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from pulse_api.gmail.deps import get_gmail_callback_service, get_gmail_service
from pulse_api.gmail.schemas import (
    GmailConnectionList,
    GmailConnectionOut,
    GmailConnectOut,
    GmailSyncOut,
    MessageDetail,
    MessageList,
    MessagePurgeOut,
    MessageSummary,
    MessageThreadList,
    MessageThreadOut,
)
from pulse_api.gmail.service import GmailService

router = APIRouter()

_gmail = Depends(get_gmail_service)
_callback = Depends(get_gmail_callback_service)
_limit = Query(default=50, ge=1, le=100)
_offset = Query(default=0, ge=0, le=10_000)


@router.post("/integrations/gmail/connect", response_model=GmailConnectOut)
def connect_gmail(service: GmailService = _gmail) -> GmailConnectOut:
    return GmailConnectOut(authorization_url=service.start_connect())


@router.get("/integrations/gmail/callback")
def gmail_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    service: GmailService = _callback,
) -> RedirectResponse:
    target = service.complete_callback(code=code, state=state, error=error)
    return RedirectResponse(url=target, status_code=302)


@router.get("/integrations/gmail/connections", response_model=GmailConnectionList)
def list_gmail_connections(service: GmailService = _gmail) -> GmailConnectionList:
    rows = service.list_connections()
    return GmailConnectionList(items=[GmailConnectionOut.from_row(row) for row in rows])


@router.post(
    "/integrations/gmail/connections/{connection_id}/disconnect",
    response_model=GmailConnectionOut,
)
def disconnect_gmail(connection_id: UUID, service: GmailService = _gmail) -> GmailConnectionOut:
    return GmailConnectionOut.from_row(service.disconnect(connection_id))


@router.post(
    "/integrations/gmail/connections/{connection_id}/sync",
    response_model=GmailSyncOut,
)
def sync_gmail(connection_id: UUID, service: GmailService = _gmail) -> GmailSyncOut:
    counts = service.sync(connection_id)
    return GmailSyncOut(examined=counts.examined, ingested=counts.ingested, skipped=counts.skipped)


@router.post("/integrations/gmail/messages/purge", response_model=MessagePurgeOut)
def purge_message_bodies(service: GmailService = _gmail) -> MessagePurgeOut:
    return MessagePurgeOut(cleared=service.purge_message_bodies())


@router.get("/message-threads", response_model=MessageThreadList)
def list_message_threads(
    service: GmailService = _gmail,
    limit: int = _limit,
    offset: int = _offset,
) -> MessageThreadList:
    rows = service.list_threads(limit=limit, offset=offset)
    return MessageThreadList(items=[MessageThreadOut.from_row(row) for row in rows])


@router.get("/message-threads/{thread_id}", response_model=MessageThreadOut)
def read_message_thread(thread_id: UUID, service: GmailService = _gmail) -> MessageThreadOut:
    return MessageThreadOut.from_row(service.get_thread(thread_id))


@router.get("/messages", response_model=MessageList)
def list_messages(
    service: GmailService = _gmail,
    limit: int = _limit,
    offset: int = _offset,
) -> MessageList:
    rows = service.list_messages(limit=limit, offset=offset)
    return MessageList(items=[MessageSummary.from_row(row) for row in rows])


@router.get("/messages/{message_id}", response_model=MessageDetail)
def read_message(message_id: UUID, service: GmailService = _gmail) -> MessageDetail:
    return MessageDetail.from_row(service.get_message(message_id))
