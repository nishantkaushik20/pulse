"""Identity and tenant-owned domain tables.

Revision ID: 0002_domain
Revises: 0001_baseline
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_domain"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_JSON = postgresql.JSONB(astext_type=sa.Text())
_NOW = sa.text("now()")
_GEN = sa.text("gen_random_uuid()")


def _id() -> sa.Column[object]:
    return sa.Column(
        "id",
        _UUID,
        primary_key=True,
        server_default=_GEN,
        nullable=False,
    )


def _created() -> sa.Column[object]:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False)


def _updated() -> sa.Column[object]:
    return sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False)


def _tenant_fk() -> sa.Column[object]:
    return sa.Column(
        "tenant_id",
        _UUID,
        sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "users",
        _id(),
        sa.Column("clerk_user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        _created(),
        _updated(),
        sa.UniqueConstraint("clerk_user_id", name="uq_users_clerk_user_id"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "tenants",
        _id(),
        sa.Column("name", sa.String(200), nullable=False),
        _created(),
        _updated(),
    )

    op.create_table(
        "tenant_users",
        _id(),
        _tenant_fk(),
        sa.Column(
            "user_id",
            _UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        _created(),
        sa.CheckConstraint("role IN ('OWNER', 'MEMBER')", name="ck_tenant_users_role"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_users_tenant_id_user_id"),
    )
    op.create_index("ix_tenant_users_user_id", "tenant_users", ["user_id"])

    op.create_table(
        "customers",
        _id(),
        _tenant_fk(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        _created(),
        _updated(),
        sa.CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="ck_customers_status"),
    )
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])
    op.create_index("ix_customers_tenant_id_email", "customers", ["tenant_id", "email"])

    op.create_table(
        "contacts",
        _id(),
        _tenant_fk(),
        sa.Column(
            "customer_id",
            _UUID,
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        _created(),
        _updated(),
    )
    op.create_index("ix_contacts_tenant_id", "contacts", ["tenant_id"])
    op.create_index(
        "ix_contacts_tenant_id_customer_id",
        "contacts",
        ["tenant_id", "customer_id"],
    )

    op.create_table(
        "business_events",
        _id(),
        _tenant_fk(),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", _UUID, nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", _JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        _created(),
    )
    op.create_index(
        "ix_business_events_tenant_id_occurred_at",
        "business_events",
        ["tenant_id", "occurred_at"],
    )

    op.create_table(
        "attention_items",
        _id(),
        _tenant_fk(),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", _UUID, nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        _updated(),
        sa.CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_attention_items_status"),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH')",
            name="ck_attention_items_priority",
        ),
    )
    op.create_index(
        "ix_attention_items_tenant_id_status",
        "attention_items",
        ["tenant_id", "status"],
    )

    op.create_table(
        "actions",
        _id(),
        _tenant_fk(),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "requested_by",
            _UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", _UUID, nullable=True),
        sa.Column("input", _JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result", _JSON, nullable=True),
        _created(),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'COMPLETED', 'CANCELLED')",
            name="ck_actions_status",
        ),
    )
    op.create_index("ix_actions_tenant_id_status", "actions", ["tenant_id", "status"])

    op.create_table(
        "action_approvals",
        _id(),
        _tenant_fk(),
        sa.Column(
            "action_id",
            _UUID,
            sa.ForeignKey("actions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approved_by",
            _UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        sa.CheckConstraint(
            "status IN ('APPROVED', 'REJECTED')",
            name="ck_action_approvals_status",
        ),
    )
    op.create_index("ix_action_approvals_tenant_id", "action_approvals", ["tenant_id"])
    op.create_index("ix_action_approvals_action_id", "action_approvals", ["action_id"])


def downgrade() -> None:
    op.drop_table("action_approvals")
    op.drop_table("actions")
    op.drop_table("attention_items")
    op.drop_table("business_events")
    op.drop_table("contacts")
    op.drop_table("customers")
    op.drop_table("tenant_users")
    op.drop_table("tenants")
    op.drop_table("users")
