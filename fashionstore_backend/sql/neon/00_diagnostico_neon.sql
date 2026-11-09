/*
FashionStore - Diagnostico seguro de Neon antes de aplicar Ciclo 2.

Uso: ejecutar completo en Neon SQL Editor. Este archivo es SOLO LECTURA:
no crea, actualiza ni elimina datos. Los conteos aparecen como NOTICE.
Conservar la salida antes de continuar con 01_esquema_hasta_ciclo2.sql.
*/

SELECT current_database() AS base_actual,
       current_user AS usuario_actual,
       current_setting('server_version') AS postgres_version,
       now() AS verificado_en;

WITH esperados(esquema, objeto, tipo) AS (
  VALUES
    ('seguridad','roles','tabla'), ('seguridad','usuarios','tabla'),
    ('seguridad','clientes','tabla'), ('seguridad','empleados','tabla'),
    ('organizacion','ciudades','tabla'), ('organizacion','sucursales','tabla'),
    ('catalogo','categorias','tabla'), ('catalogo','tallas','tabla'),
    ('catalogo','colores','tabla'), ('catalogo','temporadas','tabla'),
    ('catalogo','colecciones','tabla'), ('catalogo','proveedores','tabla'),
    ('catalogo','productos','tabla'), ('catalogo','imagenes_producto','tabla'),
    ('catalogo','producto_temporada','tabla'), ('catalogo','producto_coleccion','tabla'),
    ('catalogo','variantes_producto','tabla'),
    ('inventario','lotes_recepcion','tabla'),
    ('inventario','detalles_lote_recepcion','tabla'),
    ('inventario','inventario_sucursal','tabla'),
    ('inventario','movimientos_inventario','tabla'),
    ('comercial','reservas','tabla'), ('comercial','detalles_reserva','tabla'),
    ('inventario','traslados','tabla'), ('inventario','detalles_traslado','tabla'),
    ('comercial','ventas','tabla'), ('comercial','detalles_venta','tabla'),
    ('comercial','pagos','tabla')
)
SELECT esquema, objeto, tipo,
       to_regclass(format('%I.%I', esquema, objeto)) IS NOT NULL AS existe
FROM esperados
ORDER BY esquema, objeto;

SELECT n.nspname AS esquema, t.typname AS enum,
       string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder) AS valores
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
JOIN pg_enum e ON e.enumtypid = t.oid
WHERE (n.nspname, t.typname) IN (
  ('comercial','estado_reserva'),
  ('comercial','estado_venta'),
  ('inventario','estado_traslado')
)
GROUP BY n.nspname, t.typname
ORDER BY n.nspname, t.typname;

SELECT table_schema, table_name, column_name, data_type, udt_schema, udt_name,
       is_nullable, column_default
FROM information_schema.columns
WHERE (table_schema, table_name) IN (
  ('organizacion','sucursales'),
  ('inventario','inventario_sucursal'),
  ('inventario','movimientos_inventario'),
  ('comercial','reservas'),
  ('comercial','detalles_reserva'),
  ('inventario','traslados'),
  ('comercial','ventas'),
  ('comercial','pagos')
)
ORDER BY table_schema, table_name, ordinal_position;

SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname IN ('comercial','inventario')
  AND indexname IN (
    'uq_movimientos_clave_idempotencia',
    'uq_movimientos_efecto_logico',
    'idx_reserva_estado_vencimiento',
    'idx_traslado_estado',
    'idx_ventas_sucursal_fecha'
  )
ORDER BY schemaname, indexname;

SELECT CASE
         WHEN to_regclass('public.alembic_version') IS NULL THEN
           'SIN_TABLA_ALEMBIC_VERSION'
         ELSE 'CONSULTAR_SIGUIENTE_NOTICE'
       END AS estado_alembic;

DO $diagnostico$
DECLARE
  tabla text;
  cantidad bigint;
  version_actual text;
BEGIN
  IF to_regclass('public.alembic_version') IS NOT NULL THEN
    EXECUTE 'SELECT version_num::text FROM public.alembic_version LIMIT 1'
      INTO version_actual;
    RAISE NOTICE 'alembic_version=%', coalesce(version_actual, '<vacia>');
  END IF;

  FOREACH tabla IN ARRAY ARRAY[
    'seguridad.roles', 'seguridad.usuarios', 'seguridad.clientes',
    'organizacion.sucursales', 'catalogo.productos',
    'catalogo.variantes_producto', 'inventario.inventario_sucursal',
    'inventario.movimientos_inventario', 'comercial.reservas',
    'inventario.traslados', 'comercial.ventas', 'comercial.pagos'
  ] LOOP
    IF to_regclass(tabla) IS NULL THEN
      RAISE NOTICE '%: NO EXISTE', tabla;
    ELSE
      EXECUTE format('SELECT count(*) FROM %s', tabla) INTO cantidad;
      RAISE NOTICE '%: % filas', tabla, cantidad;
    END IF;
  END LOOP;
END
$diagnostico$;

SELECT c.conname AS restriccion,
       n.nspname AS esquema,
       t.relname AS tabla,
       pg_get_constraintdef(c.oid) AS definicion
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname IN ('organizacion','inventario','comercial')
  AND (
    c.conname LIKE 'ck_inventario_%'
    OR c.conname LIKE 'ck_detalle_reserva_%'
    OR c.conname LIKE 'ck_sucursales_adelanto_%'
  )
ORDER BY n.nspname, t.relname, c.conname;

