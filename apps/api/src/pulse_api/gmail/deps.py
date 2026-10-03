"""Gmail dependencies. The callback does not depend on Clerk."""

from fastapi import Depends
from sqlalchemy.orm import Session

from pulse_api.config import Settings, get_settings
from pulse_api.context import TenantContext
from pulse_api.deps import get_session, require_tenant
from pulse_api.gmail.client import GmailClient, UrllibGmailClient
from pulse_api.gmail.service import GmailService
from pulse_api.gmail.state_store import OAuthStateStore, RedisOAuthStateStore

_settings_dep = Depends(get_settings)
_session_dep = Depends(get_session)
_tenant_dep = Depends(require_tenant)


def get_oauth_state_store(settings: Settings = _settings_dep) -> OAuthStateStore:
    return RedisOAuthStateStore(settings.redis_url)


def get_gmail_client(settings: Settings = _settings_dep) -> GmailClient:
    return UrllibGmailClient(settings)


_store_dep = Depends(get_oauth_state_store)
_client_dep = Depends(get_gmail_client)


def get_gmail_service(
    tenant: TenantContext = _tenant_dep,
    session: Session = _session_dep,
    settings: Settings = _settings_dep,
    store: OAuthStateStore = _store_dep,
    client: GmailClient = _client_dep,
) -> GmailService:
    return GmailService(session, tenant, settings, store, client)


def get_gmail_callback_service(
    session: Session = _session_dep,
    settings: Settings = _settings_dep,
    store: OAuthStateStore = _store_dep,
    client: GmailClient = _client_dep,
) -> GmailService:
    return GmailService(session, None, settings, store, client)
