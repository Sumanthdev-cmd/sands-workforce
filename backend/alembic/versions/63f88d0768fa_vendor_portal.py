"""separate vendor portal accounts, sessions and notifications

Revision ID: 63f88d0768fa
Revises: de40e219f852
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "63f88d0768fa"
down_revision: Union[str, Sequence[str], None] = 'de40e219f852'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendor_portal_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("force_password_change", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_vendor_portal_account_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_vendor_portal_accounts"),
        sa.UniqueConstraint("organization_id", "vendor_id", name="uq_vendor_portal_org_vendor"),
    )
    op.create_index("ix_vendor_portal_accounts_org_status", "vendor_portal_accounts", ["organization_id", "status"])
    op.create_index("ix_vendor_portal_accounts_vendor", "vendor_portal_accounts", ["vendor_id"])

    op.create_table(
        "vendor_portal_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(length=100), nullable=True),
        sa.Column("user_agent", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["vendor_portal_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_vendor_portal_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_vendor_portal_session_token_hash"),
    )
    op.create_index("ix_vendor_portal_sessions_account", "vendor_portal_sessions", ["account_id"])
    op.create_index("ix_vendor_portal_sessions_expires", "vendor_portal_sessions", ["expires_at"])

    op.create_table(
        "vendor_portal_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dedupe_key", sa.String(length=500), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["vendor_portal_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_vendor_portal_notifications"),
        sa.UniqueConstraint("dedupe_key", name="uq_vendor_portal_notification_dedupe"),
    )
    op.create_index("ix_vendor_portal_notifications_account_read", "vendor_portal_notifications", ["account_id", "read_at"])
    op.create_index("ix_vendor_portal_notifications_org", "vendor_portal_notifications", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_vendor_portal_notifications_org", table_name="vendor_portal_notifications")
    op.drop_index("ix_vendor_portal_notifications_account_read", table_name="vendor_portal_notifications")
    op.drop_table("vendor_portal_notifications")
    op.drop_index("ix_vendor_portal_sessions_expires", table_name="vendor_portal_sessions")
    op.drop_index("ix_vendor_portal_sessions_account", table_name="vendor_portal_sessions")
    op.drop_table("vendor_portal_sessions")
    op.drop_index("ix_vendor_portal_accounts_vendor", table_name="vendor_portal_accounts")
    op.drop_index("ix_vendor_portal_accounts_org_status", table_name="vendor_portal_accounts")
    op.drop_table("vendor_portal_accounts")
