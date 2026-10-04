"""Request dependencies. Authentication and tenant context stay here, not in clients."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from pulse_api.ai import DisabledModel, LanguageModel
from pulse_api.auth import ClerkAuthenticator, ClerkIdentity, fetch_clerk_profile
from pulse_api.config import Settings, get_settings
from pulse_api.context import RequestContext, TenantContext
from pulse_api.db import build_session_factory, get_app_engine, session_scope
from pulse_api.errors import UnauthorizedError
from pulse_api.reasoning import ReasoningService
from pulse_api.services import (
    ActionService,
    AttentionService,
    BusinessEventService,
    ContactService,
    CustomerService,
    IdentityService,
    ProfileLookup,
    build_request_context,
    ensure_user,
)


def get_session() -> Iterator[Session]:
    factory = build_session_factory(get_app_engine())
    with session_scope(factory) as session:
        yield session


_settings_dep = Depends(get_settings)
_session_dep = Depends(get_session)


def get_identity(
    settings: Settings = _settings_dep,
    authorization: Annotated[str | None, Header()] = None,
) -> ClerkIdentity:
    return ClerkAuthenticator(settings).authenticate(authorization)


def _profile_lookup(settings: Settings) -> ProfileLookup:
    def lookup(clerk_user_id: str) -> tuple[str, str]:
        if settings.clerk_secret_key is None:
            raise UnauthorizedError("authentication is not configured")
        return fetch_clerk_profile(settings.clerk_secret_key, clerk_user_id)

    return lookup


_identity_dep = Depends(get_identity)


def get_request_context(
    identity: ClerkIdentity = _identity_dep,
    session: Session = _session_dep,
    settings: Settings = _settings_dep,
) -> RequestContext:
    user = ensure_user(session, identity, _profile_lookup(settings))
    return build_request_context(session, user)


_context_dep = Depends(get_request_context)


def require_tenant(context: RequestContext = _context_dep) -> TenantContext:
    return context.require_tenant()


_tenant_dep = Depends(require_tenant)


def get_identity_service(
    context: RequestContext = _context_dep,
    session: Session = _session_dep,
) -> IdentityService:
    return IdentityService(session, context)


def get_customer_service(
    tenant: TenantContext = _tenant_dep,
    session: Session = _session_dep,
) -> CustomerService:
    return CustomerService(session, tenant)


def get_contact_service(
    tenant: TenantContext = _tenant_dep,
    session: Session = _session_dep,
) -> ContactService:
    return ContactService(session, tenant)


def get_event_service(
    tenant: TenantContext = _tenant_dep,
    session: Session = _session_dep,
) -> BusinessEventService:
    return BusinessEventService(session, tenant)


def get_attention_service(
    tenant: TenantContext = _tenant_dep,
    session: Session = _session_dep,
) -> AttentionService:
    return AttentionService(session, tenant)


def get_language_model() -> LanguageModel:
    return DisabledModel()


_model_dep = Depends(get_language_model)


def get_reasoning_service(
    tenant: TenantContext = _tenant_dep,
    session: Session = _session_dep,
    settings: Settings = _settings_dep,
    model: LanguageModel = _model_dep,
) -> ReasoningService:
    return ReasoningService(session, tenant, model, settings.ai_daily_budget)


def get_action_service(
    tenant: TenantContext = _tenant_dep,
    session: Session = _session_dep,
) -> ActionService:
    return ActionService(session, tenant)
