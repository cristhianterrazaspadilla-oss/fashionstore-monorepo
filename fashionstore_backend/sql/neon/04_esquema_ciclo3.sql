/*
FashionStore - Upgrade de Neon desde Ciclo 2 a Ciclo 3.

Requisito: public.alembic_version debe estar en 0003_ciclo2_linea_invariante
o en una version posterior de Ciclo 3. No elimina ni reemplaza datos.
Equivale a las migraciones Alembic 0004_ciclo3_backend y
0005_ciclo3_correcciones.
*/
BEGIN;

DO $precondiciones$
DECLARE version_actual text;
BEGIN
  IF to_regclass('comercial.ventas') IS NULL
     OR to_regclass('comercial.pagos') IS NULL
     OR to_regclass('catalogo.variantes_producto') IS NULL THEN
    RAISE EXCEPTION 'Falta el esquema de Ciclo 2. Ejecute y verifique primero 01_esquema_hasta_ciclo2.sql';
  END IF;
  SELECT version_num INTO version_actual FROM public.alembic_version LIMIT 1;
  IF version_actual IS NULL OR version_actual NOT IN (
    '0003_ciclo2_linea_invariante','0004_ciclo3_backend','0005_ciclo3_correcciones'
  ) THEN
    RAISE EXCEPTION 'Version Alembic no compatible: %', coalesce(version_actual,'NULL');
  END IF;
END
$precondiciones$;

CREATE SCHEMA IF NOT EXISTS inteligencia;

DO $tipo$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
    WHERE n.nspname='comercial' AND t.typname='estado_entrega'
  ) THEN
    CREATE TYPE comercial.estado_entrega AS ENUM
      ('SOLICITADO','PREPARADO','LISTO_RECOJO','EN_REPARTO','RECOGIDO','ENTREGADO','CANCELADO');
  END IF;
END
$tipo$;

CREATE TABLE IF NOT EXISTS comercial.carritos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id uuid NOT NULL REFERENCES seguridad.clientes(usuario_id),
  canal varchar(10) NOT NULL DEFAULT 'WEB' CHECK(canal IN ('WEB','MOVIL')),
  estado varchar(20) NOT NULL DEFAULT 'ACTIVO' CHECK(estado IN ('ACTIVO','CONVERTIDO','ABANDONADO')),
  creada_en timestamptz NOT NULL DEFAULT now(),
  actualizada_en timestamptz NOT NULL DEFAULT now(),
  convertida_en timestamptz,
  venta_id uuid REFERENCES comercial.ventas(id)
);
-- Compatibilidad con el DDL preliminar del documento final, que usaba
-- creado_en/actualizado_en y no incluia canal ni venta_id.
ALTER TABLE comercial.carritos ADD COLUMN IF NOT EXISTS canal varchar(10) DEFAULT 'WEB';
ALTER TABLE comercial.carritos ADD COLUMN IF NOT EXISTS creada_en timestamptz DEFAULT now();
ALTER TABLE comercial.carritos ADD COLUMN IF NOT EXISTS actualizada_en timestamptz DEFAULT now();
ALTER TABLE comercial.carritos ADD COLUMN IF NOT EXISTS convertida_en timestamptz;
ALTER TABLE comercial.carritos ADD COLUMN IF NOT EXISTS venta_id uuid REFERENCES comercial.ventas(id);
UPDATE comercial.carritos SET canal='WEB' WHERE canal IS NULL;
DO $compat_carritos_fechas$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='comercial' AND table_name='carritos' AND column_name='creado_en') THEN
    EXECUTE 'UPDATE comercial.carritos SET creada_en=coalesce(creada_en,creado_en)';
    EXECUTE 'ALTER TABLE comercial.carritos ALTER COLUMN creado_en SET DEFAULT now()';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='comercial' AND table_name='carritos' AND column_name='actualizado_en') THEN
    EXECUTE 'UPDATE comercial.carritos SET actualizada_en=coalesce(actualizada_en,actualizado_en)';
    EXECUTE 'ALTER TABLE comercial.carritos ALTER COLUMN actualizado_en SET DEFAULT now()';
  END IF;
END
$compat_carritos_fechas$;
ALTER TABLE comercial.carritos ALTER COLUMN canal SET NOT NULL;
ALTER TABLE comercial.carritos ALTER COLUMN creada_en SET NOT NULL;
ALTER TABLE comercial.carritos ALTER COLUMN actualizada_en SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_carritos_activo_por_cliente_canal
  ON comercial.carritos(cliente_id,canal) WHERE estado='ACTIVO';
CREATE INDEX IF NOT EXISTS idx_carritos_cliente_estado
  ON comercial.carritos(cliente_id,estado);

CREATE TABLE IF NOT EXISTS comercial.detalles_carrito (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  carrito_id uuid NOT NULL REFERENCES comercial.carritos(id) ON DELETE CASCADE,
  variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),
  cantidad integer NOT NULL CHECK(cantidad>0),
  agregado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_detalle_carrito_carrito_variante UNIQUE(carrito_id,variante_id)
);
ALTER TABLE comercial.detalles_carrito ADD COLUMN IF NOT EXISTS agregado_en timestamptz DEFAULT now();
ALTER TABLE comercial.detalles_carrito ADD COLUMN IF NOT EXISTS actualizado_en timestamptz DEFAULT now();
UPDATE comercial.detalles_carrito SET agregado_en=now() WHERE agregado_en IS NULL;
UPDATE comercial.detalles_carrito SET actualizado_en=agregado_en WHERE actualizado_en IS NULL;
ALTER TABLE comercial.detalles_carrito ALTER COLUMN agregado_en SET NOT NULL;
ALTER TABLE comercial.detalles_carrito ALTER COLUMN actualizado_en SET NOT NULL;
DO $compat_detalle_carrito_unico$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='comercial' AND table_name='detalles_carrito' AND column_name='sucursal_origen_id') THEN
    ALTER TABLE comercial.detalles_carrito ALTER COLUMN sucursal_origen_id DROP NOT NULL;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conrelid='comercial.detalles_carrito'::regclass
      AND conname='uq_detalle_carrito_carrito_variante'
  ) THEN
    IF EXISTS (
      SELECT 1 FROM comercial.detalles_carrito
      GROUP BY carrito_id,variante_id HAVING count(*)>1
    ) THEN
      RAISE EXCEPTION 'Hay variantes duplicadas por carrito; consolide esos datos antes de actualizar Ciclo 3';
    END IF;
    ALTER TABLE comercial.detalles_carrito ADD CONSTRAINT uq_detalle_carrito_carrito_variante
      UNIQUE(carrito_id,variante_id);
  END IF;
END
$compat_detalle_carrito_unico$;
CREATE INDEX IF NOT EXISTS idx_detalle_carrito_carrito
  ON comercial.detalles_carrito(carrito_id);

CREATE TABLE IF NOT EXISTS comercial.pedidos_entrega (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venta_id uuid NOT NULL UNIQUE REFERENCES comercial.ventas(id) ON DELETE CASCADE,
  sucursal_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
  cliente_id uuid NOT NULL REFERENCES seguridad.clientes(usuario_id),
  modalidad varchar(20) NOT NULL CHECK(modalidad IN ('RECOJO','DELIVERY')),
  estado varchar(20) NOT NULL DEFAULT 'SOLICITADO'
    CHECK(estado IN ('SOLICITADO','PREPARADO','LISTO_RECOJO','EN_REPARTO','RECOGIDO','ENTREGADO','CANCELADO')),
  anillo_sucursal smallint,
  anillo_destino smallint,
  anillo_minimo smallint,
  anillo_maximo smallint,
  direccion text,
  tarifa_base numeric(12,2) NOT NULL DEFAULT 0 CHECK(tarifa_base>=0),
  incremento_anillo numeric(12,2) NOT NULL DEFAULT 0 CHECK(incremento_anillo>=0),
  costo_entrega numeric(12,2) NOT NULL DEFAULT 0 CHECK(costo_entrega>=0),
  codigo_recojo varchar(20),
  creada_en timestamptz NOT NULL DEFAULT now(),
  actualizada_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_pedidos_delivery_requiere_datos CHECK(
    modalidad='RECOJO' OR (direccion IS NOT NULL AND anillo_destino IS NOT NULL)
  ),
  CONSTRAINT ck_pedidos_recojo_sin_tarifa CHECK(modalidad='DELIVERY' OR costo_entrega=0)
);
-- Traduce sin borrar datos la version preliminar tipo_entrega/sucursal_recojo.
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS sucursal_id uuid REFERENCES organizacion.sucursales(id);
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS cliente_id uuid REFERENCES seguridad.clientes(usuario_id);
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS modalidad varchar(20);
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS anillo_sucursal smallint;
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS anillo_minimo smallint;
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS anillo_maximo smallint;
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS direccion text;
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS tarifa_base numeric(12,2) DEFAULT 0;
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS incremento_anillo numeric(12,2) DEFAULT 0;
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS costo_entrega numeric(12,2) DEFAULT 0;
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS codigo_recojo varchar(20);
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS creada_en timestamptz DEFAULT now();
ALTER TABLE comercial.pedidos_entrega ADD COLUMN IF NOT EXISTS actualizada_en timestamptz DEFAULT now();
DO $compat_pedidos$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='comercial' AND table_name='pedidos_entrega' AND column_name='tipo_entrega') THEN
    EXECUTE 'UPDATE comercial.pedidos_entrega SET modalidad=coalesce(modalidad,tipo_entrega)';
    EXECUTE 'ALTER TABLE comercial.pedidos_entrega ALTER COLUMN tipo_entrega DROP NOT NULL';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='comercial' AND table_name='pedidos_entrega' AND column_name='direccion_referencia') THEN
    EXECUTE 'UPDATE comercial.pedidos_entrega SET direccion=coalesce(direccion,direccion_referencia)';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='comercial' AND table_name='pedidos_entrega' AND column_name='costo_calculado') THEN
    EXECUTE 'UPDATE comercial.pedidos_entrega SET costo_entrega=coalesce(costo_calculado,0)';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='comercial' AND table_name='pedidos_entrega' AND column_name='sucursal_recojo_id') THEN
    EXECUTE 'UPDATE comercial.pedidos_entrega SET sucursal_id=coalesce(sucursal_id,sucursal_recojo_id)';
  END IF;
END
$compat_pedidos$;
UPDATE comercial.pedidos_entrega pe SET
  sucursal_id=coalesce(pe.sucursal_id,v.sucursal_id),
  cliente_id=coalesce(pe.cliente_id,v.cliente_id),
  modalidad=coalesce(pe.modalidad,'RECOJO'),
  anillo_sucursal=coalesce(pe.anillo_sucursal,s.numero_anillo),
  anillo_minimo=coalesce(pe.anillo_minimo,s.anillo_minimo_delivery),
  anillo_maximo=coalesce(pe.anillo_maximo,s.anillo_maximo_delivery),
  tarifa_base=coalesce(pe.tarifa_base,s.tarifa_base_delivery,0),
  incremento_anillo=coalesce(pe.incremento_anillo,s.incremento_anillo_delivery,0),
  creada_en=coalesce(pe.creada_en,v.creada_en), actualizada_en=coalesce(pe.actualizada_en,v.creada_en)
FROM comercial.ventas v LEFT JOIN organizacion.sucursales s ON s.id=v.sucursal_id
WHERE v.id=pe.venta_id;
DO $validar_pedidos_legacy$
BEGIN
  IF EXISTS (SELECT 1 FROM comercial.pedidos_entrega WHERE sucursal_id IS NULL OR cliente_id IS NULL OR modalidad IS NULL) THEN
    RAISE EXCEPTION 'Hay pedidos legacy sin sucursal/cliente/modalidad derivable; deben corregirse antes del upgrade';
  END IF;
END
$validar_pedidos_legacy$;
ALTER TABLE comercial.pedidos_entrega ALTER COLUMN sucursal_id SET NOT NULL;
ALTER TABLE comercial.pedidos_entrega ALTER COLUMN cliente_id SET NOT NULL;
ALTER TABLE comercial.pedidos_entrega ALTER COLUMN modalidad SET NOT NULL;
-- La version preliminar usaba comercial.estado_entrega (ENUM); el contrato
-- definitivo del backend usa varchar(20). Normalizarlo evita incompatibilidad
-- al insertar/actualizar desde la semilla y FastAPI.
DO $compat_tipo_estado_pedido$
BEGIN
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
CREATE INDEX IF NOT EXISTS idx_pedidos_sucursal_estado
  ON comercial.pedidos_entrega(sucursal_id,estado);
CREATE INDEX IF NOT EXISTS idx_pedidos_venta ON comercial.pedidos_entrega(venta_id);

CREATE TABLE IF NOT EXISTS catalogo.promociones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  codigo varchar(40) NOT NULL UNIQUE,
  nombre varchar(180) NOT NULL,
  descripcion text,
  tipo varchar(20) NOT NULL CHECK(tipo IN ('PORCENTAJE','MONTO_FIJO')),
  valor numeric(12,2) NOT NULL CHECK(valor>=0),
  activa boolean NOT NULL DEFAULT true,
  vigencia_inicio timestamptz,
  vigencia_fin timestamptz,
  creada_en timestamptz NOT NULL DEFAULT now(),
  actualizada_en timestamptz NOT NULL DEFAULT now(),
  creada_por uuid REFERENCES seguridad.usuarios(id),
  CONSTRAINT ck_promociones_porcentaje_max CHECK(tipo<>'PORCENTAJE' OR valor<=100),
  CONSTRAINT ck_promociones_vigencia_coherente CHECK(
    vigencia_fin IS NULL OR vigencia_inicio IS NULL OR vigencia_inicio<=vigencia_fin
  )
);
ALTER TABLE catalogo.promociones ADD COLUMN IF NOT EXISTS codigo varchar(40);
ALTER TABLE catalogo.promociones ADD COLUMN IF NOT EXISTS descripcion text;
ALTER TABLE catalogo.promociones ADD COLUMN IF NOT EXISTS vigencia_inicio timestamptz;
ALTER TABLE catalogo.promociones ADD COLUMN IF NOT EXISTS vigencia_fin timestamptz;
ALTER TABLE catalogo.promociones ADD COLUMN IF NOT EXISTS creada_en timestamptz DEFAULT now();
ALTER TABLE catalogo.promociones ADD COLUMN IF NOT EXISTS actualizada_en timestamptz DEFAULT now();
ALTER TABLE catalogo.promociones ADD COLUMN IF NOT EXISTS creada_por uuid REFERENCES seguridad.usuarios(id);
DO $compat_promociones$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='catalogo' AND table_name='promociones' AND column_name='fecha_inicio') THEN
    EXECUTE 'UPDATE catalogo.promociones SET vigencia_inicio=coalesce(vigencia_inicio,fecha_inicio)';
    EXECUTE 'ALTER TABLE catalogo.promociones ALTER COLUMN fecha_inicio DROP NOT NULL';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='catalogo' AND table_name='promociones' AND column_name='fecha_fin') THEN
    EXECUTE 'UPDATE catalogo.promociones SET vigencia_fin=coalesce(vigencia_fin,fecha_fin)';
    EXECUTE 'ALTER TABLE catalogo.promociones ALTER COLUMN fecha_fin DROP NOT NULL';
  END IF;
END
$compat_promociones$;
UPDATE catalogo.promociones SET codigo='LEGACY-'||replace(id::text,'-','') WHERE codigo IS NULL;
ALTER TABLE catalogo.promociones ALTER COLUMN codigo SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_promociones_codigo ON catalogo.promociones(codigo);
CREATE INDEX IF NOT EXISTS idx_promociones_vigencia
  ON catalogo.promociones(activa,vigencia_inicio,vigencia_fin);

CREATE TABLE IF NOT EXISTS catalogo.promocion_variante (
  promocion_id uuid NOT NULL REFERENCES catalogo.promociones(id) ON DELETE CASCADE,
  variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id) ON DELETE CASCADE,
  creada_en timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(promocion_id,variante_id)
);
CREATE INDEX IF NOT EXISTS idx_promocion_variante_variante
  ON catalogo.promocion_variante(variante_id);

CREATE TABLE IF NOT EXISTS inteligencia.historial_navegacion (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id uuid REFERENCES seguridad.clientes(usuario_id),
  usuario_id uuid REFERENCES seguridad.usuarios(id),
  variante_id uuid REFERENCES catalogo.variantes_producto(id),
  producto_id uuid REFERENCES catalogo.productos(id),
  evento varchar(40) NOT NULL,
  metadatos jsonb NOT NULL DEFAULT '{}'::jsonb,
  creada_en timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE inteligencia.historial_navegacion ADD COLUMN IF NOT EXISTS usuario_id uuid REFERENCES seguridad.usuarios(id);
ALTER TABLE inteligencia.historial_navegacion ADD COLUMN IF NOT EXISTS creada_en timestamptz DEFAULT now();
DO $compat_historial$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='inteligencia' AND table_name='historial_navegacion' AND column_name='ocurrido_en') THEN
    EXECUTE 'UPDATE inteligencia.historial_navegacion SET creada_en=coalesce(creada_en,ocurrido_en)';
  END IF;
END
$compat_historial$;
UPDATE inteligencia.historial_navegacion SET usuario_id=cliente_id WHERE usuario_id IS NULL AND cliente_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_navegacion_cliente_fecha
  ON inteligencia.historial_navegacion(cliente_id,creada_en DESC);
CREATE INDEX IF NOT EXISTS idx_navegacion_evento
  ON inteligencia.historial_navegacion(evento);

CREATE TABLE IF NOT EXISTS inteligencia.solicitudes_ia (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id uuid REFERENCES seguridad.usuarios(id),
  cliente_id uuid REFERENCES seguridad.clientes(usuario_id),
  tipo varchar(30) NOT NULL CHECK(tipo IN ('RECOMENDACION','BUSQUEDA_VOZ','REPORTE','DECISION_INVENTARIO')),
  entrada text NOT NULL DEFAULT '',
  funcion_usada varchar(60),
  parametros jsonb NOT NULL DEFAULT '{}'::jsonb,
  respuesta text NOT NULL DEFAULT '',
  datos jsonb NOT NULL DEFAULT '{}'::jsonb,
  proveedor varchar(20) NOT NULL DEFAULT 'DETERMINISTA',
  latencia_ms integer NOT NULL DEFAULT 0 CHECK(latencia_ms>=0),
  creada_en timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE inteligencia.solicitudes_ia ADD COLUMN IF NOT EXISTS cliente_id uuid REFERENCES seguridad.clientes(usuario_id);
ALTER TABLE inteligencia.solicitudes_ia ADD COLUMN IF NOT EXISTS entrada text DEFAULT '';
ALTER TABLE inteligencia.solicitudes_ia ADD COLUMN IF NOT EXISTS funcion_usada varchar(60);
ALTER TABLE inteligencia.solicitudes_ia ADD COLUMN IF NOT EXISTS parametros jsonb DEFAULT '{}'::jsonb;
ALTER TABLE inteligencia.solicitudes_ia ADD COLUMN IF NOT EXISTS proveedor varchar(20) DEFAULT 'DETERMINISTA';
ALTER TABLE inteligencia.solicitudes_ia ADD COLUMN IF NOT EXISTS latencia_ms integer DEFAULT 0;
DO $compat_solicitudes$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='inteligencia' AND table_name='solicitudes_ia' AND column_name='consulta') THEN
    EXECUTE 'UPDATE inteligencia.solicitudes_ia SET entrada=coalesce(nullif(entrada,''''),consulta)';
    EXECUTE 'ALTER TABLE inteligencia.solicitudes_ia ALTER COLUMN consulta DROP NOT NULL';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='inteligencia' AND table_name='solicitudes_ia' AND column_name='canal_entrada') THEN
    EXECUTE 'ALTER TABLE inteligencia.solicitudes_ia ALTER COLUMN canal_entrada DROP NOT NULL';
  END IF;
END
$compat_solicitudes$;
UPDATE inteligencia.solicitudes_ia SET entrada='' WHERE entrada IS NULL;
UPDATE inteligencia.solicitudes_ia SET parametros='{}'::jsonb WHERE parametros IS NULL;
UPDATE inteligencia.solicitudes_ia SET proveedor='DETERMINISTA' WHERE proveedor IS NULL;
UPDATE inteligencia.solicitudes_ia SET latencia_ms=0 WHERE latencia_ms IS NULL;
ALTER TABLE inteligencia.solicitudes_ia ALTER COLUMN entrada SET NOT NULL;
ALTER TABLE inteligencia.solicitudes_ia ALTER COLUMN parametros SET NOT NULL;
ALTER TABLE inteligencia.solicitudes_ia ALTER COLUMN proveedor SET NOT NULL;
ALTER TABLE inteligencia.solicitudes_ia ALTER COLUMN latencia_ms SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_solicitudes_tipo_fecha
  ON inteligencia.solicitudes_ia(tipo,creada_en DESC);
CREATE INDEX IF NOT EXISTS idx_solicitudes_usuario
  ON inteligencia.solicitudes_ia(usuario_id);

CREATE TABLE IF NOT EXISTS comercial.registros_idempotencia (
  clave uuid NOT NULL DEFAULT gen_random_uuid(),
  usuario_id uuid NOT NULL,
  recurso_tipo varchar(40) NOT NULL,
  operacion varchar(80) NOT NULL,
  hash_solicitud text NOT NULL,
  recurso_id uuid,
  respuesta jsonb NOT NULL DEFAULT '{}'::jsonb,
  creada_en timestamptz NOT NULL DEFAULT now(),
  expira_en timestamptz,
  CONSTRAINT registros_idempotencia_pkey PRIMARY KEY(clave,usuario_id,recurso_tipo,operacion)
);

-- Completa instalaciones que ya ejecutaron 0004 pero todavia no 0005.
ALTER TABLE comercial.registros_idempotencia ADD COLUMN IF NOT EXISTS usuario_id uuid;
ALTER TABLE comercial.registros_idempotencia ADD COLUMN IF NOT EXISTS operacion varchar(80);
UPDATE comercial.registros_idempotencia SET operacion=recurso_tipo WHERE operacion IS NULL;
UPDATE comercial.registros_idempotencia
SET usuario_id='00000000-0000-0000-0000-000000000000'::uuid WHERE usuario_id IS NULL;
ALTER TABLE comercial.registros_idempotencia ALTER COLUMN usuario_id SET NOT NULL;
ALTER TABLE comercial.registros_idempotencia ALTER COLUMN operacion SET NOT NULL;
DO $pk_idempotencia$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    WHERE c.conrelid='comercial.registros_idempotencia'::regclass
      AND c.conname='registros_idempotencia_pkey'
      AND pg_get_constraintdef(c.oid) LIKE '%clave, usuario_id, recurso_tipo, operacion%'
  ) THEN
    ALTER TABLE comercial.registros_idempotencia DROP CONSTRAINT IF EXISTS registros_idempotencia_pkey;
    ALTER TABLE comercial.registros_idempotencia ADD CONSTRAINT registros_idempotencia_pkey
      PRIMARY KEY(clave,usuario_id,recurso_tipo,operacion);
  END IF;
END
$pk_idempotencia$;
CREATE INDEX IF NOT EXISTS idx_idempotencia_expira
  ON comercial.registros_idempotencia(expira_en);
CREATE INDEX IF NOT EXISTS idx_idempotencia_usuario_expira
  ON comercial.registros_idempotencia(usuario_id,expira_en);

ALTER TABLE comercial.ventas ADD COLUMN IF NOT EXISTS expira_en timestamptz;
ALTER TABLE comercial.detalles_venta ADD COLUMN IF NOT EXISTS promocion_id uuid
  REFERENCES catalogo.promociones(id);
CREATE INDEX IF NOT EXISTS idx_ventas_estado_expira ON comercial.ventas(estado,expira_en);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pagos_referencia_externa
  ON comercial.pagos(referencia_externa) WHERE referencia_externa IS NOT NULL;

DELETE FROM public.alembic_version;
INSERT INTO public.alembic_version(version_num) VALUES('0005_ciclo3_correcciones');

COMMIT;

