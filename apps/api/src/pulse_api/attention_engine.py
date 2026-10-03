"""Deterministic attention rules.

Business events enter here. Gmail persistence does not. The only Phase 4 rule
creates an OPEN, MEDIUM review item for EMAIL_RECEIVED. It does not decide that
a reply is owed: sent mail and customer matching are not available yet.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from pulse_api.context import TenantContext
from pulse_api.gmail.repository import MessageRepository
from pulse_api.models import AttentionPriority, BusinessEvent, Message
from pulse_api.repositories import AttentionRepository

EMAIL_REVIEW_TYPE = "email_review"
EMAIL_REVIEW_TITLE = "New email needs review"


@dataclass(frozen=True)
class AttentionDecision:
    item_type: str
    priority: str
    title: str
    description: str | None
    entity_type: str
    entity_id: UUID


class AttentionEngine:
    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self._tenant = tenant
        self._messages = MessageRepository(session, tenant.tenant_id)
        self._items = AttentionRepository(session, tenant.tenant_id)

    def evaluate(self, event: BusinessEvent) -> list[AttentionDecision]:
        if event.tenant_id != self._tenant.tenant_id:
            return []
        if event.event_type != "EMAIL_RECEIVED" or event.entity_type != "message":
            return []
        message = self._messages.get(event.entity_id)
        if message is None:
            return []
        return [
            AttentionDecision(
                item_type=EMAIL_REVIEW_TYPE,
                priority=AttentionPriority.MEDIUM,
                title=EMAIL_REVIEW_TITLE,
                description=_description(message),
                entity_type="message",
                entity_id=message.id,
            )
        ]

    def apply(self, event: BusinessEvent) -> list[UUID]:
        created: list[UUID] = []
        for decision in self.evaluate(event):
            item_id = self._items.insert_idempotent(
                item_type=decision.item_type,
                priority=decision.priority,
                title=decision.title,
                description=decision.description,
                entity_type=decision.entity_type,
                entity_id=decision.entity_id,
            )
            if item_id is not None:
                created.append(item_id)
        return created


def _description(message: Message) -> str | None:
    lines: list[str] = []
    sender = message.from_email or ""
    if message.from_name and sender:
        sender = f"{message.from_name} <{sender}>"
    if sender:
        lines.append(f"From: {sender}")
    subject = message.subject.strip()
    if subject:
        lines.append(f"Subject: {subject[:500]}")
    if not lines:
        return None
    return "\n".join(lines)
