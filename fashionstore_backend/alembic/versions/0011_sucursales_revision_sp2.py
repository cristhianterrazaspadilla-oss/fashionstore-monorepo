"""Organizacion: revision en sucursales para control optimista (CU15).

Revision ID: 0011_sucursales_revision_sp2
Revises: 0010_identidad_revision_sp2
"""
from alembic import op

revision = "0011_sucursales_revision_sp2"
down_revision = "0010_identidad_revision_sp2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. organizacion.sucursales: revision
    op.execute("""
        ALTER TABLE organizacion.sucursales
        ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_sucursales_revision'
            ) THEN
                ALTER TABLE organizacion.sucursales
                ADD CONSTRAINT ck_sucursales_revision CHECK (revision >= 1);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    raise RuntimeError(
        "0011 modifica esquema de sucursales con datos en operacion; "
        "restaurar respaldo verificado para revertir."
    )
