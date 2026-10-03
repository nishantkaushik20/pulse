"""Gmail connections and ingested messages.

Revision ID: 0003_gmail
Revises: 0002_domain
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_gmail"
down_revision: str | None = "0002_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_JSON = postgresql.JSONB(astext_type=sa.Text())
_NOW = sa.text("now()")
_GEN = sa.text("gen_random_uuid()")
_EMPTY_LIST = sa.text("'[]'::jsonb")


def _id() -> sa.Column[object]:
    return sa.Column("id", _UUID, primary_key=True, server_default=_GEN, nullable=False)


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
        "gmail_connections",
        _id(),
        _tenant_fk(),
        sa.Column(
            "connected_by",
            _UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_account_id", sa.String(320), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("encrypted_refresh_token", sa.LargeBinary(), nullable=True),
        sa.Column("encrypted_access_token", sa.LargeBinary(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encryption_key_version", sa.Integer(), nullable=False),
        sa.Column("history_id", sa.String(64), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("scopes", sa.String(500), nullable=False),
        _created(),
        _updated(),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED', 'ERROR')",
            name="ck_gmail_connections_status",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "external_account_id",
            name="uq_gmail_connections_tenant_external",
        ),
        sa.UniqueConstraint(
            "external_account_id",
            name="uq_gmail_connections_external_account_id",
        ),
    )
    op.create_index("ix_gmail_connections_tenant_id", "gmail_connections", ["tenant_id"])

    op.create_table(
        "message_threads",
        _id(),
        _tenant_fk(),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_thread_id", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        _created(),
        _updated(),
        sa.CheckConstraint("source IN ('gmail')", name="ck_message_threads_source"),
        sa.UniqueConstraint(
            "tenant_id",
            "source",
            "external_thread_id",
            name="uq_message_threads_tenant_source_external",
        ),
    )
    op.create_index("ix_message_threads_tenant_id", "message_threads", ["tenant_id"])

    op.create_table(
        "messages",
        _id(),
        _tenant_fk(),
        sa.Column(
            "thread_id",
            _UUID,
            sa.ForeignKey("message_threads.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_message_id", sa.String(255), nullable=False),
        sa.Column("from_email", sa.String(320), nullable=True),
        sa.Column("from_name", sa.String(200), nullable=True),
        sa.Column("to_addresses", _JSON, server_default=_EMPTY_LIST, nullable=False),
        sa.Column("cc_addresses", _JSON, server_default=_EMPTY_LIST, nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("snippet", sa.String(1000), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        _created(),
        sa.CheckConstraint("source IN ('gmail')", name="ck_messages_source"),
        sa.UniqueConstraint(
            "tenant_id",
            "source",
            "external_message_id",
            name="uq_messages_tenant_source_external",
        ),
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    op.create_index("ix_messages_tenant_thread", "messages", ["tenant_id", "thread_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_tenant_thread", table_name="messages")
    op.drop_index("ix_messages_tenant_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_message_threads_tenant_id", table_name="message_threads")
    op.drop_table("message_threads")
    op.drop_index("ix_gmail_connections_tenant_id", table_name="gmail_connections")
    op.drop_table("gmail_connections")
