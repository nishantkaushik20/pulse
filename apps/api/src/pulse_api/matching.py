"""Deterministic customer matching. This module never writes customer rows."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_api.models import Contact, Customer

EXACT_EMAIL = "exact_email"


def exact_email_customer(
    session: Session,
    tenant_id: UUID,
    email: str | None,
) -> tuple[UUID | None, str | None]:
    """Return a customer id when the address matches a contact or customer email.

    Contact rows win over the customer record. The comparison is the stored
    lowercase address. No row is inserted or updated.
    """
    normalized = _normalize(email)
    if normalized is None:
        return None, None
    contact_customer_id = session.scalar(
        select(Contact.customer_id)
        .where(Contact.tenant_id == tenant_id, Contact.email == normalized)
        .order_by(Contact.created_at.asc(), Contact.id.asc())
        .limit(1)
    )
    if contact_customer_id is not None:
        return contact_customer_id, EXACT_EMAIL
    customer_id = session.scalar(
        select(Customer.id)
        .where(Customer.tenant_id == tenant_id, Customer.email == normalized)
        .order_by(Customer.created_at.asc(), Customer.id.asc())
        .limit(1)
    )
    if customer_id is None:
        return None, None
    return customer_id, EXACT_EMAIL


def customer_name(session: Session, tenant_id: UUID, customer_id: UUID | None) -> str | None:
    if customer_id is None:
        return None
    return session.scalar(
        select(Customer.name).where(Customer.tenant_id == tenant_id, Customer.id == customer_id)
    )


def _normalize(email: str | None) -> str | None:
    if email is None:
        return None
    cleaned = email.strip().lower()
    return cleaned or None
