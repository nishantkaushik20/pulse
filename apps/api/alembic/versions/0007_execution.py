"""Action lifecycle, idempotency, and audit logs.

Revision ID: 0007_execution
Revises: 0006_ai
Create Date: 2026-10-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_execution"
down_revision: str | None = "0006_ai"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_STATUSES = (
    "status IN ('PROPOSED', 'PENDING_APPROVAL', 'APPROVED', 'EXECUTING', "
    "'COMPLETED', 'FAILED', 'CANCELLED', 'EXPIRED')"
)


def upgrade() -> None:
    op.execute("UPDATE actions SET status = 'PROPOSED' WHERE status = 'PENDING'")
    op.drop_constraint("ck_actions_status", "actions", type_="check")
    op.alter_column("actions", "status", type_=sa.String(length=32), existing_nullable=False)
    op.create_check_constraint("ck_actions_status", "actions", _STATUSES)
    op.add_column("actions", sa.Column("idempotency_key", sa.String(length=100)))
    op.create_index(
        "uq_actions_tenant_idempotency_key",
        "actions",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "tenant_id",
            _UUID,
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            _UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", _UUID, nullable=False),
        sa.Column("result_code", sa.String(32), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_audit_logs_tenant_id_created_at",
        "audit_logs",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_tenant_id_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("uq_actions_tenant_idempotency_key", table_name="actions")
    op.drop_column("actions", "idempotency_key")
    op.drop_constraint("ck_actions_status", "actions", type_="check")
    op.execute(
        "UPDATE actions SET status = 'PENDING' "
        "WHERE status NOT IN ('PENDING', 'COMPLETED', 'CANCELLED')"
    )
    op.alter_column("actions", "status", type_=sa.String(length=16), existing_nullable=False)
    op.create_check_constraint(
        "ck_actions_status",
        "actions",
        "status IN ('PENDING', 'COMPLETED', 'CANCELLED')",
    )
