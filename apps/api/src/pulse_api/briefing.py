"""Deterministic selection for the daily briefing. No model score."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from pulse_api.models import AttentionItem, AttentionPriority

BRIEFING_CAP = 5
AGE_THRESHOLD = timedelta(days=2)
DUE_WINDOW = timedelta(days=1)

_PRIORITY = {
    AttentionPriority.HIGH.value: 0,
    AttentionPriority.MEDIUM.value: 1,
    AttentionPriority.LOW.value: 2,
}


def briefing_sort_key(item: AttentionItem, now: datetime) -> tuple[int, int, int, datetime, UUID]:
    """Due soon, then aged, then stored priority, then oldest."""
    created_at = _aware(item.created_at)
    moment = _aware(now)
    due_at = _aware(item.due_at) if item.due_at is not None else None
    due = due_at is not None and due_at <= moment + DUE_WINDOW
    aged = created_at <= moment - AGE_THRESHOLD
    return (
        0 if due else 1,
        0 if aged else 1,
        _PRIORITY.get(item.priority, 3),
        created_at,
        item.id,
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
