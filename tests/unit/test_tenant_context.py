"""Current tenant resolution stays behind resolve_current_tenant."""

from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from pulse_api.context import resolve_current_tenant
from pulse_api.db import Base, build_session_factory, session_scope
from pulse_api.models import Tenant, TenantRole, TenantUser, User
from pulse_api.services import build_request_context


def test_request_context_uses_the_earliest_membership() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    earlier = datetime(2024, 1, 1, tzinfo=UTC)
    later = datetime(2025, 1, 1, tzinfo=UTC)

    with session_scope(factory) as session:
        user = User(clerk_user_id="user_two", email="two@example.com", name="Two")
        first = Tenant(name="Earlier")
        second = Tenant(name="Later")
        session.add_all([user, first, second])
        session.flush()
        session.add_all(
            [
                TenantUser(
                    tenant_id=second.id,
                    user_id=user.id,
                    role=TenantRole.MEMBER,
                    created_at=later,
                ),
                TenantUser(
                    tenant_id=first.id,
                    user_id=user.id,
                    role=TenantRole.OWNER,
                    created_at=earlier,
                ),
            ]
        )
        session.flush()
        resolved = resolve_current_tenant(session, user.id)
        request = build_request_context(session, user)

    assert resolved is not None
    assert resolved.tenant_id == first.id
    assert resolved.role is TenantRole.OWNER
    assert request.tenant == resolved
    engine.dispose()


def test_resolve_current_tenant_is_empty_without_membership() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    with session_scope(factory) as session:
        user = User(clerk_user_id="user_none", email="none@example.com", name="None")
        session.add(user)
        session.flush()
        assert resolve_current_tenant(session, user.id) is None
    engine.dispose()


def _enable_sqlite_foreign_keys(dbapi_connection: object, _record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
