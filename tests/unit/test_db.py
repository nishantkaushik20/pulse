import pytest
from sqlalchemy import text

from pulse_api.db import Base, build_session_factory, create_db_engine, session_scope


def test_session_scope_executes_within_a_transaction() -> None:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    factory = build_session_factory(engine)

    with session_scope(factory) as session:
        value = session.execute(text("SELECT 1")).scalar_one()

    assert value == 1
    assert Base.metadata.tables == {}
    engine.dispose()


def test_session_scope_rolls_back_on_error() -> None:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    factory = build_session_factory(engine)

    with pytest.raises(RuntimeError, match="fail"):
        with session_scope(factory) as session:
            session.execute(text("SELECT 1"))
            raise RuntimeError("fail")

    engine.dispose()
