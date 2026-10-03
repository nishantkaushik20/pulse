import base64

import pytest

from pulse_api.gmail.normalize import (
    BODY_TEXT_LIMIT,
    BadGmailMessage,
    is_received_inbox,
    normalize_message,
)


def _encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _message(
    *,
    labels: list[str] | None = None,
    plain: str = "Hello plain",
    html: str = "<b>SECRET-HTML</b>",
    attachment: str | None = "ATTACH-BYTES",
    message_id: str = "msg-1",
    thread_id: str = "thread-1",
    internal_date: object = "1710000000000",
) -> dict[str, object]:
    parts: list[dict[str, object]] = [
        {"mimeType": "text/plain", "body": {"data": _encoded(plain)}},
        {"mimeType": "text/html", "body": {"data": _encoded(html)}},
    ]
    if attachment is not None:
        parts.append(
            {
                "mimeType": "application/pdf",
                "filename": "invoice.pdf",
                "body": {"attachmentId": "att-1", "data": _encoded(attachment)},
            }
        )
    return {
        "id": message_id,
        "threadId": thread_id,
        "labelIds": ["INBOX"] if labels is None else labels,
        "snippet": "snippet text",
        "internalDate": internal_date,
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "Pat Example <Pat@Example.com>"},
                {"name": "To", "value": "Ada <Ada@Gmail.com>"},
                {"name": "Cc", "value": "Sam <Sam@Example.com>"},
                {"name": "Subject", "value": "Hello subject"},
            ],
            "parts": parts,
        },
    }


def test_normalize_maps_gmail_fields() -> None:
    normalized = normalize_message(_message())

    assert normalized.external_message_id == "msg-1"
    assert normalized.external_thread_id == "thread-1"
    assert normalized.from_email == "pat@example.com"
    assert normalized.from_name == "Pat Example"
    assert normalized.to_addresses == [{"email": "ada@gmail.com", "name": "Ada"}]
    assert normalized.cc_addresses == [{"email": "sam@example.com", "name": "Sam"}]
    assert normalized.subject == "Hello subject"
    assert normalized.snippet == "snippet text"
    assert normalized.body_text == "Hello plain"
    assert normalized.received_at.year == 2024


def test_plain_text_is_kept_and_html_and_attachments_are_ignored() -> None:
    normalized = normalize_message(_message())

    assert normalized.body_text == "Hello plain"
    assert "SECRET-HTML" not in normalized.body_text
    assert "ATTACH-BYTES" not in normalized.body_text


def test_html_only_message_has_empty_body() -> None:
    message = _message(plain="", attachment=None)
    payload = message["payload"]
    assert isinstance(payload, dict)
    payload["parts"] = [{"mimeType": "text/html", "body": {"data": _encoded("<p>SECRET-HTML</p>")}}]
    normalized = normalize_message(message)

    assert normalized.body_text == ""
    assert "SECRET-HTML" not in normalized.body_text


def test_body_is_capped() -> None:
    normalized = normalize_message(_message(plain="x" * (BODY_TEXT_LIMIT + 50), attachment=None))

    assert len(normalized.body_text) == BODY_TEXT_LIMIT


def test_sent_and_non_inbox_are_not_received_mail() -> None:
    assert is_received_inbox(["INBOX"]) is True
    assert is_received_inbox(["INBOX", "SENT"]) is False
    assert is_received_inbox(["SENT"]) is False
    assert is_received_inbox(["CATEGORY_PROMOTIONS"]) is False

    with pytest.raises(BadGmailMessage):
        normalize_message(_message(labels=["SENT"]))


def test_missing_internal_date_is_rejected() -> None:
    with pytest.raises(BadGmailMessage):
        normalize_message(_message(internal_date="not-a-date"))
