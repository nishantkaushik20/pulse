"""Authenticated request context. Tenant id is never taken from the client."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_api.errors import ForbiddenError
from pulse_api.models import TenantRole, TenantUser


@dataclass(frozen=True)
class TenantContext:
    user_id: UUID
    tenant_id: UUID
    role: TenantRole

    def require_owner(self) -> None:
        if self.role is not TenantRole.OWNER:
            raise ForbiddenError("owner role required")


def resolve_current_tenant(session: Session, user_id: UUID) -> TenantContext | None:
    """Resolve the one implicit tenant for this phase.

    The current tenant is the earliest membership by created_at, then id.
    This function is the only place that rule is applied. A future tenant
    switch must prove the user belongs to the requested tenant and then
    return a TenantContext. A client-supplied tenant id is never enough.
    """
    statement = (
        select(TenantUser)
        .where(TenantUser.user_id == user_id)
        .order_by(TenantUser.created_at.asc(), TenantUser.id.asc())
        .limit(1)
    )
    membership = session.scalar(statement)
    if membership is None:
        return None
    return TenantContext(
        user_id=user_id,
        tenant_id=membership.tenant_id,
        role=TenantRole(membership.role),
    )


@dataclass(frozen=True)
class RequestContext:
    user_id: UUID
    clerk_user_id: str
    email: str
    name: str
    tenant: TenantContext | None

    def require_tenant(self) -> TenantContext:
        if self.tenant is None:
            raise ForbiddenError("tenant membership required")
        return self.tenant
