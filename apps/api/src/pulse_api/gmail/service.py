"""Gmail connect, callback, and bounded manual sync.

Routes never see OAuth tokens. Tenant id comes from TenantContext or from the
server-side OAuth state created by that context. The callback does not read a
tenant id from the query string.
"""

import base64
import hashlib
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pulse_api.attention_engine import AttentionEngine
from pulse_api.config import Settings
from pulse_api.context import TenantContext
from pulse_api.crypto import ENCRYPTION_KEY_VERSION, TokenCipherError, decrypt_token, encrypt_token
from pulse_api.errors import ConflictError, ForbiddenError, NotFoundError, UnavailableError
from pulse_api.gmail.client import (
    SYNC_MAX_MESSAGES,
    SYNC_QUERY,
    GmailClient,
    GmailUnauthorized,
    GmailUnavailable,
    InvalidGrant,
    OAuthTokens,
    authorization_url,
)
from pulse_api.gmail.normalize import BadGmailMessage, is_received_inbox, normalize_message
from pulse_api.gmail.repository import (
    GmailConnectionRepository,
    MessageRepository,
    MessageThreadRepository,
)
from pulse_api.gmail.state_store import STATE_TTL_SECONDS, OAuthStateStore
from pulse_api.models import (
    GmailConnection,
    GmailConnectionStatus,
    Message,
    MessageThread,
    TenantUser,
    utcnow,
)

logger = logging.getLogger(__name__)

_MAX_STATE_LENGTH = 512
_MAX_CODE_LENGTH = 2048
_REFRESH_SKEW = timedelta(seconds=60)
_SAFE_REASONS = frozenset({"invalid_state", "denied", "failed", "conflict"})


@dataclass(frozen=True)
class SyncCounts:
    examined: int
    ingested: int
    skipped: int


@dataclass
class _Access:
    token: str
    unauthorized_retry: bool = False


class GmailService:
    def __init__(
        self,
        session: Session,
        tenant: TenantContext | None,
        settings: Settings,
        store: OAuthStateStore,
        client: GmailClient,
    ) -> None:
        self._session = session
        self._tenant_context = tenant
        self._settings = settings
        self._store = store
        self._client = client

    def start_connect(self) -> str:
        tenant = self._require_tenant()
        tenant.require_owner()
        self._require_configured()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(32)
        self._store.put(
            state,
            {
                "user_id": str(tenant.user_id),
                "tenant_id": str(tenant.tenant_id),
                "pkce_verifier": verifier,
            },
            STATE_TTL_SECONDS,
        )
        client_id = self._settings.google_client_id or ""
        redirect_uri = self._settings.google_redirect_uri or ""
        return authorization_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=_pkce_challenge(verifier),
        )

    def complete_callback(
        self,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
    ) -> str:
        if state is None or not state.strip() or len(state) > _MAX_STATE_LENGTH:
            return self._redirect(reason="invalid_state")
        self._require_configured()
        record = self._store.consume(state)
        if record is None:
            return self._redirect(reason="invalid_state")
        parsed = _parse_state(record)
        if parsed is None:
            return self._redirect(reason="invalid_state")
        user_id, tenant_id, verifier = parsed
        if not self._membership_exists(user_id, tenant_id):
            return self._redirect(reason="failed")
        if error == "access_denied":
            return self._redirect(reason="denied")
        if error:
            return self._redirect(reason="failed")
        if code is None or not code.strip() or len(code) > _MAX_CODE_LENGTH:
            return self._redirect(reason="failed")
        redirect_uri = self._settings.google_redirect_uri or ""
        try:
            tokens = self._client.exchange_code(
                code=code,
                verifier=verifier,
                redirect_uri=redirect_uri,
            )
            profile = self._client.get_profile(tokens.access_token)
        except (InvalidGrant, GmailUnavailable):
            return self._redirect(reason="failed")
        repository = GmailConnectionRepository(self._session, tenant_id)
        if repository.other_tenant_owns_mailbox(profile.email):
            return self._redirect(reason="conflict")
        try:
            connection = repository.get_by_mailbox(profile.email)
            if connection is None:
                connection = repository.add(
                    GmailConnection(
                        tenant_id=tenant_id,
                        connected_by=user_id,
                        external_account_id=profile.email,
                        status=GmailConnectionStatus.ACTIVE,
                        encryption_key_version=ENCRYPTION_KEY_VERSION,
                        scopes="",
                    )
                )
            connection.connected_by = user_id
            connection.status = GmailConnectionStatus.ACTIVE
            connection.history_id = profile.history_id or connection.history_id
            connection.last_error_code = None
            self._apply_tokens(connection, tokens, keep_refresh=connection.encrypted_refresh_token)
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            return self._redirect(reason="conflict")
        logger.info("gmail mailbox connected")
        return self._redirect(connected=True)

    def list_connections(self) -> list[GmailConnection]:
        tenant = self._require_tenant()
        rows = GmailConnectionRepository(self._session, tenant.tenant_id).list(limit=100, offset=0)
        return list(rows)

    def disconnect(self, connection_id: UUID) -> GmailConnection:
        tenant = self._require_tenant()
        tenant.require_owner()
        connection = self._connection(tenant, connection_id)
        refresh = self._decrypt_optional(connection.encrypted_refresh_token)
        if refresh:
            try:
                self._client.revoke_token(refresh)
            except (InvalidGrant, GmailUnavailable):
                pass
        self._clear_credentials(connection, "revoked")
        self._session.flush()
        logger.info("gmail mailbox disconnected")
        return connection

    def sync(self, connection_id: UUID) -> SyncCounts:
        tenant = self._require_tenant()
        self._require_configured()
        connection = self._connection(tenant, connection_id)
        if connection.status != GmailConnectionStatus.ACTIVE:
            raise ConflictError("gmail authorization expired")
        access = _Access(self._usable_access_token(connection))
        messages = MessageRepository(self._session, tenant.tenant_id)
        identifiers = self._call_gmail(
            connection,
            access,
            lambda token: self._client.list_message_ids(
                token,
                query=SYNC_QUERY,
                limit=SYNC_MAX_MESSAGES,
            ),
        )
        examined = 0
        ingested = 0
        skipped = 0
        for message_id in identifiers:
            examined += 1

            def _load_message(token: str, current_id: str = message_id) -> dict[str, Any]:
                return self._client.get_message(token, current_id)

            raw = self._call_gmail(connection, access, _load_message)
            if not is_received_inbox(raw.get("labelIds")):
                skipped += 1
                continue
            try:
                normalized = normalize_message(raw)
            except BadGmailMessage:
                connection.last_error_code = "bad_message"
                connection.updated_at = utcnow()
                self._session.commit()
                raise ConflictError("gmail message could not be stored") from None
            event = messages.ingest(normalized)
            if event is not None:
                AttentionEngine(self._session, tenant).apply(event)
                ingested += 1
            else:
                skipped += 1
            self._session.commit()
        profile = self._call_gmail(
            connection,
            access,
            self._client.get_profile,
        )
        if profile.history_id:
            connection.history_id = profile.history_id
        connection.last_synced_at = utcnow()
        connection.last_error_code = None
        connection.updated_at = utcnow()
        self._session.flush()
        logger.info("gmail sync completed", extra={"ingested": ingested})
        return SyncCounts(examined=examined, ingested=ingested, skipped=skipped)

    def list_threads(self, *, limit: int, offset: int) -> list[MessageThread]:
        tenant = self._require_tenant()
        rows = MessageThreadRepository(self._session, tenant.tenant_id).list(
            limit=limit,
            offset=offset,
        )
        return list(rows)

    def get_thread(self, thread_id: UUID) -> MessageThread:
        tenant = self._require_tenant()
        row = MessageThreadRepository(self._session, tenant.tenant_id).get(thread_id)
        if row is None:
            raise NotFoundError("message thread not found")
        return row

    def list_messages(self, *, limit: int, offset: int) -> list[Message]:
        tenant = self._require_tenant()
        return list(
            MessageRepository(self._session, tenant.tenant_id).list_recent(
                limit=limit, offset=offset
            )
        )

    def get_message(self, message_id: UUID) -> Message:
        tenant = self._require_tenant()
        row = MessageRepository(self._session, tenant.tenant_id).get(message_id)
        if row is None:
            raise NotFoundError("message not found")
        return row

    def _connection(self, tenant: TenantContext, connection_id: UUID) -> GmailConnection:
        row = GmailConnectionRepository(self._session, tenant.tenant_id).get(connection_id)
        if row is None:
            raise NotFoundError("gmail connection not found")
        return row

    def _usable_access_token(self, connection: GmailConnection) -> str:
        if not _needs_refresh(connection):
            return self._decrypt_required(connection.encrypted_access_token)
        return self._refresh_access_token(connection)

    def _refresh_access_token(self, connection: GmailConnection) -> str:
        if connection.encrypted_refresh_token is None:
            self._clear_credentials(connection, "invalid_grant")
            self._session.commit()
            raise ConflictError("gmail authorization expired")
        refresh = self._decrypt_required(connection.encrypted_refresh_token)
        try:
            tokens = self._client.refresh_access_token(refresh)
        except InvalidGrant:
            self._clear_credentials(connection, "invalid_grant")
            self._session.commit()
            raise ConflictError("gmail authorization expired") from None
        except GmailUnavailable:
            raise UnavailableError("gmail is unavailable") from None
        self._apply_tokens(connection, tokens, keep_refresh=connection.encrypted_refresh_token)
        self._session.commit()
        return tokens.access_token

    def _call_gmail[T](
        self,
        connection: GmailConnection,
        access: _Access,
        call: Callable[[str], T],
    ) -> T:
        """Run one Gmail read. A 401 refreshes once and retries that call once."""
        try:
            return call(access.token)
        except GmailUnauthorized:
            pass
        except GmailUnavailable:
            self._mark_unavailable(connection)
            raise UnavailableError("gmail is unavailable") from None
        if access.unauthorized_retry:
            self._mark_unavailable(connection)
            raise UnavailableError("gmail is unavailable")
        access.token = self._refresh_access_token(connection)
        access.unauthorized_retry = True
        try:
            return call(access.token)
        except (GmailUnauthorized, GmailUnavailable):
            self._mark_unavailable(connection)
            raise UnavailableError("gmail is unavailable") from None

    def _apply_tokens(
        self,
        connection: GmailConnection,
        tokens: OAuthTokens,
        *,
        keep_refresh: bytes | None,
    ) -> None:
        key = self._key()
        connection.encrypted_access_token = encrypt_token(key, tokens.access_token)
        if tokens.refresh_token:
            connection.encrypted_refresh_token = encrypt_token(key, tokens.refresh_token)
        else:
            connection.encrypted_refresh_token = keep_refresh
        connection.access_token_expires_at = utcnow() + timedelta(seconds=tokens.expires_in)
        connection.encryption_key_version = ENCRYPTION_KEY_VERSION
        connection.scopes = (tokens.scopes or "")[:500]
        connection.updated_at = utcnow()

    def _clear_credentials(self, connection: GmailConnection, error_code: str) -> None:
        connection.status = GmailConnectionStatus.REVOKED
        connection.encrypted_access_token = None
        connection.encrypted_refresh_token = None
        connection.access_token_expires_at = None
        connection.last_error_code = error_code
        connection.updated_at = utcnow()

    def _mark_unavailable(self, connection: GmailConnection) -> None:
        connection.last_error_code = "unavailable"
        connection.updated_at = utcnow()
        self._session.commit()

    def _decrypt_required(self, payload: bytes | None) -> str:
        if payload is None:
            raise UnavailableError("gmail is unavailable")
        try:
            return decrypt_token(self._key(), payload)
        except TokenCipherError:
            raise UnavailableError("gmail is unavailable") from None

    def _decrypt_optional(self, payload: bytes | None) -> str | None:
        key = self._settings.integration_encryption_key
        if payload is None or key is None:
            return None
        try:
            return decrypt_token(key, payload)
        except TokenCipherError:
            return None

    def _key(self) -> str:
        key = self._settings.integration_encryption_key
        if key is None:
            raise UnavailableError("gmail is not configured")
        return key

    def _require_configured(self) -> None:
        settings = self._settings
        if (
            settings.integration_encryption_key is None
            or settings.google_client_id is None
            or settings.google_client_secret is None
            or settings.google_redirect_uri is None
        ):
            raise UnavailableError("gmail is not configured")

    def _require_tenant(self) -> TenantContext:
        if self._tenant_context is None:
            raise ForbiddenError("tenant membership required")
        return self._tenant_context

    def _membership_exists(self, user_id: UUID, tenant_id: UUID) -> bool:
        statement = select(TenantUser.id).where(
            TenantUser.user_id == user_id,
            TenantUser.tenant_id == tenant_id,
        )
        return self._session.scalar(statement) is not None

    def _redirect(self, *, connected: bool = False, reason: str | None = None) -> str:
        base = self._settings.web_app_url.rstrip("/")
        if connected:
            return f"{base}/?gmail=connected"
        safe = reason if reason in _SAFE_REASONS else "failed"
        return f"{base}/?gmail=error&reason={safe}"


def _parse_state(record: dict[str, str]) -> tuple[UUID, UUID, str] | None:
    verifier = record.get("pkce_verifier")
    if not verifier:
        return None
    try:
        user_id = UUID(record["user_id"])
        tenant_id = UUID(record["tenant_id"])
    except (KeyError, ValueError):
        return None
    return user_id, tenant_id, verifier


def _needs_refresh(connection: GmailConnection) -> bool:
    if connection.encrypted_access_token is None or connection.access_token_expires_at is None:
        return True
    expires = connection.access_token_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= utcnow() + _REFRESH_SKEW


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
