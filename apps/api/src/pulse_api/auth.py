"""Clerk session verification. Pulse does not implement password authentication."""

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import jwt
from jwt import PyJWKClient

from pulse_api.config import Settings
from pulse_api.errors import UnauthorizedError, UnavailableError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClerkIdentity:
    clerk_user_id: str
    email: str | None
    name: str | None


class ClerkAuthenticator:
    """Verify a Clerk session JWT. There is no alternate acceptance path."""

    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.clerk_issuer
        self._jwks_url = settings.clerk_jwks_url

    def authenticate(self, authorization: str | None) -> ClerkIdentity:
        if self._issuer is None:
            raise UnauthorizedError("authentication is not configured")
        token = _bearer_token(authorization)
        try:
            signing_key = _jwks_client(_resolved_jwks_url(self._issuer, self._jwks_url))
            key = signing_key.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={"require": ["exp", "sub", "iss"]},
            )
        except jwt.PyJWTError:
            logger.warning("clerk token verification failed")
            raise UnauthorizedError("invalid token") from None
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise UnauthorizedError("invalid token")
        return ClerkIdentity(
            clerk_user_id=subject.strip(),
            email=_clean_optional(claims.get("email")),
            name=_clean_optional(claims.get("name")),
        )


def fetch_clerk_profile(secret_key: str, clerk_user_id: str) -> tuple[str, str]:
    """Load email and name from Clerk. The response body is not logged."""
    url = f"https://api.clerk.com/v1/users/{quote(clerk_user_id, safe='')}"
    request = Request(url, headers={"Authorization": f"Bearer {secret_key}"})
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        logger.warning("clerk profile lookup failed")
        raise UnavailableError("authentication profile is unavailable") from None
    if not isinstance(payload, dict):
        raise UnavailableError("authentication profile is unavailable")
    email = _primary_email(payload)
    if email is None:
        raise UnavailableError("authentication profile is unavailable")
    return email, _display_name(payload)


def _bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization.strip():
        raise UnauthorizedError("authentication required")
    scheme, _, token = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("authentication required")
    return token.strip()


def _resolved_jwks_url(issuer: str, configured: str | None) -> str:
    if configured:
        return configured
    return f"{issuer.rstrip('/')}/.well-known/jwks.json"


@lru_cache
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url)


def _clean_optional(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _primary_email(payload: dict[str, object]) -> str | None:
    addresses = payload.get("email_addresses")
    if not isinstance(addresses, list):
        return None
    primary_id = payload.get("primary_email_address_id")
    fallback: str | None = None
    for item in addresses:
        if not isinstance(item, dict):
            continue
        address = item.get("email_address")
        if not isinstance(address, str) or "@" not in address:
            continue
        if item.get("id") == primary_id:
            return address.strip().lower()
        if fallback is None:
            fallback = address.strip().lower()
    return fallback


def _display_name(payload: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("first_name", "last_name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " ".join(parts)[:200]
