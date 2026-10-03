"""Clerk session verification without a live Clerk tenant."""

import io
import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKClient
from jwt.algorithms import RSAAlgorithm

from pulse_api.auth import ClerkAuthenticator, fetch_clerk_profile
from pulse_api.config import Settings
from pulse_api.errors import UnauthorizedError, UnavailableError

_ISSUER = "https://clerk.example"


@pytest.fixture
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_valid_rs256_token_establishes_identity(
    private_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_jwks(monkeypatch, private_key)
    token = _token(private_key, {"email": "Ada@Example.com", "name": "Ada Lovelace"})
    identity = ClerkAuthenticator(_settings()).authenticate(f"Bearer {token}")
    assert identity.clerk_user_id == "user_123"
    assert identity.email == "Ada@Example.com"
    assert identity.name == "Ada Lovelace"


def test_wrong_issuer_expired_and_bad_algorithm_are_rejected(
    private_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _stub_jwks(monkeypatch, private_key)
    authenticator = ClerkAuthenticator(_settings())
    cases = [
        _token(private_key, issuer="https://other.example"),
        _token(private_key, expires_in=timedelta(minutes=-5)),
        jwt.encode(
            {"sub": "user_123", "iss": _ISSUER, "exp": _exp(timedelta(minutes=5))},
            "hmac-secret-key-with-enough-length",
            algorithm="HS256",
        ),
    ]
    with caplog.at_level(logging.WARNING):
        for token in cases:
            with pytest.raises(UnauthorizedError, match="invalid token"):
                authenticator.authenticate(f"Bearer {token}")
    assert "super-secret" not in caplog.text
    for token in cases:
        assert token not in caplog.text


def test_jwks_selects_the_key_id_and_rejects_an_unknown_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    second = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _install_jwks(monkeypatch, {"key-a": first, "key-b": second})
    authenticator = ClerkAuthenticator(_settings())

    selected = _token(second, headers={"kid": "key-b"})
    assert authenticator.authenticate(f"Bearer {selected}").clerk_user_id == "user_123"

    mismatched = _token(first, headers={"kid": "key-b"})
    unknown = _token(second, headers={"kid": "missing"})
    for token in (mismatched, unknown):
        with pytest.raises(UnauthorizedError, match="invalid token"):
            authenticator.authenticate(f"Bearer {token}")


def test_malformed_and_subject_tokens_are_rejected(
    private_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_jwks(monkeypatch, private_key)
    authenticator = ClerkAuthenticator(_settings())
    rejected = [
        "not-a-jwt",
        "a.b.c",
        _token(private_key, {"sub": "   "}),
        _token(private_key, {"sub": 42}),
        jwt.encode(
            {"iss": _ISSUER, "exp": _exp(timedelta(minutes=5))},
            private_key,
            algorithm="RS256",
        ),
        _token(private_key, expires_in=timedelta(minutes=5), nbf_in=timedelta(minutes=5)),
        _token(private_key, algorithm="RS384"),
    ]
    for token in rejected:
        with pytest.raises(UnauthorizedError, match="invalid token"):
            authenticator.authenticate(f"Bearer {token}")


def test_audience_and_authorized_party_are_not_authorization(
    private_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_jwks(monkeypatch, private_key)
    token = _token(
        private_key,
        {
            "aud": "https://some-other-api.example",
            "azp": "https://evil.example",
            "org_role": "admin",
            "email": "Ada@Example.com",
        },
    )
    identity = ClerkAuthenticator(_settings()).authenticate(f"Bearer {token}")
    assert identity.clerk_user_id == "user_123"
    assert identity.email == "Ada@Example.com"
    assert not hasattr(identity, "role")


def test_missing_configuration_and_header_are_rejected() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://pulse:pulse@localhost/pulse",
        redis_url="redis://localhost:6379/0",
    )
    with pytest.raises(UnauthorizedError, match="not configured"):
        ClerkAuthenticator(settings).authenticate("Bearer anything")
    with pytest.raises(UnauthorizedError, match="authentication required"):
        ClerkAuthenticator(_settings()).authenticate(None)


def test_profile_lookup_uses_primary_email_and_does_not_log_payload(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = {
        "primary_email_address_id": "idn_1",
        "email_addresses": [
            {"id": "idn_2", "email_address": "other@example.com"},
            {"id": "idn_1", "email_address": "Ada@Example.com"},
        ],
        "first_name": "Ada",
        "last_name": "Lovelace",
        "private_note": "do-not-log-profile-secret",
    }

    class _Response:
        def read(self) -> bytes:
            return json.dumps(payload).encode()

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr("pulse_api.auth.urlopen", lambda *_args, **_kwargs: _Response())
    with caplog.at_level(logging.DEBUG):
        email, name = fetch_clerk_profile("sk_test_secret", "user_123")
    assert email == "ada@example.com"
    assert name == "Ada Lovelace"
    assert "do-not-log-profile-secret" not in caplog.text
    assert "sk_test_secret" not in caplog.text


def test_profile_lookup_failure_does_not_log_the_body(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def explode(*_args: object, **_kwargs: object) -> object:
        raise HTTPError(
            "https://api.clerk.com/v1/users/user_123",
            500,
            "error",
            hdrs=None,
            fp=io.BytesIO(b"profile-body-secret"),
        )

    monkeypatch.setattr("pulse_api.auth.urlopen", explode)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(UnavailableError):
            fetch_clerk_profile("sk_test_secret", "user_123")
    assert "profile-body-secret" not in caplog.text
    assert "sk_test_secret" not in caplog.text
    assert "clerk profile lookup failed" in caplog.text


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://pulse:pulse@localhost/pulse",
        redis_url="redis://localhost:6379/0",
        clerk_issuer=_ISSUER,
        clerk_secret_key="sk_test_secret",
    )


def _stub_jwks(monkeypatch: pytest.MonkeyPatch, private_key: rsa.RSAPrivateKey) -> None:
    public_key = private_key.public_key()

    class _Key:
        key = public_key

    class _Client:
        def get_signing_key_from_jwt(self, _token: str) -> _Key:
            return _Key()

    monkeypatch.setattr("pulse_api.auth._jwks_client", lambda _url: _Client())


def _install_jwks(
    monkeypatch: pytest.MonkeyPatch,
    keys: dict[str, rsa.RSAPrivateKey],
) -> None:
    document = {"keys": [_public_jwk(key, kid) for kid, key in keys.items()]}

    def factory(url: str) -> PyJWKClient:
        client = PyJWKClient(url)
        client.fetch_data = lambda: document  # type: ignore[method-assign]
        return client

    monkeypatch.setattr("pulse_api.auth._jwks_client", factory)


def _public_jwk(private_key: rsa.RSAPrivateKey, kid: str) -> dict[str, object]:
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return jwk


def _token(
    private_key: rsa.RSAPrivateKey,
    extra: dict[str, object] | None = None,
    *,
    issuer: str = _ISSUER,
    expires_in: timedelta = timedelta(minutes=5),
    nbf_in: timedelta | None = None,
    headers: dict[str, str] | None = None,
    algorithm: str = "RS256",
) -> str:
    claims: dict[str, object] = {"sub": "user_123", "iss": issuer, "exp": _exp(expires_in)}
    if nbf_in is not None:
        claims["nbf"] = _exp(nbf_in)
    claims.update(extra or {})
    return jwt.encode(claims, private_key, algorithm=algorithm, headers=headers)


def _exp(delta: timedelta) -> int:
    return int((datetime.now(UTC) + delta).timestamp())
