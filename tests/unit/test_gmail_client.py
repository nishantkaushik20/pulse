import io
import json
import logging
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from pulse_api.config import Settings
from pulse_api.gmail.client import (
    GMAIL_READONLY_SCOPE,
    GmailUnavailable,
    InvalidGrant,
    UrllibGmailClient,
    authorization_url,
)


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_authorization_url_requests_readonly_scope_only() -> None:
    url = authorization_url(
        client_id="client",
        redirect_uri="http://localhost:8000/integrations/gmail/callback",
        state="state-value",
        code_challenge="challenge-value",
    )

    query = parse_qs(urlparse(url).query)
    assert query["scope"] == [GMAIL_READONLY_SCOPE]
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    assert "gmail.send" not in url
    assert "gmail.modify" not in url
    assert "gmail.compose" not in url
    assert "mail.google.com" not in url
    assert "gmail.metadata" not in url


def test_exchange_sends_pkce_verifier(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    captured: dict[str, bytes] = {}

    def capture(request: object, timeout: int = 10) -> _Response:
        data = getattr(request, "data", b"")
        captured["body"] = data if isinstance(data, bytes) else b""
        return _Response(
            b'{"access_token":"access-token-value","refresh_token":"refresh-token-PLAINTEXT-MARKER","expires_in":3600}'
        )

    monkeypatch.setattr("pulse_api.gmail.client.urlopen", capture)
    caplog.set_level(logging.DEBUG)
    tokens = UrllibGmailClient(_settings()).exchange_code(
        code="super-secret-auth-code",
        verifier="pkce-verifier-value",
        redirect_uri="http://localhost/callback",
    )

    body = captured["body"].decode()
    assert "code_verifier=pkce-verifier-value" in body
    assert tokens.access_token == "access-token-value"
    assert "super-secret-auth-code" not in caplog.text
    assert "pkce-verifier-value" not in caplog.text
    assert "google-client-secret" not in caplog.text


def test_invalid_grant_does_not_expose_google_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(request: object, timeout: int = 10) -> _Response:
        raise HTTPError(
            "https://oauth2.googleapis.com/token",
            400,
            "Bad Request",
            Message(),
            io.BytesIO(b'{"error":"invalid_grant","error_description":"SUPER-GOOGLE-BODY"}'),
        )

    monkeypatch.setattr("pulse_api.gmail.client.urlopen", boom)

    with pytest.raises(InvalidGrant) as exc:
        UrllibGmailClient(_settings()).refresh_access_token("refresh-token-PLAINTEXT-MARKER")

    assert "SUPER-GOOGLE-BODY" not in str(exc.value)
    assert "refresh-token-PLAINTEXT-MARKER" not in str(exc.value)


@pytest.mark.parametrize("status", [429, 500])
def test_retryable_status_hides_google_body(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    def boom(request: object, timeout: int = 10) -> _Response:
        raise HTTPError(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            status,
            "error",
            Message(),
            io.BytesIO(b'{"error":"backendError","secret":"BODY-SECRET"}'),
        )

    monkeypatch.setattr("pulse_api.gmail.client.urlopen", boom)

    with pytest.raises(GmailUnavailable) as exc:
        UrllibGmailClient(_settings()).list_message_ids(
            "access-token-value", query="in:inbox", limit=50
        )

    assert "BODY-SECRET" not in str(exc.value)
    assert "access-token-value" not in str(exc.value)


def test_token_response_without_access_token_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pulse_api.gmail.client.urlopen",
        lambda request, timeout=10: _Response(json.dumps({"refresh_token": "x"}).encode()),
    )

    with pytest.raises(GmailUnavailable):
        UrllibGmailClient(_settings()).exchange_code(
            code="super-secret-auth-code",
            verifier="verifier",
            redirect_uri="http://localhost/callback",
        )
