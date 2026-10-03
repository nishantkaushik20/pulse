import pytest
from sqlalchemy import text

from pulse_api.db import (
    READINESS_CONNECT_TIMEOUT_SECONDS,
    Base,
    build_session_factory,
    check_database,
    create_db_engine,
    session_scope,
)


def test_session_scope_executes_within_a_transaction() -> None:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    factory = build_session_factory(engine)

    with session_scope(factory) as session:
        value = session.execute(text("SELECT 1")).scalar_one()

    assert value == 1
    assert Base.metadata.tables == {}
    engine.dispose()


def test_application_engine_does_not_set_readiness_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_create_engine(url: str, **kwargs: object) -> object:
        seen["url"] = url
        seen["kwargs"] = kwargs
        raise RuntimeError("stop")

    monkeypatch.setattr("pulse_api.db.create_engine", fake_create_engine)

    with pytest.raises(RuntimeError, match="stop"):
        create_db_engine("sqlite+pysqlite:///:memory:")

    assert seen["kwargs"] == {"pool_pre_ping": True}


def test_readiness_check_sets_short_connect_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class FakeConnection:
        def execute(self, _statement: object) -> None:
            return None

        def __enter__(self) -> object:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

    class FakeEngine:
        def connect(self) -> FakeConnection:
            return FakeConnection()

        def dispose(self) -> None:
            return None

    def fake_create_engine(url: str, **kwargs: object) -> FakeEngine:
        seen["url"] = url
        seen["kwargs"] = kwargs
        return FakeEngine()

    monkeypatch.setattr("pulse_api.db.create_engine", fake_create_engine)

    check_database("postgresql+psycopg://pulse:pulse@localhost:5432/pulse")

    assert seen["kwargs"] == {
        "pool_pre_ping": True,
        "connect_args": {"connect_timeout": READINESS_CONNECT_TIMEOUT_SECONDS},
    }
    assert READINESS_CONNECT_TIMEOUT_SECONDS == 2


def test_session_scope_rolls_back_on_error() -> None:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    factory = build_session_factory(engine)

    with pytest.raises(RuntimeError, match="fail"):
        with session_scope(factory) as session:
            session.execute(text("SELECT 1"))
            raise RuntimeError("fail")

    engine.dispose()
