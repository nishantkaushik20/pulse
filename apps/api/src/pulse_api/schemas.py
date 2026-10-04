"""Request and response models. Tenant id is not an input."""

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pulse_api.models import (
    Action,
    ActionApproval,
    ActionStatus,
    ApprovalStatus,
    AttentionItem,
    AttentionPriority,
    AttentionStatus,
    BusinessEvent,
    Contact,
    Customer,
    CustomerStatus,
    TenantRole,
    TenantUser,
    User,
)

_JSON_LIMIT = 16_384


def _json_object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("must be a JSON object")
    encoded = json.dumps(value)
    if len(encoded.encode("utf-8")) > _JSON_LIMIT:
        raise ValueError("JSON exceeds 16KB")
    return value


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class Page(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10_000)


class UserOut(BaseModel):
    id: UUID
    clerk_user_id: str
    email: str
    name: str


class TenantOut(BaseModel):
    id: UUID
    name: str
    role: TenantRole


class MeOut(BaseModel):
    user: UserOut
    tenant: TenantOut | None


class TenantCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned


class TenantUpdate(TenantCreate):
    pass


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: UUID
    role: TenantRole = TenantRole.MEMBER


class MemberOut(BaseModel):
    user_id: UUID
    email: str
    name: str
    role: TenantRole
    created_at: datetime


class CustomerCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    status: CustomerStatus = CustomerStatus.ACTIVE

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned

    @field_validator("company_name", "email", "phone")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        return _optional_text(value)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.lower()


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    status: CustomerStatus | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned

    @field_validator("company_name", "email", "phone")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        return _optional_text(value)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.lower()


class CustomerOut(BaseModel):
    id: UUID
    name: str
    company_name: str | None
    email: str | None
    phone: str | None
    status: CustomerStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Customer) -> "CustomerOut":
        return cls(
            id=row.id,
            name=row.name,
            company_name=row.company_name,
            email=row.email,
            phone=row.phone,
            status=CustomerStatus(row.status),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class CustomerList(BaseModel):
    items: list[CustomerOut]


class ContactCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned

    @field_validator("email", "phone")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        return _optional_text(value)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.lower()


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    customer_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned

    @field_validator("email", "phone")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("email")
    @classmethod
    def lower_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.lower()


class ContactOut(BaseModel):
    id: UUID
    customer_id: UUID
    name: str
    email: str | None
    phone: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Contact) -> "ContactOut":
        return cls(
            id=row.id,
            customer_id=row.customer_id,
            name=row.name,
            email=row.email,
            phone=row.phone,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class ContactList(BaseModel):
    items: list[ContactOut]


class BusinessEventCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_type: str = Field(min_length=1, max_length=100)
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: UUID
    source: str = Field(min_length=1, max_length=64)
    occurred_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _json_object(value)


class BusinessEventOut(BaseModel):
    id: UUID
    event_type: str
    entity_type: str
    entity_id: UUID
    source: str
    occurred_at: datetime
    data: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: BusinessEvent) -> "BusinessEventOut":
        return cls(
            id=row.id,
            event_type=row.event_type,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            source=row.source,
            occurred_at=row.occurred_at,
            data=row.data,
            created_at=row.created_at,
        )


class BusinessEventList(BaseModel):
    items: list[BusinessEventOut]


class AttentionCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = Field(min_length=1, max_length=64)
    priority: AttentionPriority = AttentionPriority.MEDIUM
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: UUID | None = None
    due_at: datetime | None = None


class AttentionOut(BaseModel):
    id: UUID
    type: str
    priority: AttentionPriority
    title: str
    description: str | None
    status: AttentionStatus
    entity_type: str | None
    entity_id: UUID | None
    due_at: datetime | None
    dismiss_reason: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: AttentionItem) -> "AttentionOut":
        return cls(
            id=row.id,
            type=row.item_type,
            priority=AttentionPriority(row.priority),
            title=row.title,
            description=row.description,
            status=AttentionStatus(row.status),
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            due_at=row.due_at,
            dismiss_reason=row.dismiss_reason,
            resolved_at=row.resolved_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class AttentionList(BaseModel):
    items: list[AttentionOut]


class AttentionInboxItem(BaseModel):
    id: UUID
    type: str
    title: str
    description: str | None
    priority: AttentionPriority
    status: AttentionStatus
    created_at: datetime
    source: str | None
    entity_type: str | None
    entity_id: UUID | None
    thread_id: UUID | None
    customer_id: UUID | None
    customer_name: str | None
    match_method: str | None
    dismiss_reason: str | None

    @classmethod
    def from_row(
        cls,
        row: AttentionItem,
        source: str | None,
        *,
        thread_id: UUID | None,
        customer_name: str | None,
    ) -> "AttentionInboxItem":
        return cls(
            id=row.id,
            type=row.item_type,
            title=row.title,
            description=row.description,
            priority=AttentionPriority(row.priority),
            status=AttentionStatus(row.status),
            created_at=row.created_at,
            source=source,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            thread_id=thread_id,
            customer_id=row.matched_customer_id,
            customer_name=customer_name,
            match_method=row.match_method,
            dismiss_reason=row.dismiss_reason,
        )


class AttentionDismiss(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: Literal["not_relevant", "done", "waiting"]


class AiTextOut(BaseModel):
    text: str


class AttentionInbox(BaseModel):
    items: list[AttentionInboxItem]


class ActionExecute(BaseModel):
    model_config = ConfigDict(extra="ignore")

    idempotency_key: str = Field(min_length=1, max_length=100)


class ActionCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_type: str = Field(min_length=1, max_length=100)
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: UUID | None = None
    input: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _json_object(value)


class ActionOut(BaseModel):
    id: UUID
    action_type: str
    status: ActionStatus
    requested_by: UUID
    entity_type: str | None
    entity_id: UUID | None
    input: dict[str, Any]
    result: dict[str, Any] | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_row(cls, row: Action) -> "ActionOut":
        return cls(
            id=row.id,
            action_type=row.action_type,
            status=ActionStatus(row.status),
            requested_by=row.requested_by,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            input=row.input,
            result=row.result,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )


class ActionList(BaseModel):
    items: list[ActionOut]


class ApprovalCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: ApprovalStatus


class ApprovalOut(BaseModel):
    id: UUID
    action_id: UUID
    approved_by: UUID
    status: ApprovalStatus
    approved_at: datetime | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: ActionApproval) -> "ApprovalOut":
        return cls(
            id=row.id,
            action_id=row.action_id,
            approved_by=row.approved_by,
            status=ApprovalStatus(row.status),
            approved_at=row.approved_at,
            created_at=row.created_at,
        )


class ApprovalList(BaseModel):
    items: list[ApprovalOut]


def user_out(user_id: UUID, clerk_user_id: str, email: str, name: str) -> UserOut:
    return UserOut(id=user_id, clerk_user_id=clerk_user_id, email=email, name=name)


def member_out(membership: TenantUser, user: User) -> MemberOut:
    return MemberOut(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=TenantRole(membership.role),
        created_at=membership.created_at,
    )
