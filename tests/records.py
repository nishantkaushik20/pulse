"""Insert tenant-owned rows in tests without the closed public create routes."""

from datetime import UTC, datetime
from uuid import UUID

from pulse_api.context import TenantContext
from pulse_api.db import session_scope
from pulse_api.models import AttentionPriority, TenantRole
from pulse_api.services import AttentionService, BusinessEventService
from tests.domain_app import DomainApp


def record_attention(
    domain: DomainApp,
    *,
    title: str,
    priority: str = AttentionPriority.MEDIUM,
    item_type: str = "manual",
    entity_type: str | None = None,
    entity_id: UUID | None = None,
) -> str:
    tenant = _tenant(domain)
    with session_scope(domain.factory) as session:
        item = AttentionService(session, tenant).create(
            item_type=item_type,
            priority=priority,
            title=title,
            description=None,
            entity_type=entity_type,
            entity_id=entity_id,
            due_at=None,
        )
        return str(item.id)


def record_event(domain: DomainApp, *, entity_id: UUID) -> str:
    tenant = _tenant(domain)
    with session_scope(domain.factory) as session:
        event = BusinessEventService(session, tenant).create(
            event_type="note",
            entity_type="customer",
            entity_id=entity_id,
            source="test",
            occurred_at=datetime.now(UTC),
            data={"note": "private"},
        )
        return str(event.id)


def _tenant(domain: DomainApp) -> TenantContext:
    me = domain.client.get("/me").json()
    return TenantContext(
        user_id=UUID(me["user"]["id"]),
        tenant_id=UUID(me["tenant"]["id"]),
        role=TenantRole(me["tenant"]["role"]),
    )
