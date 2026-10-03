"""One-time OAuth state. The value is not a token and is not logged."""

import json
import time
from collections.abc import Callable
from typing import Protocol

from redis.exceptions import RedisError

from pulse_api.errors import UnavailableError
from pulse_api.redis_client import create_redis_client

STATE_TTL_SECONDS = 600
_PREFIX = "oauth_state:"


class OAuthStateStore(Protocol):
    def put(self, state: str, value: dict[str, str], ttl_seconds: int) -> None: ...

    def consume(self, state: str) -> dict[str, str] | None: ...


class RedisOAuthStateStore:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    def put(self, state: str, value: dict[str, str], ttl_seconds: int) -> None:
        client = create_redis_client(self._redis_url)
        try:
            client.set(_PREFIX + state, json.dumps(value), ex=ttl_seconds)
        except RedisError:
            raise UnavailableError("gmail is unavailable") from None
        finally:
            client.close()

    def consume(self, state: str) -> dict[str, str] | None:
        client = create_redis_client(self._redis_url)
        try:
            raw = client.getdel(_PREFIX + state)
        except RedisError:
            raise UnavailableError("gmail is unavailable") from None
        finally:
            client.close()
        return _decode(raw)


class MemoryOAuthStateStore:
    """Test double with an explicit clock. Not used by the application."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self.items: dict[str, tuple[str, float]] = {}

    def put(self, state: str, value: dict[str, str], ttl_seconds: int) -> None:
        self.items[state] = (json.dumps(value), self._clock() + ttl_seconds)

    def consume(self, state: str) -> dict[str, str] | None:
        item = self.items.pop(state, None)
        if item is None:
            return None
        raw, expires_at = item
        if self._clock() >= expires_at:
            return None
        return _decode(raw)


def _decode(raw: object) -> dict[str, str] | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    decoded: dict[str, str] = {}
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, str):
            decoded[key] = value
    return decoded
