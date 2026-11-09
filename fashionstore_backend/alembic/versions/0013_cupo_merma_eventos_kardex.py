"""Cupos de caja: merma auditada y eventos de supervisiÃ³n.

Revision ID: 0013_cupo_merma_eventos_kardex
Revises: 0012_cierre_turno_supervision
"""
from alembic import op

revision = "0013_cupo_merma_eventos_kardex"
down_revision = "0012_cierre_turno_supervision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE inventario.cupos_caja ADD COLUMN IF NOT EXISTS mermado integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE inventario.cupos_caja ADD COLUMN IF NOT EXISTS costo_unitario_snapshot numeric(12, 2)")
    op.execute("""
        UPDATE inventario.cupos_caja AS c
        SET costo_unitario_snapshot = COALESCE(v.costo_promedio, 0)
        FROM catalogo.variantes_producto AS v
        WHERE v.id = c.variante_id AND c.costo_unitario_snapshot IS NULL
    """)
    op.execute("ALTER TABLE inventario.cupos_caja ALTER COLUMN costo_unitario_snapshot SET DEFAULT 0")
    op.execute("ALTER TABLE inventario.cupos_caja ALTER COLUMN costo_unitario_snapshot SET NOT NULL")
    op.execute("ALTER TABLE inventario.cupos_caja ADD CONSTRAINT ck_cupos_caja_mermado_nneg CHECK (mermado >= 0)")
    op.execute("ALTER TABLE inventario.cupos_caja ADD CONSTRAINT ck_cupos_caja_costo_snapshot_nneg CHECK (costo_unitario_snapshot >= 0)")
    op.execute("ALTER TABLE inventario.cupos_caja ADD CONSTRAINT ck_cupos_caja_cantidades_cupo CHECK (consumido + liberado + mermado <= otorgado)")
    op.execute("ALTER TABLE inventario.movimientos_inventario DROP CONSTRAINT IF EXISTS movimientos_inventario_tipo_check")
    op.execute("""
        ALTER TABLE inventario.movimientos_inventario
        ADD CONSTRAINT movimientos_inventario_tipo_check CHECK (
            tipo IN (
                'RECEPCION_PROVEEDOR','RESERVA','LIBERACION_RESERVA',
                'COMPROMISO_TRASLADO','DESPACHO_TRASLADO','RECEPCION_TRASLADO',
                'VENTA_PRESENCIAL','VENTA_DIGITAL','DEVOLUCION','MERMA','AJUSTE',
                'COMPROMISO_DIGITAL','LIBERACION_DIGITAL','COMPROMISO_CAJA',
                'LIBERACION_CUPO_CAJA'
            )
        )
    """)
    op.execute("""
        CREATE TABLE comercial.turnos_caja_eventos (
            id uuid PRIMARY KEY,
            turno_id uuid NOT NULL REFERENCES comercial.turnos_caja(id),
            empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
            actor_id uuid NOT NULL REFERENCES seguridad.usuarios(id),
            revision integer NOT NULL,
            tipo varchar(40) NOT NULL,
            datos jsonb NOT NULL DEFAULT '{}'::jsonb,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_turnos_caja_eventos_turno_revision UNIQUE (turno_id, revision)
        );
    """)
    op.execute("CREATE INDEX ix_turnos_caja_eventos_turno_id ON comercial.turnos_caja_eventos(turno_id)")
    op.execute("CREATE INDEX ix_turnos_caja_eventos_empresa_id ON comercial.turnos_caja_eventos(empresa_id)")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM inventario.movimientos_inventario
                WHERE tipo IN ('COMPROMISO_CAJA','LIBERACION_CUPO_CAJA')
            ) THEN
                RAISE EXCEPTION
                    'No se puede revertir 0013: existen movimientos de cupos de caja en el Kardex';
            END IF;
        END $$
    """)
    op.execute("ALTER TABLE inventario.movimientos_inventario DROP CONSTRAINT IF EXISTS movimientos_inventario_tipo_check")
    op.execute("""
        ALTER TABLE inventario.movimientos_inventario
        ADD CONSTRAINT movimientos_inventario_tipo_check CHECK (
            tipo IN (
                'RECEPCION_PROVEEDOR','RESERVA','LIBERACION_RESERVA',
                'COMPROMISO_TRASLADO','DESPACHO_TRASLADO','RECEPCION_TRASLADO',
                'VENTA_PRESENCIAL','VENTA_DIGITAL','DEVOLUCION','MERMA','AJUSTE',
                'COMPROMISO_DIGITAL','LIBERACION_DIGITAL'
            )
        )
    """)
    op.execute("DROP TABLE IF EXISTS comercial.turnos_caja_eventos")
    op.execute("ALTER TABLE inventario.cupos_caja DROP CONSTRAINT IF EXISTS ck_cupos_caja_cantidades_cupo")
    op.execute("ALTER TABLE inventario.cupos_caja DROP CONSTRAINT IF EXISTS ck_cupos_caja_costo_snapshot_nneg")
    op.execute("ALTER TABLE inventario.cupos_caja DROP COLUMN IF EXISTS costo_unitario_snapshot")
    op.execute("ALTER TABLE inventario.cupos_caja DROP CONSTRAINT IF EXISTS ck_cupos_caja_mermado_nneg")
    op.execute("ALTER TABLE inventario.cupos_caja DROP COLUMN IF EXISTS mermado")
