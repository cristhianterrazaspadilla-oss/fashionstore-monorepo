/*
Parche para instalaciones donde 04_esquema_ciclo3.sql ya fue aplicado antes
de la normalizacion. No elimina pedidos ni altera sus valores.
*/
BEGIN;

DO $compat_tipo_estado_pedido$
BEGIN
  IF to_regclass('comercial.pedidos_entrega') IS NULL THEN
    RAISE EXCEPTION 'No existe comercial.pedidos_entrega; ejecute primero 04_esquema_ciclo3.sql';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_attribute a
    JOIN pg_type t ON t.oid=a.atttypid
    WHERE a.attrelid='comercial.pedidos_entrega'::regclass
      AND a.attname='estado' AND a.attnum>0 AND NOT a.attisdropped
      AND t.typtype='e'
  ) THEN
    ALTER TABLE comercial.pedidos_entrega
      ALTER COLUMN estado TYPE varchar(20) USING estado::text;
  END IF;
END
$compat_tipo_estado_pedido$;

-- Retira exclusivamente CHECKs del DDL preliminar que usan las columnas
-- tipo_entrega/sucursal_recojo_id/direccion_referencia. Esas columnas fueron
-- sustituidas por modalidad/sucursal_id/direccion en el contrato definitivo.
DO $compat_checks_legacy$
DECLARE c record;
BEGIN
  FOR c IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid='comercial.pedidos_entrega'::regclass
      AND contype='c'
      AND (
        pg_get_constraintdef(oid) ILIKE '%tipo_entrega%'
        OR pg_get_constraintdef(oid) ILIKE '%sucursal_recojo_id%'
        OR pg_get_constraintdef(oid) ILIKE '%direccion_referencia%'
        OR pg_get_constraintdef(oid) ILIKE '%costo_calculado%'
      )
  LOOP
    EXECUTE format('ALTER TABLE comercial.pedidos_entrega DROP CONSTRAINT %I', c.conname);
  END LOOP;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid='comercial.pedidos_entrega'::regclass
      AND conname='ck_pedidos_delivery_requiere_datos'
  ) THEN
    ALTER TABLE comercial.pedidos_entrega
      ADD CONSTRAINT ck_pedidos_delivery_requiere_datos CHECK (
        modalidad='RECOJO' OR (direccion IS NOT NULL AND anillo_destino IS NOT NULL)
      );
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid='comercial.pedidos_entrega'::regclass
      AND conname='ck_pedidos_recojo_sin_tarifa'
  ) THEN
    ALTER TABLE comercial.pedidos_entrega
      ADD CONSTRAINT ck_pedidos_recojo_sin_tarifa CHECK (
        modalidad='DELIVERY' OR costo_entrega=0
      );
  END IF;
END
$compat_checks_legacy$;

COMMIT;

SELECT data_type, udt_schema, udt_name
FROM information_schema.columns
WHERE table_schema='comercial'
  AND table_name='pedidos_entrega'
  AND column_name='estado';
