"""upgrade approval requests optional attachments

Revision ID: 1e79c3a0698d
Revises: 8716b17c663b
Create Date: 2026-08-28 18:33:04.488125

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e79c3a0698d'
down_revision: Union[str, Sequence[str], None] = '8716b17c663b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Supporting document/image is optional.
    op.execute("""
        ALTER TABLE document_approval_requests
        ALTER COLUMN document_id DROP NOT NULL
    """)

    # Fingerprint used to prevent duplicate requests.
    op.execute("""
        ALTER TABLE document_approval_requests
        ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(64)
    """)

    # Remove the old document foreign key.
    op.execute("""
        DO $$
        DECLARE
            fk_name text;
        BEGIN
            SELECT tc.constraint_name
            INTO fk_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.table_name = 'document_approval_requests'
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = 'document_id'
            LIMIT 1;

            IF fk_name IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TABLE document_approval_requests DROP CONSTRAINT %I',
                    fk_name
                );
            END IF;
        END
        $$;
    """)

    # Re-create document FK using SET NULL.
    op.execute("""
        ALTER TABLE document_approval_requests
        ADD CONSTRAINT fk_document_approval_requests_document_id
        FOREIGN KEY (document_id)
        REFERENCES document_records(id)
        ON DELETE SET NULL
    """)

    # Normal lookup index.
    op.execute("""
        CREATE INDEX IF NOT EXISTS
        ix_document_approval_requests_dedupe_key
        ON document_approval_requests (dedupe_key)
    """)

    # Database-level duplicate protection.
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


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS
        uq_document_approval_pending_dedupe
    """)

    op.execute("""
        DROP INDEX IF EXISTS
        ix_document_approval_requests_dedupe_key
    """)

    op.execute("""
        ALTER TABLE document_approval_requests
        DROP CONSTRAINT IF EXISTS
        fk_document_approval_requests_document_id
    """)

    op.execute("""
        ALTER TABLE document_approval_requests
        ADD CONSTRAINT document_approval_requests_document_id_fkey
        FOREIGN KEY (document_id)
        REFERENCES document_records(id)
        ON DELETE CASCADE
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM document_approval_requests
                WHERE document_id IS NULL
            ) THEN
                ALTER TABLE document_approval_requests
                ALTER COLUMN document_id SET NOT NULL;
            END IF;
        END
        $$;
    """)

    op.execute("""
        ALTER TABLE document_approval_requests
        DROP COLUMN IF EXISTS dedupe_key
    """)
