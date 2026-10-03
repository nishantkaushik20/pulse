"""SQLAlchemy 2 engine and session setup."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for future tenant-owned models."""


# Same budget as the Redis readiness socket timeout.
READINESS_CONNECT_TIMEOUT_SECONDS = 2


def create_db_engine(database_url: str, *, connect_timeout: int | None = None) -> Engine:
    if connect_timeout is None:
        return create_engine(database_url, pool_pre_ping=True)
    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": connect_timeout},
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database(database_url: str) -> None:
    engine = create_db_engine(
        database_url,
        connect_timeout=READINESS_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()
