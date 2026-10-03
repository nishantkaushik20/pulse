import pytest

from pulse_api.redis_client import check_redis


def test_check_redis_rejects_failed_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRedis:
        def ping(self) -> bool:
            return False

        def close(self) -> None:
            return None

    monkeypatch.setattr("pulse_api.redis_client.create_redis_client", lambda _url: FakeRedis())

    with pytest.raises(RuntimeError, match="redis ping failed"):
        check_redis("redis://localhost:6379/0")
