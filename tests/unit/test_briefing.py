"""Briefing order is due, then age, then stored priority."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pulse_api.briefing import BRIEFING_CAP, briefing_sort_key
from pulse_api.models import AttentionItem, AttentionPriority, AttentionStatus


def test_due_and_aged_items_sort_ahead_of_fresh_mail() -> None:
    now = datetime(2026, 10, 4, tzinfo=UTC)
    fresh = _item("fresh", AttentionPriority.HIGH, now - timedelta(hours=1))
    aged = _item("aged", AttentionPriority.LOW, now - timedelta(days=3))
    due = _item("due", AttentionPriority.LOW, now - timedelta(hours=2), due_at=now)
    ordered = sorted([fresh, aged, due], key=lambda item: briefing_sort_key(item, now))
    assert [item.title for item in ordered] == ["due", "aged", "fresh"]
    assert BRIEFING_CAP == 5


def _item(
    title: str,
    priority: str,
    created_at: datetime,
    due_at: datetime | None = None,
) -> AttentionItem:
    return AttentionItem(
        id=uuid4(),
        tenant_id=uuid4(),
        item_type="email_review",
        priority=priority,
        title=title,
        status=AttentionStatus.OPEN,
        created_at=created_at,
        updated_at=created_at,
        due_at=due_at,
    )
