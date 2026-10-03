"""Gmail and Google OAuth HTTP. Responses are parsed and never logged."""

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pulse_api.config import Settings

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SYNC_MAX_MESSAGES = 50
SYNC_QUERY = "in:inbox newer_than:7d -in:sent"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TIMEOUT = 10


class InvalidGrant(Exception):
    """Refresh or exchange was rejected. The Google body is not retained."""


class GmailUnavailable(Exception):
    """Gmail or Google returned a retryable failure."""


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int
    scopes: str


@dataclass(frozen=True)
class GmailProfile:
    email: str
    history_id: str


class GmailClient(Protocol):
    def exchange_code(self, *, code: str, verifier: str, redirect_uri: str) -> OAuthTokens: ...

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens: ...

    def revoke_token(self, token: str) -> None: ...

    def get_profile(self, access_token: str) -> GmailProfile: ...

    def list_message_ids(self, access_token: str, *, query: str, limit: int) -> list[str]: ...

    def get_message(self, access_token: str, message_id: str) -> dict[str, Any]: ...


class UrllibGmailClient:
    def __init__(self, settings: Settings) -> None:
        self._client_id = settings.google_client_id or ""
        self._client_secret = settings.google_client_secret or ""

    def exchange_code(self, *, code: str, verifier: str, redirect_uri: str) -> OAuthTokens:
        payload = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        )
        return _tokens(payload)

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        payload = self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        )
        return _tokens(payload)

    def revoke_token(self, token: str) -> None:
        body = urlencode({"token": token}).encode("utf-8")
        request = Request(_REVOKE_URL, data=body, method="POST")
        try:
            with urlopen(request, timeout=_TIMEOUT):
                return
        except (HTTPError, URLError, TimeoutError):
            raise GmailUnavailable from None

    def get_profile(self, access_token: str) -> GmailProfile:
        payload = self._gmail("GET", "/profile", access_token)
        email = payload.get("emailAddress")
        history_id = payload.get("historyId")
        if not isinstance(email, str) or "@" not in email:
            raise GmailUnavailable
        history = history_id if isinstance(history_id, str) else ""
        return GmailProfile(email=email.strip().lower(), history_id=history[:64])

    def list_message_ids(self, access_token: str, *, query: str, limit: int) -> list[str]:
        bounded = max(1, min(limit, SYNC_MAX_MESSAGES))
        payload = self._gmail(
            "GET",
            "/messages?" + urlencode({"q": query, "maxResults": str(bounded)}),
            access_token,
        )
        raw = payload.get("messages")
        if not isinstance(raw, list):
            return []
        ids: list[str] = []
        for item in raw:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                ids.append(item["id"])
            if len(ids) >= bounded:
                break
        return ids

    def get_message(self, access_token: str, message_id: str) -> dict[str, Any]:
        safe_id = message_id.replace("/", "")
        payload = self._gmail("GET", f"/messages/{safe_id}?format=full", access_token)
        return payload

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        body = urlencode(form).encode("utf-8")
        request = Request(_TOKEN_URL, data=body, method="POST")
        return _json_object(_open(request))

    def _gmail(self, method: str, path: str, access_token: str) -> dict[str, Any]:
        request = Request(
            _GMAIL_BASE + path,
            method=method,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return _json_object(_open(request))


def authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GMAIL_READONLY_SCOPE,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    return f"{_AUTH_URL}?{query}"


def _open(request: Request) -> bytes:
    try:
        with urlopen(request, timeout=_TIMEOUT) as response:
            data = response.read()
    except HTTPError as exc:
        code = _error_code(exc)
        status = exc.code
        if code == "invalid_grant":
            raise InvalidGrant from None
        if status == 429 or status >= 500:
            raise GmailUnavailable from None
        raise GmailUnavailable from None
    except (URLError, TimeoutError):
        raise GmailUnavailable from None
    if isinstance(data, bytes):
        return data
    return b""


def _error_code(exc: HTTPError) -> str | None:
    try:
        raw = exc.read()
    except Exception:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, str):
        return error
    return None


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise GmailUnavailable from None
    if not isinstance(payload, dict):
        raise GmailUnavailable
    return payload


def _tokens(payload: dict[str, Any]) -> OAuthTokens:
    access = payload.get("access_token")
    if not isinstance(access, str) or not access:
        raise GmailUnavailable
    refresh = payload.get("refresh_token")
    expires = payload.get("expires_in")
    scopes = payload.get("scope")
    return OAuthTokens(
        access_token=access,
        refresh_token=refresh if isinstance(refresh, str) and refresh else None,
        expires_in=expires if isinstance(expires, int) and expires > 0 else 3600,
        scopes=scopes if isinstance(scopes, str) else GMAIL_READONLY_SCOPE,
    )
