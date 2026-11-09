"""Identidad: persistencia razon_social, nombre_comercial y revision en usuarios (CU01, CU14).

Revision ID: 0010_identidad_revision_sp2
Revises: 0009_modelo_final_66
"""
from alembic import op

revision = "0010_identidad_revision_sp2"
down_revision = "0009_modelo_final_66"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. organizacion.empresas: razon_social y nombre_comercial
    op.execute("""
        ALTER TABLE organizacion.empresas
        ADD COLUMN IF NOT EXISTS razon_social varchar(200),
        ADD COLUMN IF NOT EXISTS nombre_comercial varchar(180);
    """)
    op.execute("""
        UPDATE organizacion.empresas
        SET razon_social = COALESCE(NULLIF(razon_social, ''), nombre),
            nombre_comercial = COALESCE(NULLIF(nombre_comercial, ''), nombre)
        WHERE razon_social IS NULL OR nombre_comercial IS NULL;
    """)
    op.execute("""
        ALTER TABLE organizacion.empresas
        ALTER COLUMN razon_social SET NOT NULL,
        ALTER COLUMN nombre_comercial SET NOT NULL;
    """)

    # 2. seguridad.usuarios: revision
    op.execute("""
        ALTER TABLE seguridad.usuarios
        ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_usuarios_revision'
            ) THEN
                ALTER TABLE seguridad.usuarios
                ADD CONSTRAINT ck_usuarios_revision CHECK (revision >= 1);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    raise RuntimeError(
        "0010 modifica esquema de identidad con empresas y usuarios en operacion; "
        "restaurar respaldo verificado para revertir."
    )
