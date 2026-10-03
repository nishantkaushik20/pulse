"""In-memory Gmail doubles. Tests do not call Google."""

from typing import Any

from pulse_api.gmail.client import (
    GMAIL_READONLY_SCOPE,
    GmailProfile,
    GmailUnauthorized,
    GmailUnavailable,
    InvalidGrant,
    OAuthTokens,
)

PLAINTEXT_REFRESH = "refresh-token-PLAINTEXT-MARKER"
PLAINTEXT_ACCESS = "access-token-value"
AUTH_CODE = "super-secret-auth-code"


class FakeGmailClient:
    def __init__(self) -> None:
        self.profile = GmailProfile(email="ada@gmail.com", history_id="hist-connect")
        self.messages: dict[str, dict[str, Any]] = {}
        self.list_ids: list[str] = []
        self.fail_refresh = False
        self.refresh_unavailable = False
        self.fail_revoke = False
        self.unavailable_on_get: set[str] = set()
        self.unauthorized_list = 0
        self.unauthorized_get: set[str] = set()
        self.unauthorized_profile = 0
        self.exchanged: list[tuple[str, str, str]] = []
        self.refresh_calls = 0
        self.list_calls = 0
        self.get_calls: list[str] = []
        self.revoked: list[str] = []
        self.listed_access: list[str] = []
        self.last_query = ""
        self.last_limit = 0
        self.access_token = PLAINTEXT_ACCESS
        self.refresh_token: str | None = PLAINTEXT_REFRESH

    def exchange_code(self, *, code: str, verifier: str, redirect_uri: str) -> OAuthTokens:
        self.exchanged.append((code, verifier, redirect_uri))
        return OAuthTokens(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            expires_in=3600,
            scopes=GMAIL_READONLY_SCOPE,
        )

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        self.refresh_calls += 1
        self.revoked_refresh_seen = refresh_token
        if self.fail_refresh:
            raise InvalidGrant
        if self.refresh_unavailable:
            raise GmailUnavailable
        return OAuthTokens(
            access_token="refreshed-access-token",
            refresh_token=None,
            expires_in=3600,
            scopes=GMAIL_READONLY_SCOPE,
        )

    def revoke_token(self, token: str) -> None:
        self.revoked.append(token)
        if self.fail_revoke:
            raise GmailUnavailable

    def get_profile(self, access_token: str) -> GmailProfile:
        self.profile_access = access_token
        if self.unauthorized_profile > 0:
            self.unauthorized_profile -= 1
            raise GmailUnauthorized
        return self.profile

    def list_message_ids(self, access_token: str, *, query: str, limit: int) -> list[str]:
        self.list_calls += 1
        self.last_query = query
        self.last_limit = limit
        self.listed_access.append(access_token)
        if self.unauthorized_list > 0:
            self.unauthorized_list -= 1
            raise GmailUnauthorized
        return list(self.list_ids)[:limit]

    def get_message(self, access_token: str, message_id: str) -> dict[str, Any]:
        self.get_calls.append(message_id)
        if message_id in self.unauthorized_get:
            self.unauthorized_get.remove(message_id)
            raise GmailUnauthorized
        if message_id in self.unavailable_on_get:
            raise GmailUnavailable
        return self.messages[message_id]
