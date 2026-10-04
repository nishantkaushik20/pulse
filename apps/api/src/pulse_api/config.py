"""Environment configuration."""

from functools import lru_cache
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pulse_api.crypto import TokenCipherError, validate_encryption_key


class Settings(BaseSettings):
    """Process configuration loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    log_level: str = "INFO"
    database_url: str
    redis_url: str
    clerk_issuer: str | None = None
    clerk_jwks_url: str | None = None
    clerk_secret_key: str | None = None
    integration_encryption_key: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    web_app_url: str = "http://localhost:3000"
    ai_daily_budget: int = 20
    ai_model: str = "none"

    @field_validator(
        "clerk_issuer",
        "clerk_jwks_url",
        "clerk_secret_key",
        "integration_encryption_key",
        "google_client_id",
        "google_client_secret",
        "google_redirect_uri",
        mode="before",
    )
    @classmethod
    def blank_optional_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("integration_encryption_key")
    @classmethod
    def encryption_key_must_be_32_bytes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            validate_encryption_key(value)
        except TokenCipherError:
            raise ValueError(
                "INTEGRATION_ENCRYPTION_KEY must be a base64-encoded 32-byte key"
            ) from None
        return value

    @field_validator("web_app_url", mode="before")
    @classmethod
    def strip_web_app_url(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip().rstrip("/")
            return cleaned or "http://localhost:3000"
        return value

    @model_validator(mode="after")
    def production_requires_clerk_and_encryption_key(self) -> Self:
        if self.app_env != "production":
            return self
        if self.clerk_issuer is None or self.clerk_secret_key is None:
            raise ValueError(
                "CLERK_ISSUER and CLERK_SECRET_KEY are required when APP_ENV=production"
            )
        if self.integration_encryption_key is None:
            raise ValueError("INTEGRATION_ENCRYPTION_KEY is required when APP_ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
