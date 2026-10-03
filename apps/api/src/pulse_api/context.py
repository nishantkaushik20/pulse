"""Authenticated request context. Tenant id is never taken from the client."""

from dataclasses import dataclass
from uuid import UUID

from pulse_api.errors import ForbiddenError
from pulse_api.models import TenantRole


@dataclass(frozen=True)
class TenantContext:
    user_id: UUID
    tenant_id: UUID
    role: TenantRole

    def require_owner(self) -> None:
        if self.role is not TenantRole.OWNER:
            raise ForbiddenError("owner role required")


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
