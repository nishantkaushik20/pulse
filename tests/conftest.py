import pytest

from pulse_api.config import get_settings


@pytest.fixture(autouse=True)
def foundation_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://pulse:pulse@localhost:5432/pulse",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
