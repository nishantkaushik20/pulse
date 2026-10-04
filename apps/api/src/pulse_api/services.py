"""Application services. Callers pass tenant context; they do not pass a client tenant id."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pulse_api.auth import ClerkIdentity
from pulse_api.briefing import BRIEFING_CAP, briefing_sort_key
from pulse_api.context import RequestContext, TenantContext, resolve_current_tenant
from pulse_api.errors import ConflictError, ForbiddenError, NotFoundError
from pulse_api.gmail.repository import MessageRepository
from pulse_api.matching import EXACT_EMAIL, customer_name, exact_email_customer
from pulse_api.models import (
    Action,
    ActionApproval,
    ActionStatus,
    ApprovalStatus,
    AttentionItem,
    AttentionStatus,
    AuditLog,
    BusinessEvent,
    Contact,
    Customer,
    Tenant,
    TenantRole,
    TenantUser,
    User,
    utcnow,
)
from pulse_api.repositories import (
    INBOX_LIMIT,
    ActionRepository,
    ApprovalRepository,
    AttentionRepository,
    BusinessEventRepository,
    ContactRepository,
    CustomerRepository,
    get_tenant,
    get_user,
    get_user_by_clerk_id,
    list_memberships,
)

ProfileLookup = Callable[[str], tuple[str, str]]


def ensure_user(session: Session, identity: ClerkIdentity, lookup: ProfileLookup) -> User:
    existing = get_user_by_clerk_id(session, identity.clerk_user_id)
    if existing is not None:
        return existing
    email = identity.email
    name = identity.name or ""
    if email is None:
        email, looked_up_name = lookup(identity.clerk_user_id)
        name = identity.name or looked_up_name
    user = User(
        clerk_user_id=identity.clerk_user_id,
        email=email.lower()[:320],
        name=name[:200],
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raced = get_user_by_clerk_id(session, identity.clerk_user_id)
        if raced is None:
            raise
        return raced
    return user


def build_request_context(session: Session, user: User) -> RequestContext:
    return RequestContext(
        user_id=user.id,
        clerk_user_id=user.clerk_user_id,
        email=user.email,
        name=user.name,
        tenant=resolve_current_tenant(session, user.id),
    )


DISMISS_REASONS = frozenset({"not_relevant", "done", "waiting"})


@dataclass(frozen=True)
class InboxRow:
    item: AttentionItem
    source: str | None
    thread_id: UUID | None
    customer_name: str | None


class IdentityService:
    def __init__(self, session: Session, request: RequestContext) -> None:
        self._session = session
        self._request = request

    @property
    def request_context(self) -> RequestContext:
        return self._request

    def create_tenant(self, name: str) -> tuple[Tenant, TenantUser]:
        if self._request.tenant is not None:
            raise ConflictError("user already belongs to a tenant")
        tenant = Tenant(name=name)
        self._session.add(tenant)
        self._session.flush()
        membership = TenantUser(
            tenant_id=tenant.id,
            user_id=self._request.user_id,
            role=TenantRole.OWNER,
        )
        self._session.add(membership)
        self._session.flush()
        return tenant, membership

    def current_tenant(self) -> tuple[Tenant, TenantRole]:
        tenant_context = self._request.require_tenant()
        tenant = get_tenant(self._session, tenant_context.tenant_id)
        if tenant is None:
            raise NotFoundError()
        return tenant, tenant_context.role

    def rename_tenant(self, name: str) -> Tenant:
        tenant_context = self._request.require_tenant()
        tenant_context.require_owner()
        tenant = get_tenant(self._session, tenant_context.tenant_id)
        if tenant is None:
            raise NotFoundError()
        tenant.name = name
        tenant.updated_at = utcnow()
        self._session.flush()
        return tenant

    def list_members(self) -> list[tuple[TenantUser, User]]:
        tenant_context = self._request.require_tenant()
        rows: list[tuple[TenantUser, User]] = []
        for membership in list_memberships(self._session, tenant_context.tenant_id):
            user = get_user(self._session, membership.user_id)
            if user is None:
                continue
            rows.append((membership, user))
        return rows

    def add_member(self, user_id: UUID, role: TenantRole) -> tuple[TenantUser, User]:
        tenant_context = self._request.require_tenant()
        tenant_context.require_owner()
        user = get_user(self._session, user_id)
        if user is None:
            raise NotFoundError()
        membership = TenantUser(
            tenant_id=tenant_context.tenant_id,
            user_id=user_id,
            role=role,
        )
        self._session.add(membership)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("membership already exists") from exc
        return membership, user


class CustomerService:
    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self._customers = CustomerRepository(session, tenant.tenant_id)
        self._contacts = ContactRepository(session, tenant.tenant_id)

    def list(self, *, limit: int, offset: int) -> Sequence[Customer]:
        return self._customers.list(limit=limit, offset=offset)

    def create(
        self,
        *,
        name: str,
        company_name: str | None,
        email: str | None,
        phone: str | None,
        status: str,
    ) -> Customer:
        return self._customers.add(
            name=name,
            company_name=company_name,
            email=email,
            phone=phone,
            status=status,
        )

    def get(self, customer_id: UUID) -> Customer:
        customer = self._customers.get(customer_id)
        if customer is None:
            raise NotFoundError()
        return customer

    def update(self, customer_id: UUID, changes: dict[str, Any]) -> Customer:
        customer = self.get(customer_id)
        return self._customers.apply_update(customer, changes)

    def delete(self, customer_id: UUID) -> None:
        self.get(customer_id)
        if self._contacts.count_for_customer(customer_id):
            raise ConflictError("customer has contacts")
        try:
            deleted = self._customers.delete(customer_id)
        except IntegrityError as exc:
            raise ConflictError("customer has contacts") from exc
        if not deleted:
            raise NotFoundError()


class ContactService:
    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self._customers = CustomerRepository(session, tenant.tenant_id)
        self._contacts = ContactRepository(session, tenant.tenant_id)

    def list_for_customer(self, customer_id: UUID, *, limit: int, offset: int) -> Sequence[Contact]:
        self._require_customer(customer_id)
        return self._contacts.list_for_customer(customer_id, limit=limit, offset=offset)

    def create(
        self,
        customer_id: UUID,
        *,
        name: str,
        email: str | None,
        phone: str | None,
    ) -> Contact:
        self._require_customer(customer_id)
        return self._contacts.add(
            customer_id=customer_id,
            name=name,
            email=email,
            phone=phone,
        )

    def get(self, contact_id: UUID) -> Contact:
        contact = self._contacts.get(contact_id)
        if contact is None:
            raise NotFoundError()
        return contact

    def update(self, contact_id: UUID, changes: dict[str, Any]) -> Contact:
        contact = self.get(contact_id)
        if "customer_id" in changes:
            self._require_customer(changes["customer_id"])
        return self._contacts.apply_update(contact, changes)

    def delete(self, contact_id: UUID) -> None:
        self.get(contact_id)
        if not self._contacts.delete(contact_id):
            raise NotFoundError()

    def _require_customer(self, customer_id: UUID) -> Customer:
        customer = self._customers.get(customer_id)
        if customer is None:
            raise NotFoundError()
        return customer


class BusinessEventService:
    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self._events = BusinessEventRepository(session, tenant.tenant_id)

    def list(self, *, limit: int, offset: int) -> Sequence[BusinessEvent]:
        return self._events.list(limit=limit, offset=offset)

    def create(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: UUID,
        source: str,
        occurred_at: datetime,
        data: dict[str, Any],
    ) -> BusinessEvent:
        return self._events.add(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            source=source,
            occurred_at=occurred_at,
            data=data,
        )

    def get(self, event_id: UUID) -> BusinessEvent:
        event = self._events.get(event_id)
        if event is None:
            raise NotFoundError()
        return event


class AttentionService:
    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self._session = session
        self._tenant = tenant
        self._items = AttentionRepository(session, tenant.tenant_id)
        self._messages = MessageRepository(session, tenant.tenant_id)

    def list(self, *, limit: int, offset: int) -> Sequence[AttentionItem]:
        return self._items.list(limit=limit, offset=offset)

    def list_inbox(self) -> Sequence[InboxRow]:
        """Open attention for the current tenant.

        Message bodies are not read. Exact email matches are recomputed and
        stored on the item. Customer rows are not created.
        """
        rows = self._items.list_open(limit=INBOX_LIMIT)
        message_ids = [
            row.entity_id
            for row in rows
            if row.entity_type == "message" and row.entity_id is not None
        ]
        messages = self._messages.get_many(message_ids)
        inbox: list[InboxRow] = []
        for row in rows:
            source = None
            thread_id = None
            name = None
            if row.entity_type == "message" and row.entity_id is not None:
                message = messages.get(row.entity_id)
                if message is not None:
                    source = message.source
                    thread_id = message.thread_id
                    name = self._refresh_match(row, message.from_email)
            inbox.append(InboxRow(item=row, source=source, thread_id=thread_id, customer_name=name))
        self._session.flush()
        return inbox

    def list_briefing(self) -> Sequence[InboxRow]:
        """At most five open items. Priority and age stay deterministic."""
        rows = list(self.list_inbox())
        moment = utcnow()
        rows.sort(key=lambda row: briefing_sort_key(row.item, moment))
        return rows[:BRIEFING_CAP]

    def _refresh_match(self, item: AttentionItem, email: str | None) -> str | None:
        customer_id, method = exact_email_customer(self._session, self._tenant.tenant_id, email)
        name = customer_name(self._session, self._tenant.tenant_id, customer_id)
        if customer_id is not None and name is None:
            customer_id = None
            method = None
        if method is not None and method != EXACT_EMAIL:
            customer_id = None
            method = None
            name = None
        if item.matched_customer_id != customer_id or item.match_method != method:
            item.matched_customer_id = customer_id
            item.match_method = method
            item.updated_at = utcnow()
        return name

    def create(
        self,
        *,
        item_type: str,
        priority: str,
        title: str,
        description: str | None,
        entity_type: str | None,
        entity_id: UUID | None,
        due_at: datetime | None,
    ) -> AttentionItem:
        try:
            return self._items.add(
                item_type=item_type,
                priority=priority,
                title=title,
                description=description,
                entity_type=entity_type,
                entity_id=entity_id,
                due_at=due_at,
            )
        except IntegrityError:
            self._session.rollback()
            raise ConflictError("attention item already exists") from None

    def get(self, item_id: UUID) -> AttentionItem:
        item = self._items.get(item_id)
        if item is None:
            raise NotFoundError()
        return item

    def resolve(self, item_id: UUID) -> AttentionItem:
        """Mark an open item resolved. Resolving again returns the same row."""
        item = self.get(item_id)
        if item.status != AttentionStatus.RESOLVED:
            moment = utcnow()
            item.status = AttentionStatus.RESOLVED
            item.resolved_at = moment
            item.resolved_by = self._tenant.user_id
            item.updated_at = moment
            self._session.flush()
        return item

    def dismiss(self, item_id: UUID, reason: str) -> AttentionItem:
        """Hide an item and record why. The row stays. The same reason is idempotent."""
        if reason not in DISMISS_REASONS:
            raise ConflictError("dismiss reason is not allowed")
        item = self.get(item_id)
        moment = utcnow()
        changed = False
        if item.status != AttentionStatus.RESOLVED:
            item.status = AttentionStatus.RESOLVED
            item.resolved_at = moment
            item.resolved_by = self._tenant.user_id
            changed = True
        if item.dismiss_reason != reason:
            item.dismiss_reason = reason
            changed = True
        if changed:
            item.updated_at = moment
            self._session.flush()
        return item


class ActionService:
    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self._session = session
        self._tenant = tenant
        self._actions = ActionRepository(session, tenant.tenant_id)
        self._approvals = ApprovalRepository(session, tenant.tenant_id)
        self._user_id = tenant.user_id

    def list(self, *, limit: int, offset: int) -> Sequence[Action]:
        return self._actions.list(limit=limit, offset=offset)

    def create(
        self,
        *,
        action_type: str,
        entity_type: str | None,
        entity_id: UUID | None,
        action_input: dict[str, Any],
    ) -> Action:
        return self._actions.add(
            action_type=action_type,
            requested_by=self._user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action_input=action_input,
        )

    def get(self, action_id: UUID) -> Action:
        action = self._actions.get(action_id)
        if action is None:
            raise NotFoundError()
        return action

    def list_approvals(
        self, action_id: UUID, *, limit: int, offset: int
    ) -> Sequence[ActionApproval]:
        self.get(action_id)
        return self._approvals.list_for_action(action_id, limit=limit, offset=offset)

    def create_approval(self, action_id: UUID, *, status: str) -> ActionApproval:
        self.get(action_id)
        approved_at = utcnow() if status == ApprovalStatus.APPROVED else None
        return self._approvals.add(
            action_id=action_id,
            approved_by=self._user_id,
            status=status,
            approved_at=approved_at,
        )

    def get_approval(self, action_id: UUID, approval_id: UUID) -> ActionApproval:
        self.get(action_id)
        approval = self._approvals.get_for_action(action_id, approval_id)
        if approval is None:
            raise NotFoundError()
        return approval

    def execute(self, action_id: UUID, idempotency_key: str) -> Action:
        """Run a low-risk action once. The same key returns the completed row."""
        key = idempotency_key.strip()
        if not key or len(key) > 100:
            raise ConflictError("idempotency key is required")
        existing = self._actions.get_by_idempotency(key)
        if existing is not None and existing.status == ActionStatus.COMPLETED:
            return existing
        if existing is not None and existing.id != action_id:
            raise ConflictError("idempotency key already used")
        action = self.get(action_id)
        if action.status == ActionStatus.COMPLETED:
            return action
        if action.action_type not in {"create_reminder", "store_draft"}:
            raise ForbiddenError("action is not executable")
        if action.action_type == "store_draft" and not self._approvals.has_approved(action.id):
            raise ForbiddenError("approval required")
        action.status = ActionStatus.EXECUTING
        action.idempotency_key = key
        self._session.flush()
        try:
            result = self._perform(action)
        except ValueError:
            action.status = ActionStatus.FAILED
            action.result = {"error_code": "invalid_input"}
            self._audit(action, "invalid_input")
            self._session.flush()
            return action
        action.status = ActionStatus.COMPLETED
        action.result = result
        action.completed_at = utcnow()
        self._audit(action, "completed")
        self._session.flush()
        return action

    def _perform(self, action: Action) -> dict[str, Any]:
        if action.action_type == "create_reminder":
            title = action.input.get("title")
            raw_due = action.input.get("due_at")
            if not isinstance(title, str) or not title.strip() or not isinstance(raw_due, str):
                raise ValueError("invalid_input")
            item = AttentionService(self._session, self._tenant).create(
                item_type="reminder",
                priority="MEDIUM",
                title=title.strip()[:200],
                description=None,
                entity_type=None,
                entity_id=None,
                due_at=datetime.fromisoformat(raw_due),
            )
            return {"attention_id": str(item.id)}
        text = action.input.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("invalid_input")
        return {"draft": text.strip()[:5000]}

    def _audit(self, action: Action, result_code: str) -> None:
        self._session.add(
            AuditLog(
                tenant_id=self._tenant.tenant_id,
                actor_user_id=self._user_id,
                action=action.action_type,
                target_type="action",
                target_id=action.id,
                result_code=result_code,
                metadata_json={"status": action.status},
            )
        )
