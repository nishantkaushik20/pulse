"""Redis client used by readiness checks."""

from redis import Redis


def create_redis_client(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)


def check_redis(redis_url: str) -> None:
    client = create_redis_client(redis_url)
    try:
        if client.ping() is not True:
            raise RuntimeError("redis ping failed")
    finally:
        client.close()
