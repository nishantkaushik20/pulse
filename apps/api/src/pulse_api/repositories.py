"""Tenant-scoped persistence. Queries on tenant-owned rows always filter tenant_id."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Select, case, delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from pulse_api.errors import NotFoundError
from pulse_api.models import (
    Action,
    ActionApproval,
    AttentionItem,
    AttentionPriority,
    AttentionStatus,
    BusinessEvent,
    Contact,
    Customer,
    Tenant,
    TenantUser,
    User,
    utcnow,
)

INBOX_LIMIT = 50

_PROTECTED_COLUMNS = frozenset({"id", "tenant_id", "created_at"})


class TenantRepository[RowT]:
    """Base for repositories that must not accept a client-supplied tenant id."""

    model: type[RowT]

    def __init__(self, session: Session, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def _select(self) -> Select[Any]:
        return select(self.model).where(self.model.tenant_id == self._tenant_id)  # type: ignore[attr-defined]

    def get(self, entity_id: UUID) -> RowT | None:
        statement = self._select().where(self.model.id == entity_id)  # type: ignore[attr-defined]
        return cast(RowT | None, self._session.scalar(statement))

    def list(self, *, limit: int, offset: int) -> Sequence[RowT]:
        statement = self._select().order_by(
            self.model.created_at.desc(),  # type: ignore[attr-defined]
            self.model.id.desc(),  # type: ignore[attr-defined]
        )
        rows = self._session.scalars(statement.limit(limit).offset(offset)).all()
        return cast(Sequence[RowT], rows)

    def _insert(self, row: RowT) -> RowT:
        row.tenant_id = self._tenant_id  # type: ignore[attr-defined]
        self._session.add(row)
        self._session.flush()
        return row


class CustomerRepository(TenantRepository[Customer]):
    model = Customer

    def add(
        self,
        *,
        name: str,
        company_name: str | None,
        email: str | None,
        phone: str | None,
        status: str,
    ) -> Customer:
        return self._insert(
            Customer(
                tenant_id=self._tenant_id,
                name=name,
                company_name=company_name,
                email=email,
                phone=phone,
                status=status,
            )
        )

    def apply_update(self, customer: Customer, changes: dict[str, Any]) -> Customer:
        _apply_changes(customer, changes)
        customer.updated_at = utcnow()
        self._session.flush()
        return customer

    def delete(self, customer_id: UUID) -> bool:
        result = self._session.execute(
            delete(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == self._tenant_id,
            )
        )
        return _rowcount(result) == 1


class ContactRepository(TenantRepository[Contact]):
    model = Contact

    def list_for_customer(self, customer_id: UUID, *, limit: int, offset: int) -> Sequence[Contact]:
        statement = (
            self._select()
            .where(Contact.customer_id == customer_id)
            .order_by(Contact.created_at.desc(), Contact.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return cast(Sequence[Contact], self._session.scalars(statement).all())

    def count_for_customer(self, customer_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(Contact)
            .where(Contact.tenant_id == self._tenant_id, Contact.customer_id == customer_id)
        )
        return int(self._session.scalar(statement) or 0)

    def add(
        self,
        *,
        customer_id: UUID,
        name: str,
        email: str | None,
        phone: str | None,
    ) -> Contact:
        self._require_customer(customer_id)
        return self._insert(
            Contact(
                tenant_id=self._tenant_id,
                customer_id=customer_id,
                name=name,
                email=email,
                phone=phone,
            )
        )

    def apply_update(self, contact: Contact, changes: dict[str, Any]) -> Contact:
        customer_id = changes.get("customer_id")
        if isinstance(customer_id, UUID):
            self._require_customer(customer_id)
        _apply_changes(contact, changes)
        contact.updated_at = utcnow()
        self._session.flush()
        return contact

    def delete(self, contact_id: UUID) -> bool:
        result = self._session.execute(
            delete(Contact).where(Contact.id == contact_id, Contact.tenant_id == self._tenant_id)
        )
        return _rowcount(result) == 1

    def _require_customer(self, customer_id: UUID) -> None:
        statement = select(Customer.id).where(
            Customer.id == customer_id,
            Customer.tenant_id == self._tenant_id,
        )
        if self._session.scalar(statement) is None:
            raise NotFoundError()


class BusinessEventRepository(TenantRepository[BusinessEvent]):
    model = BusinessEvent

    def add(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: UUID,
        source: str,
        occurred_at: datetime,
        data: dict[str, Any],
    ) -> BusinessEvent:
        return self._insert(
            BusinessEvent(
                tenant_id=self._tenant_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                source=source,
                occurred_at=occurred_at,
                data=data,
            )
        )


class AttentionRepository(TenantRepository[AttentionItem]):
    model = AttentionItem

    def add(
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
        return self._insert(
            AttentionItem(
                tenant_id=self._tenant_id,
                item_type=item_type,
                priority=priority,
                title=title,
                description=description,
                entity_type=entity_type,
                entity_id=entity_id,
                due_at=due_at,
            )
        )

    def insert_idempotent(
        self,
        *,
        item_type: str,
        priority: str,
        title: str,
        description: str | None,
        entity_type: str,
        entity_id: UUID,
    ) -> UUID | None:
        """Insert one attention item, or none when the tenant already has this source.

        The unique key is (tenant_id, type, entity_type, entity_id).
        """
        item_id = uuid4()
        now = utcnow()
        statement = (
            _dialect_insert(self._session)(AttentionItem)
            .values(
                id=item_id,
                tenant_id=self._tenant_id,
                item_type=item_type,
                priority=priority,
                title=title,
                description=description,
                status=AttentionStatus.OPEN,
                entity_type=entity_type,
                entity_id=entity_id,
                due_at=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "type", "entity_type", "entity_id"],
            )
            .returning(AttentionItem.id)
        )
        return cast(UUID | None, self._session.execute(statement).scalar_one_or_none())

    def list_open(self, *, limit: int = INBOX_LIMIT) -> Sequence[AttentionItem]:
        """Open items for the inbox.

        Priority is HIGH, then MEDIUM, then LOW. Equal priority is newer first.
        ``id`` descending breaks remaining ties. Lexical ordering of the priority
        strings is not used, because that would place LOW ahead of MEDIUM.
        """
        rank = case(
            (AttentionItem.priority == AttentionPriority.HIGH, 3),
            (AttentionItem.priority == AttentionPriority.MEDIUM, 2),
            (AttentionItem.priority == AttentionPriority.LOW, 1),
            else_=0,
        )
        statement = (
            self._select()
            .where(AttentionItem.status == AttentionStatus.OPEN)
            .order_by(rank.desc(), AttentionItem.created_at.desc(), AttentionItem.id.desc())
            .limit(limit)
        )
        return cast(Sequence[AttentionItem], self._session.scalars(statement).all())


class ActionRepository(TenantRepository[Action]):
    model = Action

    def add(
        self,
        *,
        action_type: str,
        requested_by: UUID,
        entity_type: str | None,
        entity_id: UUID | None,
        action_input: dict[str, Any],
    ) -> Action:
        return self._insert(
            Action(
                tenant_id=self._tenant_id,
                action_type=action_type,
                requested_by=requested_by,
                entity_type=entity_type,
                entity_id=entity_id,
                input=action_input,
            )
        )


class ApprovalRepository(TenantRepository[ActionApproval]):
    model = ActionApproval

    def list_for_action(
        self, action_id: UUID, *, limit: int, offset: int
    ) -> Sequence[ActionApproval]:
        statement = (
            self._select()
            .where(ActionApproval.action_id == action_id)
            .order_by(ActionApproval.created_at.desc(), ActionApproval.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return cast(Sequence[ActionApproval], self._session.scalars(statement).all())

    def get_for_action(self, action_id: UUID, approval_id: UUID) -> ActionApproval | None:
        statement = self._select().where(
            ActionApproval.id == approval_id,
            ActionApproval.action_id == action_id,
        )
        return cast(ActionApproval | None, self._session.scalar(statement))

    def add(
        self,
        *,
        action_id: UUID,
        approved_by: UUID,
        status: str,
        approved_at: datetime | None,
    ) -> ActionApproval:
        statement = select(Action.id).where(
            Action.id == action_id,
            Action.tenant_id == self._tenant_id,
        )
        if self._session.scalar(statement) is None:
            raise NotFoundError()
        return self._insert(
            ActionApproval(
                tenant_id=self._tenant_id,
                action_id=action_id,
                approved_by=approved_by,
                status=status,
                approved_at=approved_at,
            )
        )


def _dialect_insert(session: Session) -> Any:
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql_insert
    return sqlite_insert


def _rowcount(result: object) -> int:
    count = getattr(result, "rowcount", 0)
    if isinstance(count, int):
        return count
    return 0


def _apply_changes(row: Any, changes: dict[str, Any]) -> None:
    for key, value in changes.items():
        if key in _PROTECTED_COLUMNS:
            continue
        setattr(row, key, value)


def get_user_by_clerk_id(session: Session, clerk_user_id: str) -> User | None:
    return session.scalar(select(User).where(User.clerk_user_id == clerk_user_id))


def get_user(session: Session, user_id: UUID) -> User | None:
    return session.get(User, user_id)


def list_memberships(session: Session, tenant_id: UUID) -> Sequence[TenantUser]:
    statement = (
        select(TenantUser)
        .where(TenantUser.tenant_id == tenant_id)
        .order_by(TenantUser.created_at.asc(), TenantUser.id.asc())
    )
    return session.scalars(statement).all()


def get_tenant(session: Session, tenant_id: UUID) -> Tenant | None:
    return session.get(Tenant, tenant_id)
