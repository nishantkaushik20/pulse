"""Turn one Gmail message resource into Pulse fields.

Message content is untrusted mailbox data. It is not an instruction and it is not logged.
"""

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import getaddresses, parseaddr
from typing import Any

GMAIL_SOURCE = "gmail"
BODY_TEXT_LIMIT = 32_768
_SUBJECT_LIMIT = 500
_SNIPPET_LIMIT = 1000
_NAME_LIMIT = 200
_EMAIL_LIMIT = 320
_ADDRESS_LIMIT = 20


class BadGmailMessage(Exception):
    """The resource cannot be stored. The message does not include mailbox content."""


@dataclass(frozen=True)
class NormalizedMessage:
    external_message_id: str
    external_thread_id: str
    from_email: str | None
    from_name: str | None
    to_addresses: list[dict[str, str]]
    cc_addresses: list[dict[str, str]]
    subject: str
    snippet: str
    body_text: str
    received_at: datetime


def is_received_inbox(label_ids: object) -> bool:
    if not isinstance(label_ids, list):
        return False
    labels = {item for item in label_ids if isinstance(item, str)}
    if "SENT" in labels:
        return False
    return "INBOX" in labels


def normalize_message(message: dict[str, Any]) -> NormalizedMessage:
    external_id = message.get("id")
    thread_id = message.get("threadId")
    if not isinstance(external_id, str) or not external_id.strip():
        raise BadGmailMessage
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise BadGmailMessage
    if not is_received_inbox(message.get("labelIds")):
        raise BadGmailMessage
    payload = message.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    headers = _headers(payload)
    from_name, from_email = parseaddr(headers.get("from", ""))
    return NormalizedMessage(
        external_message_id=external_id.strip()[:255],
        external_thread_id=thread_id.strip()[:255],
        from_email=_clean_email(from_email),
        from_name=_clean_name(from_name),
        to_addresses=_address_list(headers.get("to", "")),
        cc_addresses=_address_list(headers.get("cc", "")),
        subject=headers.get("subject", "").strip()[:_SUBJECT_LIMIT],
        snippet=_snippet(message.get("snippet")),
        body_text=_plain_text(payload)[:BODY_TEXT_LIMIT],
        received_at=_received_at(message.get("internalDate")),
    )


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    raw = payload.get("headers")
    if not isinstance(raw, list):
        return found
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if isinstance(name, str) and isinstance(value, str):
            found[name.lower()] = value
    return found


def _plain_text(payload: dict[str, Any]) -> str:
    if payload.get("mimeType") == "text/plain" and not payload.get("filename"):
        body = payload.get("body")
        if isinstance(body, dict) and isinstance(body.get("data"), str):
            return _decode_part(body["data"])
    parts = payload.get("parts")
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            text = _plain_text(part)
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _decode_part(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    try:
        raw = base64.urlsafe_b64decode(data + padding)
    except ValueError:
        return ""
    return raw.decode("utf-8", errors="replace")


def _received_at(value: object) -> datetime:
    if isinstance(value, str) and value.isdigit():
        millis = int(value)
    elif isinstance(value, int) and not isinstance(value, bool):
        millis = value
    else:
        raise BadGmailMessage
    return datetime.fromtimestamp(millis / 1000, tz=UTC)


def _snippet(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:_SNIPPET_LIMIT]


def _address_list(header: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name, email in getaddresses([header]):
        cleaned = _clean_email(email)
        if cleaned is None:
            continue
        item: dict[str, str] = {"email": cleaned}
        display = _clean_name(name)
        if display is not None:
            item["name"] = display
        rows.append(item)
        if len(rows) >= _ADDRESS_LIMIT:
            break
    return rows


def _clean_email(value: str) -> str | None:
    cleaned = value.strip().lower()
    if "@" not in cleaned:
        return None
    return cleaned[:_EMAIL_LIMIT]


def _clean_name(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:_NAME_LIMIT]
