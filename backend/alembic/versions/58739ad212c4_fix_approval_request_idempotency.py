"""fix approval request idempotency

Revision ID: 58739ad212c4
Revises: 1e79c3a0698d
Create Date: 2026-08-28 19:00:07.449179

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '58739ad212c4'
down_revision: Union[str, Sequence[str], None] = '1e79c3a0698d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS
        uq_document_approval_pending_dedupe
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        uq_document_approval_submission_dedupe
        ON document_approval_requests (
            organization_id,
            dedupe_key
        )
        WHERE dedupe_key IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS
        uq_document_approval_submission_dedupe
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        uq_document_approval_pending_dedupe
        ON document_approval_requests (
            organization_id,
            dedupe_key
        )
        WHERE
            status = 'PENDING'
            AND dedupe_key IS NOT NULL
    """)
    
