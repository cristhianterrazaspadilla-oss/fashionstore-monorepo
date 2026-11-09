-- Migracion 0011_sucursales_revision_sp2: revision en sucursales para control optimista (CU15)
-- Aplica sobre 0010_identidad_revision_sp2 sin perdida de datos

BEGIN;

ALTER TABLE organizacion.sucursales
ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1;

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

UPDATE alembic_version
SET version_num = '0011_sucursales_revision_sp2';

COMMIT;
