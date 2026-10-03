import pytest
from pydantic import ValidationError

from pulse_api.config import Settings, get_settings


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "ci")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/pulse")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/1")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_env == "ci"
    assert settings.log_level == "DEBUG"
    assert settings.database_url.endswith("/pulse")
    assert settings.redis_url == "redis://cache:6379/1"


def test_settings_require_database_and_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_blank_clerk_values_are_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pulse:pulse@localhost/pulse")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CLERK_ISSUER", " ")
    monkeypatch.setenv("CLERK_SECRET_KEY", "")
    monkeypatch.setenv("CLERK_JWKS_URL", "")

    settings = Settings(_env_file=None)

    assert settings.clerk_issuer is None
    assert settings.clerk_secret_key is None
    assert settings.clerk_jwks_url is None


def test_blank_encryption_key_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pulse:pulse@localhost/pulse")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", " ")

    settings = Settings(_env_file=None)

    assert settings.integration_encryption_key is None


def test_encryption_key_must_decode_to_32_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pulse:pulse@localhost/pulse")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", "aaaa")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_requires_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pulse:pulse@localhost/pulse")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_requires_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pulse:pulse@localhost/pulse")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CLERK_ISSUER", "https://example.clerk.accounts.dev")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test")
    monkeypatch.delenv("INTEGRATION_ENCRYPTION_KEY", raising=False)

    with pytest.raises(ValidationError, match="INTEGRATION_ENCRYPTION_KEY"):
        Settings(_env_file=None)


def test_production_accepts_clerk_and_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pulse:pulse@localhost/pulse")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CLERK_ISSUER", "https://example.clerk.accounts.dev")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test")
    monkeypatch.setenv(
        "INTEGRATION_ENCRYPTION_KEY",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )

    settings = Settings(_env_file=None)

    assert settings.clerk_issuer == "https://example.clerk.accounts.dev"
    assert settings.integration_encryption_key is not None
