"""Minimal REST API for identity and tenant-scoped records."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from pulse_api.deps import (
    get_action_service,
    get_attention_service,
    get_contact_service,
    get_customer_service,
    get_event_service,
    get_identity_service,
)
from pulse_api.models import TenantRole, utcnow
from pulse_api.schemas import (
    ActionCreate,
    ActionList,
    ActionOut,
    ApprovalCreate,
    ApprovalList,
    ApprovalOut,
    AttentionCreate,
    AttentionInbox,
    AttentionInboxItem,
    AttentionList,
    AttentionOut,
    BusinessEventCreate,
    BusinessEventList,
    BusinessEventOut,
    ContactCreate,
    ContactList,
    ContactOut,
    ContactUpdate,
    CustomerCreate,
    CustomerList,
    CustomerOut,
    CustomerUpdate,
    MemberCreate,
    MemberOut,
    MeOut,
    TenantCreate,
    TenantOut,
    TenantUpdate,
    UserOut,
    member_out,
)
from pulse_api.services import (
    ActionService,
    AttentionService,
    BusinessEventService,
    ContactService,
    CustomerService,
    IdentityService,
)

identity_router = APIRouter()
customer_router = APIRouter()
operations_router = APIRouter()

_identity_service = Depends(get_identity_service)
_customers = Depends(get_customer_service)
_contacts = Depends(get_contact_service)
_events = Depends(get_event_service)
_attention = Depends(get_attention_service)
_actions = Depends(get_action_service)
_limit = Query(default=50, ge=1, le=100)
_offset = Query(default=0, ge=0, le=10_000)


@identity_router.get("/me", response_model=MeOut)
def read_me(service: IdentityService = _identity_service) -> MeOut:
    request = service.request_context
    tenant_out = None
    if request.tenant is not None:
        tenant, role = service.current_tenant()
        tenant_out = TenantOut(id=tenant.id, name=tenant.name, role=role)
    return MeOut(
        user=UserOut(
            id=request.user_id,
            clerk_user_id=request.clerk_user_id,
            email=request.email,
            name=request.name,
        ),
        tenant=tenant_out,
    )


@identity_router.post("/tenants", response_model=TenantOut, status_code=201)
def create_tenant(
    body: TenantCreate,
    service: IdentityService = _identity_service,
) -> TenantOut:
    tenant, membership = service.create_tenant(body.name)
    return TenantOut(id=tenant.id, name=tenant.name, role=TenantRole(membership.role))


@identity_router.get("/tenant", response_model=TenantOut)
def read_tenant(service: IdentityService = _identity_service) -> TenantOut:
    tenant, role = service.current_tenant()
    return TenantOut(id=tenant.id, name=tenant.name, role=role)


@identity_router.patch("/tenant", response_model=TenantOut)
def rename_tenant(
    body: TenantUpdate,
    service: IdentityService = _identity_service,
) -> TenantOut:
    tenant = service.rename_tenant(body.name)
    _tenant, role = service.current_tenant()
    return TenantOut(id=tenant.id, name=tenant.name, role=role)


@identity_router.get("/tenant/members", response_model=list[MemberOut])
def list_members(service: IdentityService = _identity_service) -> list[MemberOut]:
    return [member_out(membership, user) for membership, user in service.list_members()]


@identity_router.post("/tenant/members", response_model=MemberOut, status_code=201)
def add_member(
    body: MemberCreate,
    service: IdentityService = _identity_service,
) -> MemberOut:
    membership, user = service.add_member(body.user_id, body.role)
    return member_out(membership, user)


@customer_router.get("/customers", response_model=CustomerList)
def list_customers(
    limit: int = _limit,
    offset: int = _offset,
    service: CustomerService = _customers,
) -> CustomerList:
    rows = service.list(limit=limit, offset=offset)
    return CustomerList(items=[CustomerOut.from_row(row) for row in rows])


@customer_router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(
    body: CustomerCreate,
    service: CustomerService = _customers,
) -> CustomerOut:
    row = service.create(
        name=body.name,
        company_name=body.company_name,
        email=body.email,
        phone=body.phone,
        status=body.status,
    )
    return CustomerOut.from_row(row)


@customer_router.get("/customers/{customer_id}", response_model=CustomerOut)
def read_customer(customer_id: UUID, service: CustomerService = _customers) -> CustomerOut:
    return CustomerOut.from_row(service.get(customer_id))


@customer_router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: UUID,
    body: CustomerUpdate,
    service: CustomerService = _customers,
) -> CustomerOut:
    row = service.update(customer_id, body.model_dump(exclude_unset=True))
    return CustomerOut.from_row(row)


@customer_router.delete("/customers/{customer_id}", status_code=204)
def delete_customer(customer_id: UUID, service: CustomerService = _customers) -> Response:
    service.delete(customer_id)
    return Response(status_code=204)


@customer_router.get("/customers/{customer_id}/contacts", response_model=ContactList)
def list_contacts(
    customer_id: UUID,
    limit: int = _limit,
    offset: int = _offset,
    service: ContactService = _contacts,
) -> ContactList:
    rows = service.list_for_customer(customer_id, limit=limit, offset=offset)
    return ContactList(items=[ContactOut.from_row(row) for row in rows])


@customer_router.post(
    "/customers/{customer_id}/contacts",
    response_model=ContactOut,
    status_code=201,
)
def create_contact(
    customer_id: UUID,
    body: ContactCreate,
    service: ContactService = _contacts,
) -> ContactOut:
    row = service.create(customer_id, name=body.name, email=body.email, phone=body.phone)
    return ContactOut.from_row(row)


@customer_router.get("/contacts/{contact_id}", response_model=ContactOut)
def read_contact(contact_id: UUID, service: ContactService = _contacts) -> ContactOut:
    return ContactOut.from_row(service.get(contact_id))


@customer_router.patch("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: UUID,
    body: ContactUpdate,
    service: ContactService = _contacts,
) -> ContactOut:
    row = service.update(contact_id, body.model_dump(exclude_unset=True))
    return ContactOut.from_row(row)


@customer_router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: UUID, service: ContactService = _contacts) -> Response:
    service.delete(contact_id)
    return Response(status_code=204)


@operations_router.get("/business-events", response_model=BusinessEventList)
def list_events(
    limit: int = _limit,
    offset: int = _offset,
    service: BusinessEventService = _events,
) -> BusinessEventList:
    rows = service.list(limit=limit, offset=offset)
    return BusinessEventList(items=[BusinessEventOut.from_row(row) for row in rows])


@operations_router.post("/business-events", response_model=BusinessEventOut, status_code=201)
def create_event(
    body: BusinessEventCreate,
    service: BusinessEventService = _events,
) -> BusinessEventOut:
    row = service.create(
        event_type=body.event_type,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        source=body.source,
        occurred_at=body.occurred_at or utcnow(),
        data=body.data,
    )
    return BusinessEventOut.from_row(row)


@operations_router.get("/business-events/{event_id}", response_model=BusinessEventOut)
def read_event(event_id: UUID, service: BusinessEventService = _events) -> BusinessEventOut:
    return BusinessEventOut.from_row(service.get(event_id))


@operations_router.get("/attention", response_model=AttentionInbox)
def list_attention_inbox(service: AttentionService = _attention) -> AttentionInbox:
    """Open attention for the authenticated tenant. The tenant is not a parameter."""
    return AttentionInbox(
        items=[AttentionInboxItem.from_row(row, source) for row, source in service.list_inbox()]
    )


@operations_router.post("/attention/{item_id}/resolve", response_model=AttentionOut)
def resolve_attention(item_id: UUID, service: AttentionService = _attention) -> AttentionOut:
    return AttentionOut.from_row(service.resolve(item_id))


@operations_router.get("/attention-items", response_model=AttentionList)
def list_attention(
    limit: int = _limit,
    offset: int = _offset,
    service: AttentionService = _attention,
) -> AttentionList:
    rows = service.list(limit=limit, offset=offset)
    return AttentionList(items=[AttentionOut.from_row(row) for row in rows])


@operations_router.post("/attention-items", response_model=AttentionOut, status_code=201)
def create_attention(
    body: AttentionCreate,
    service: AttentionService = _attention,
) -> AttentionOut:
    row = service.create(
        item_type=body.type,
        priority=body.priority,
        title=body.title,
        description=body.description,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        due_at=body.due_at,
    )
    return AttentionOut.from_row(row)


@operations_router.get("/attention-items/{item_id}", response_model=AttentionOut)
def read_attention(item_id: UUID, service: AttentionService = _attention) -> AttentionOut:
    return AttentionOut.from_row(service.get(item_id))


@operations_router.get("/actions", response_model=ActionList)
def list_actions(
    limit: int = _limit,
    offset: int = _offset,
    service: ActionService = _actions,
) -> ActionList:
    rows = service.list(limit=limit, offset=offset)
    return ActionList(items=[ActionOut.from_row(row) for row in rows])


@operations_router.post("/actions", response_model=ActionOut, status_code=201)
def create_action(body: ActionCreate, service: ActionService = _actions) -> ActionOut:
    row = service.create(
        action_type=body.action_type,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        action_input=body.input,
    )
    return ActionOut.from_row(row)


@operations_router.get("/actions/{action_id}", response_model=ActionOut)
def read_action(action_id: UUID, service: ActionService = _actions) -> ActionOut:
    return ActionOut.from_row(service.get(action_id))


@operations_router.get("/actions/{action_id}/approvals", response_model=ApprovalList)
def list_approvals(
    action_id: UUID,
    limit: int = _limit,
    offset: int = _offset,
    service: ActionService = _actions,
) -> ApprovalList:
    rows = service.list_approvals(action_id, limit=limit, offset=offset)
    return ApprovalList(items=[ApprovalOut.from_row(row) for row in rows])


@operations_router.post(
    "/actions/{action_id}/approvals",
    response_model=ApprovalOut,
    status_code=201,
)
def create_approval(
    action_id: UUID,
    body: ApprovalCreate,
    service: ActionService = _actions,
) -> ApprovalOut:
    row = service.create_approval(action_id, status=body.status)
    return ApprovalOut.from_row(row)


@operations_router.get(
    "/actions/{action_id}/approvals/{approval_id}",
    response_model=ApprovalOut,
)
def read_approval(
    action_id: UUID,
    approval_id: UUID,
    service: ActionService = _actions,
) -> ApprovalOut:
    return ApprovalOut.from_row(service.get_approval(action_id, approval_id))
