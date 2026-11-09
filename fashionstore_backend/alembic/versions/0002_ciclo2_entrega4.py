"""Ciclo 2 Entrega 4 — auditoria de preparacion/atencion y descuento de adelanto.

Agrega a comercial.reservas: preparada_en, atendida_en, preparada_por,
atendida_por (CU10: responsable y marcas temporales).
Agrega a comercial.ventas: adelanto_descontado (CU11: aplicado una sola vez).
Re-ejecutable (guardas IF NOT EXISTS).
"""
from alembic import op

revision = "0002_ciclo2_entrega4"
down_revision = "0001_ciclo2_entrega1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS preparada_en timestamptz")
    op.execute("ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS atendida_en timestamptz")
    op.execute("ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS preparada_por uuid REFERENCES seguridad.usuarios(id)")
    op.execute("ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS atendida_por uuid REFERENCES seguridad.usuarios(id)")
    op.execute("ALTER TABLE comercial.ventas ADD COLUMN IF NOT EXISTS adelanto_descontado numeric(12,2) NOT NULL DEFAULT 0")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ventas_adelanto_desc_nneg') THEN
                ALTER TABLE comercial.ventas ADD CONSTRAINT ck_ventas_adelanto_desc_nneg CHECK (adelanto_descontado >= 0);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE comercial.ventas DROP CONSTRAINT IF EXISTS ck_ventas_adelanto_desc_nneg")
    op.execute("ALTER TABLE comercial.ventas DROP COLUMN IF EXISTS adelanto_descontado")
    op.execute("ALTER TABLE comercial.reservas DROP COLUMN IF EXISTS atendida_por")
    op.execute("ALTER TABLE comercial.reservas DROP COLUMN IF EXISTS preparada_por")
    op.execute("ALTER TABLE comercial.reservas DROP COLUMN IF EXISTS atendida_en")
    op.execute("ALTER TABLE comercial.reservas DROP COLUMN IF EXISTS preparada_en")
