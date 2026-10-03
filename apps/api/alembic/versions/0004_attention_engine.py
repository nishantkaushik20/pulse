"""Unique attention item per tenant, type, and source entity.

Revision ID: 0004_attention
Revises: 0003_gmail
Create Date: 2026-10-03

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_attention"
down_revision: str | None = "0003_gmail"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_attention_items_tenant_type_entity",
        "attention_items",
        ["tenant_id", "type", "entity_type", "entity_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_attention_items_tenant_type_entity", table_name="attention_items")
