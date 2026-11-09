"""Pago: restriccion unica de referencia externa por empresa y proveedor.

Garantiza el uso unico del cargo financiero en comercial.pagos ante concurrencia
de liquidaciones en caja (CU19/CU22).

Revision ID: 0014_pago_ref_externa_unique
Revises: 0013_cupo_merma_eventos_kardex
"""
from alembic import op

revision = "0014_pago_ref_externa_unique"
down_revision = "0013_cupo_merma_eventos_kardex"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_pagos_empresa_prov_ref
        ON comercial.pagos (empresa_id, proveedor_pago, referencia_externa)
        WHERE referencia_externa IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS comercial.uq_pagos_empresa_prov_ref;")
