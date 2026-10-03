"""SQLite API harness. The identity override exists only in tests."""

from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pulse_api.auth import ClerkIdentity
from pulse_api.db import Base, build_session_factory, session_scope
from pulse_api.deps import get_identity, get_session
from pulse_api.main import create_app


@dataclass
class DomainApp:
    client: TestClient
    engine: Engine
    factory: sessionmaker[Session]
    _identity: ClerkIdentity = field(
        default_factory=lambda: ClerkIdentity("user_a", "a@example.com", "Ada")
    )

    def login(self, clerk_user_id: str, email: str, name: str) -> None:
        self._identity = ClerkIdentity(clerk_user_id, email, name)

    def identity(self) -> ClerkIdentity:
        return self._identity


@pytest.fixture
def domain() -> Iterator[DomainApp]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    holder = DomainApp(client=None, engine=engine, factory=factory)  # type: ignore[arg-type]

    def override_session() -> Iterator[Session]:
        with session_scope(factory) as session:
            yield session

    def override_identity() -> ClerkIdentity:
        return holder.identity()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_identity] = override_identity
    with TestClient(app) as client:
        holder.client = client
        yield holder
    engine.dispose()


def _enable_sqlite_foreign_keys(dbapi_connection: object, _record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
