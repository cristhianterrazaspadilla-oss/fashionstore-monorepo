-- Migracion 0012_cierre_turno_supervision: trazabilidad durable de cierre y supervisión de turnos de caja (CU06, CU07)
-- Aplica sobre 0011_sucursales_revision_sp2 sin perdida de datos

BEGIN;

ALTER TABLE comercial.turnos_caja
    ADD COLUMN IF NOT EXISTS cerrado_por_id uuid REFERENCES seguridad.usuarios(id),
    ADD COLUMN IF NOT EXISTS motivo_supervision text,
    ADD COLUMN IF NOT EXISTS supervision_forzada boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS arqueo_declarado_bob numeric(14, 2),
    ADD COLUMN IF NOT EXISTS evidencia_cierre jsonb,
    ADD COLUMN IF NOT EXISTS ajustes_inventario jsonb;

UPDATE alembic_version
SET version_num = '0012_cierre_turno_supervision';

COMMIT;
