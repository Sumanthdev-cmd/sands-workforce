# payroll md approval workflow
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "9ab4c6d8e0f2"
down_revision: Union[str, None] = "674f9337c02e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.alter_column(
        "payroll_runs", "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=40),
        existing_nullable=False,
    )
    for name, typ in [
        ("submitted_by_user_id", postgresql.UUID(as_uuid=True)),
        ("submitted_at", sa.DateTime(timezone=True)),
        ("submission_note", sa.Text()),
        ("approved_by_user_id", postgresql.UUID(as_uuid=True)),
        ("approved_at", sa.DateTime(timezone=True)),
        ("approval_note", sa.Text()),
        ("returned_by_user_id", postgresql.UUID(as_uuid=True)),
        ("returned_at", sa.DateTime(timezone=True)),
        ("return_note", sa.Text()),
    ]:
        op.add_column("payroll_runs", sa.Column(name, typ, nullable=True))
    op.create_foreign_key("fk_payroll_runs_submitted_by_user_id_users", "payroll_runs", "users", ["submitted_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_payroll_runs_approved_by_user_id_users", "payroll_runs", "users", ["approved_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_payroll_runs_returned_by_user_id_users", "payroll_runs", "users", ["returned_by_user_id"], ["id"], ondelete="SET NULL")

def downgrade() -> None:
    op.drop_constraint("fk_payroll_runs_returned_by_user_id_users", "payroll_runs", type_="foreignkey")
    op.drop_constraint("fk_payroll_runs_approved_by_user_id_users", "payroll_runs", type_="foreignkey")
    op.drop_constraint("fk_payroll_runs_submitted_by_user_id_users", "payroll_runs", type_="foreignkey")
    for name in ["return_note","returned_at","returned_by_user_id","approval_note","approved_at","approved_by_user_id","submission_note","submitted_at","submitted_by_user_id"]:
        op.drop_column("payroll_runs", name)
    op.alter_column(
        "payroll_runs", "status",
        existing_type=sa.String(length=40),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
