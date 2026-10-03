import json

import pytest
from redis.exceptions import RedisError

from pulse_api.errors import UnavailableError
from pulse_api.gmail.state_store import MemoryOAuthStateStore, RedisOAuthStateStore


def test_memory_state_is_single_use_and_expires() -> None:
    clock = {"now": 100.0}
    store = MemoryOAuthStateStore(clock=lambda: clock["now"])
    store.put("state-1", {"user_id": "u", "tenant_id": "t", "pkce_verifier": "v"}, 600)

    assert store.consume("state-1") == {
        "user_id": "u",
        "tenant_id": "t",
        "pkce_verifier": "v",
    }
    assert store.consume("state-1") is None

    store.put("state-2", {"user_id": "u", "tenant_id": "t", "pkce_verifier": "v"}, 600)
    clock["now"] = 701.0
    assert store.consume("state-2") is None


def test_missing_state_is_rejected() -> None:
    store = MemoryOAuthStateStore()

    assert store.consume("missing") is None


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.closed = False

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value

    def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)

    def close(self) -> None:
        self.closed = True


def test_redis_state_is_consumed_with_getdel(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr("pulse_api.gmail.state_store.create_redis_client", lambda url: fake)
    store = RedisOAuthStateStore("redis://localhost:6379/0")

    store.put("opaque", {"user_id": "user-1", "tenant_id": "tenant-1", "pkce_verifier": "ver"}, 600)

    assert "oauth_state:opaque" in fake.values
    assert store.consume("opaque") == {
        "user_id": "user-1",
        "tenant_id": "tenant-1",
        "pkce_verifier": "ver",
    }
    assert store.consume("opaque") is None
    assert fake.closed is True
    stored = json.dumps(fake.values)
    assert "access_token" not in stored


def test_redis_failure_is_generic(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom:
        def set(self, *_args: object, **_kwargs: object) -> None:
            raise RedisError("redis-secret-token")

        def close(self) -> None:
            return None

    monkeypatch.setattr("pulse_api.gmail.state_store.create_redis_client", lambda url: Boom())

    with pytest.raises(UnavailableError) as exc:
        RedisOAuthStateStore("redis://localhost:6379/0").put("s", {"user_id": "u"}, 600)

    assert exc.value.detail == "gmail is unavailable"
    assert "redis-secret-token" not in str(exc.value)
