"""Attention resolution metadata and derived email matches.

Revision ID: 0005_context
Revises: 0004_attention
Create Date: 2026-10-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_context"
down_revision: str | None = "0004_attention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("attention_items", sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.add_column("attention_items", sa.Column("resolved_by", _UUID))
    op.add_column("attention_items", sa.Column("dismiss_reason", sa.String(length=32)))
    op.add_column("attention_items", sa.Column("matched_customer_id", _UUID))
    op.add_column("attention_items", sa.Column("match_method", sa.String(length=32)))
    op.create_foreign_key(
        "fk_attention_items_resolved_by_users",
        "attention_items",
        "users",
        ["resolved_by"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_attention_items_matched_customer_id_customers",
        "attention_items",
        "customers",
        ["matched_customer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_attention_items_dismiss_reason",
        "attention_items",
        "dismiss_reason IS NULL OR dismiss_reason IN ('not_relevant', 'done', 'waiting')",
    )
    op.create_check_constraint(
        "ck_attention_items_match_method",
        "attention_items",
        "match_method IS NULL OR match_method IN ('exact_email')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_attention_items_match_method", "attention_items", type_="check")
    op.drop_constraint("ck_attention_items_dismiss_reason", "attention_items", type_="check")
    op.drop_constraint(
        "fk_attention_items_matched_customer_id_customers",
        "attention_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_attention_items_resolved_by_users",
        "attention_items",
        type_="foreignkey",
    )
    op.drop_column("attention_items", "match_method")
    op.drop_column("attention_items", "matched_customer_id")
    op.drop_column("attention_items", "dismiss_reason")
    op.drop_column("attention_items", "resolved_by")
    op.drop_column("attention_items", "resolved_at")
