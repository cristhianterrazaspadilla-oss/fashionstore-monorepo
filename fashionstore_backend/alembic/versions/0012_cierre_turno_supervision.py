"""Ventas y Pagos: trazabilidad durable de cierre y supervisión de turnos de caja (CU06, CU07).

Revision ID: 0012_cierre_turno_supervision
Revises: 0011_sucursales_revision_sp2
"""
from alembic import op

revision = "0012_cierre_turno_supervision"
down_revision = "0011_sucursales_revision_sp2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE comercial.turnos_caja
        ADD COLUMN IF NOT EXISTS cerrado_por_id uuid REFERENCES seguridad.usuarios(id),
        ADD COLUMN IF NOT EXISTS motivo_supervision text,
        ADD COLUMN IF NOT EXISTS supervision_forzada boolean NOT NULL DEFAULT false,
        ADD COLUMN IF NOT EXISTS arqueo_declarado_bob numeric(14, 2),
        ADD COLUMN IF NOT EXISTS evidencia_cierre jsonb,
        ADD COLUMN IF NOT EXISTS ajustes_inventario jsonb;
    """)


def downgrade() -> None:
    raise RuntimeError(
        "0012 contiene trazabilidad de supervisión y cierres de turno de caja; "
        "restaurar respaldo verificado para revertir."
    )
