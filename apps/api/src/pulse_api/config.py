"""Environment configuration."""

from functools import lru_cache
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @field_validator("clerk_issuer", "clerk_jwks_url", "clerk_secret_key", mode="before")
    @classmethod
    def blank_clerk_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def production_requires_clerk(self) -> Self:
        if self.app_env == "production" and (
            self.clerk_issuer is None or self.clerk_secret_key is None
        ):
            raise ValueError(
                "CLERK_ISSUER and CLERK_SECRET_KEY are required when APP_ENV=production"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
