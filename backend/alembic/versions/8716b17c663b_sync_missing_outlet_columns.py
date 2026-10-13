"""sync missing outlet columns

Revision ID: 8716b17c663b
Revises: beff03226eef
Create Date: 2026-08-27 11:59:44.628434

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8716b17c663b'
down_revision: Union[str, Sequence[str], None] = 'beff03226eef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE outlets
        ADD COLUMN IF NOT EXISTS cluster_name VARCHAR(180)
    """)

    op.execute("""
        ALTER TABLE outlets
        ADD COLUMN IF NOT EXISTS latitude NUMERIC(10,7)
    """)

    op.execute("""
        ALTER TABLE outlets
        ADD COLUMN IF NOT EXISTS longitude NUMERIC(10,7)
    """)

    op.execute("""
        ALTER TABLE outlets
        ADD COLUMN IF NOT EXISTS vendor_id UUID
    """)

    op.execute("""
        ALTER TABLE outlets
        ADD COLUMN IF NOT EXISTS vendor_contact_person VARCHAR(180)
    """)

    op.execute("""
        ALTER TABLE outlets
        ADD COLUMN IF NOT EXISTS opening_date DATE
    """)

    op.execute("""
        ALTER TABLE outlets
        ADD COLUMN IF NOT EXISTS excise_licence_number VARCHAR(120)
    """)

    op.execute("""
        ALTER TABLE outlets
        ADD COLUMN IF NOT EXISTS excise_expiry_date DATE
    """)

    op.execute("""
        ALTER TABLE outlets
        ADD COLUMN IF NOT EXISTS rent_agreement_expiry_date DATE
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_outlets_vendor_id_vendors'
            ) THEN
                ALTER TABLE outlets
                ADD CONSTRAINT fk_outlets_vendor_id_vendors
                FOREIGN KEY (vendor_id)
                REFERENCES vendors(id)
                ON DELETE SET NULL;
            END IF;
        END
        $$;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_outlets_cluster_name
        ON outlets (cluster_name)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_outlets_vendor_id
        ON outlets (vendor_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_outlets_excise_expiry_date
        ON outlets (excise_expiry_date)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_outlets_rent_agreement_expiry_date
        ON outlets (rent_agreement_expiry_date)
    """)


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_outlets_rent_agreement_expiry_date"
    )

    op.execute(
        "DROP INDEX IF EXISTS ix_outlets_excise_expiry_date"
    )

    op.execute(
        "DROP INDEX IF EXISTS ix_outlets_vendor_id"
    )

    op.execute(
        "DROP INDEX IF EXISTS ix_outlets_cluster_name"
    )

    op.execute("""
        ALTER TABLE outlets
        DROP CONSTRAINT IF EXISTS fk_outlets_vendor_id_vendors
    """)

    op.execute(
        "ALTER TABLE outlets DROP COLUMN IF EXISTS rent_agreement_expiry_date"
    )

    op.execute(
        "ALTER TABLE outlets DROP COLUMN IF EXISTS excise_expiry_date"
    )

    op.execute(
        "ALTER TABLE outlets DROP COLUMN IF EXISTS excise_licence_number"
    )

    op.execute(
        "ALTER TABLE outlets DROP COLUMN IF EXISTS opening_date"
    )

    op.execute(
        "ALTER TABLE outlets DROP COLUMN IF EXISTS vendor_contact_person"
    )

    op.execute(
        "ALTER TABLE outlets DROP COLUMN IF EXISTS vendor_id"
    )

    op.execute(
        "ALTER TABLE outlets DROP COLUMN IF EXISTS longitude"
    )

    op.execute(
        "ALTER TABLE outlets DROP COLUMN IF EXISTS latitude"
    )

    op.execute(
        "ALTER TABLE outlets DROP COLUMN IF EXISTS cluster_name"
    )