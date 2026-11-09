/*
FashionStore - Esquema consolidado hasta Ciclo 2 para Neon SQL Editor.

Reejecutable: crea objetos faltantes y completa columnas introducidas por las
migraciones 0001..0003. No elimina datos. Si un objeto antiguo es incompatible,
la transaccion falla y no se registra una version de Alembic falsa.
*/
BEGIN;

CREATE SCHEMA IF NOT EXISTS seguridad;
CREATE SCHEMA IF NOT EXISTS organizacion;
CREATE SCHEMA IF NOT EXISTS catalogo;
CREATE SCHEMA IF NOT EXISTS inventario;
CREATE SCHEMA IF NOT EXISTS comercial;
CREATE SCHEMA IF NOT EXISTS inteligencia;

CREATE TABLE IF NOT EXISTS seguridad.roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre varchar(50) NOT NULL UNIQUE,
  descripcion text,
  activo boolean NOT NULL DEFAULT true,
  creado_en timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS seguridad.usuarios (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rol_id uuid NOT NULL REFERENCES seguridad.roles(id),
  nombres varchar(100) NOT NULL,
  apellidos varchar(100) NOT NULL,
  correo_electronico varchar(160) NOT NULL UNIQUE,
  contrasenia_hash varchar(255) NOT NULL,
  telefono varchar(30),
  estado varchar(20) NOT NULL DEFAULT 'ACTIVO',
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_usuarios_correo_electronico
  ON seguridad.usuarios(correo_electronico);

CREATE TABLE IF NOT EXISTS seguridad.clientes (
  usuario_id uuid PRIMARY KEY REFERENCES seguridad.usuarios(id) ON DELETE CASCADE,
  direccion_referencia text,
  fecha_nacimiento date,
  preferencias jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS organizacion.ciudades (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre varchar(100) NOT NULL UNIQUE,
  activo boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS organizacion.sucursales (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ciudad_id uuid NOT NULL REFERENCES organizacion.ciudades(id),
  nombre varchar(100) NOT NULL,
  direccion text NOT NULL,
  telefono varchar(30),
  numero_anillo smallint,
  tarifa_base_delivery numeric(12,2) NOT NULL DEFAULT 0,
  incremento_anillo_delivery numeric(12,2) NOT NULL DEFAULT 0,
  anillo_minimo_delivery smallint NOT NULL DEFAULT 1,
  anillo_maximo_delivery smallint NOT NULL DEFAULT 10,
  delivery_activo boolean NOT NULL DEFAULT true,
  activa boolean NOT NULL DEFAULT true,
  adelanto_activo boolean NOT NULL DEFAULT false,
  modalidad_adelanto varchar(20),
  valor_adelanto numeric(12,2) NOT NULL DEFAULT 0,
  CONSTRAINT uq_sucursales_ciudad_nombre UNIQUE(ciudad_id,nombre)
);

ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS numero_anillo smallint;
ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS tarifa_base_delivery numeric(12,2) NOT NULL DEFAULT 0;
ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS incremento_anillo_delivery numeric(12,2) NOT NULL DEFAULT 0;
ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS anillo_minimo_delivery smallint NOT NULL DEFAULT 1;
ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS anillo_maximo_delivery smallint NOT NULL DEFAULT 10;
ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS delivery_activo boolean NOT NULL DEFAULT true;
ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS activa boolean NOT NULL DEFAULT true;
ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS adelanto_activo boolean NOT NULL DEFAULT false;
ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS modalidad_adelanto varchar(20);
ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS valor_adelanto numeric(12,2) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS seguridad.empleados (
  usuario_id uuid PRIMARY KEY REFERENCES seguridad.usuarios(id) ON DELETE CASCADE,
  sucursal_id uuid REFERENCES organizacion.sucursales(id),
  cargo varchar(80) NOT NULL,
  activo boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS catalogo.categorias (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  categoria_padre_id uuid REFERENCES catalogo.categorias(id),
  nombre varchar(100) NOT NULL,
  descripcion text,
  activo boolean NOT NULL DEFAULT true,
  CONSTRAINT uq_categoria_padre_nombre UNIQUE(categoria_padre_id,nombre)
);
CREATE TABLE IF NOT EXISTS catalogo.tallas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), nombre varchar(30) NOT NULL UNIQUE,
  orden smallint NOT NULL DEFAULT 0, activo boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS catalogo.colores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), nombre varchar(60) NOT NULL UNIQUE,
  codigo_hex varchar(7), activo boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS catalogo.temporadas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), nombre varchar(100) NOT NULL UNIQUE,
  fecha_inicio date, fecha_fin date, activa boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS catalogo.colecciones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), nombre varchar(100) NOT NULL UNIQUE,
  descripcion text, activa boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS catalogo.proveedores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), razon_social varchar(180) NOT NULL,
  nit varchar(40) UNIQUE, contacto varchar(160), telefono varchar(30),
  correo_electronico varchar(160), direccion text, convenio text,
  activo boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS catalogo.productos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  categoria_id uuid REFERENCES catalogo.categorias(id),
  proveedor_principal_id uuid REFERENCES catalogo.proveedores(id),
  nombre varchar(180) NOT NULL, descripcion text, genero varchar(30),
  marca varchar(100), precio_base numeric(12,2) NOT NULL DEFAULT 0,
  activo boolean NOT NULL DEFAULT true, creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS catalogo.imagenes_producto (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  producto_id uuid NOT NULL REFERENCES catalogo.productos(id) ON DELETE CASCADE,
  enlace_imagen text NOT NULL, texto_alternativo varchar(180),
  orden smallint NOT NULL DEFAULT 0, es_principal boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS catalogo.producto_temporada (
  producto_id uuid NOT NULL REFERENCES catalogo.productos(id) ON DELETE CASCADE,
  temporada_id uuid NOT NULL REFERENCES catalogo.temporadas(id),
  PRIMARY KEY(producto_id,temporada_id)
);
CREATE TABLE IF NOT EXISTS catalogo.producto_coleccion (
  producto_id uuid NOT NULL REFERENCES catalogo.productos(id) ON DELETE CASCADE,
  coleccion_id uuid NOT NULL REFERENCES catalogo.colecciones(id),
  PRIMARY KEY(producto_id,coleccion_id)
);
CREATE TABLE IF NOT EXISTS catalogo.variantes_producto (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  producto_id uuid NOT NULL REFERENCES catalogo.productos(id) ON DELETE CASCADE,
  talla_id uuid NOT NULL REFERENCES catalogo.tallas(id),
  color_id uuid NOT NULL REFERENCES catalogo.colores(id),
  sku varchar(80) NOT NULL UNIQUE, codigo_barras varchar(80) UNIQUE,
  precio numeric(12,2) NOT NULL, peso_gramos integer,
  costo_promedio numeric(12,2) NOT NULL DEFAULT 0,
  costo_ultimo numeric(12,2) NOT NULL DEFAULT 0,
  recurso_prueba_virtual text, activa boolean NOT NULL DEFAULT true,
  CONSTRAINT uq_variante_prod_talla_color UNIQUE(producto_id,talla_id,color_id)
);
CREATE INDEX IF NOT EXISTS ix_variantes_producto_sku
  ON catalogo.variantes_producto(sku);
ALTER TABLE catalogo.variantes_producto ADD COLUMN IF NOT EXISTS recurso_prueba_virtual text;
ALTER TABLE catalogo.variantes_producto ADD COLUMN IF NOT EXISTS costo_promedio numeric(12,2) NOT NULL DEFAULT 0;
ALTER TABLE catalogo.variantes_producto ADD COLUMN IF NOT EXISTS costo_ultimo numeric(12,2) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS inventario.lotes_recepcion (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  proveedor_id uuid NOT NULL REFERENCES catalogo.proveedores(id),
  sucursal_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
  temporada_id uuid REFERENCES catalogo.temporadas(id),
  coleccion_id uuid REFERENCES catalogo.colecciones(id),
  recibido_por_id uuid NOT NULL REFERENCES seguridad.usuarios(id),
  numero_documento varchar(100), fecha_recepcion timestamptz NOT NULL DEFAULT now(),
  observacion text
);
CREATE TABLE IF NOT EXISTS inventario.detalles_lote_recepcion (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lote_id uuid NOT NULL REFERENCES inventario.lotes_recepcion(id) ON DELETE CASCADE,
  variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),
  cantidad integer NOT NULL, costo_unitario numeric(12,2) NOT NULL,
  CONSTRAINT uq_detalles_lote_variante UNIQUE(lote_id,variante_id)
);
CREATE TABLE IF NOT EXISTS inventario.inventario_sucursal (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),
  sucursal_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
  disponible integer NOT NULL DEFAULT 0, reservado integer NOT NULL DEFAULT 0,
  comprometido_traslado integer NOT NULL DEFAULT 0,
  en_transito integer NOT NULL DEFAULT 0,
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_inventario_variante_sucursal UNIQUE(variante_id,sucursal_id)
);
CREATE TABLE IF NOT EXISTS inventario.movimientos_inventario (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),
  sucursal_origen_id uuid REFERENCES organizacion.sucursales(id),
  sucursal_destino_id uuid REFERENCES organizacion.sucursales(id),
  responsable_id uuid REFERENCES seguridad.usuarios(id),
  tipo varchar(40) NOT NULL, cantidad integer NOT NULL,
  costo_unitario numeric(12,2) NOT NULL DEFAULT 0,
  referencia_tipo varchar(40), referencia_id uuid, linea_referencia_id uuid,
  clave_idempotencia uuid, fecha_hora timestamptz NOT NULL DEFAULT now(),
  observacion text
);
ALTER TABLE inventario.movimientos_inventario ADD COLUMN IF NOT EXISTS linea_referencia_id uuid;
ALTER TABLE inventario.movimientos_inventario ADD COLUMN IF NOT EXISTS clave_idempotencia uuid;

DO $tipos$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                 WHERE n.nspname='comercial' AND t.typname='estado_reserva') THEN
    CREATE TYPE comercial.estado_reserva AS ENUM
      ('PENDIENTE_TRASLADO','PENDIENTE','PREPARADA','ATENDIDA','COMPLETADA','CANCELADA','VENCIDA');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                 WHERE n.nspname='inventario' AND t.typname='estado_traslado') THEN
    CREATE TYPE inventario.estado_traslado AS ENUM
      ('SOLICITADO','APROBADO','RECHAZADO','DESPACHADO','RECIBIDO','CANCELADO');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                 WHERE n.nspname='comercial' AND t.typname='estado_venta') THEN
    CREATE TYPE comercial.estado_venta AS ENUM
      ('PENDIENTE_PAGO','PAGADA','CANCELADA','PARCIALMENTE_DEVUELTA','DEVUELTA');
  END IF;
END
$tipos$;

CREATE TABLE IF NOT EXISTS comercial.reservas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id uuid NOT NULL REFERENCES seguridad.clientes(usuario_id),
  sucursal_destino_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
  codigo varchar(50) NOT NULL UNIQUE,
  estado comercial.estado_reserva NOT NULL DEFAULT 'PENDIENTE',
  fecha_creacion timestamptz NOT NULL DEFAULT now(), fecha_visita timestamptz,
  vence_en timestamptz NOT NULL, observacion text,
  adelanto_modalidad varchar(20), adelanto_valor numeric(12,2),
  adelanto_monto numeric(12,2), preparada_en timestamptz, atendida_en timestamptz,
  preparada_por uuid REFERENCES seguridad.usuarios(id),
  atendida_por uuid REFERENCES seguridad.usuarios(id),
  clave_idempotencia uuid UNIQUE, hash_solicitud text,
  CONSTRAINT ck_reservas_codigo_formato CHECK(codigo LIKE 'FS-%')
);
ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS preparada_en timestamptz;
ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS atendida_en timestamptz;
ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS preparada_por uuid REFERENCES seguridad.usuarios(id);
ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS atendida_por uuid REFERENCES seguridad.usuarios(id);
ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS adelanto_modalidad varchar(20);
ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS adelanto_valor numeric(12,2);
ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS adelanto_monto numeric(12,2);
ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS clave_idempotencia uuid;
ALTER TABLE comercial.reservas ADD COLUMN IF NOT EXISTS hash_solicitud text;

CREATE TABLE IF NOT EXISTS comercial.detalles_reserva (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reserva_id uuid NOT NULL REFERENCES comercial.reservas(id) ON DELETE CASCADE,
  variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),
  cantidad_solicitada integer NOT NULL CHECK(cantidad_solicitada>0),
  cantidad_reservada integer NOT NULL DEFAULT 0 CHECK(cantidad_reservada>=0),
  cantidad_pendiente_traslado integer NOT NULL DEFAULT 0 CHECK(cantidad_pendiente_traslado>=0),
  cantidad_vendida integer NOT NULL DEFAULT 0 CHECK(cantidad_vendida>=0),
  cantidad_liberada integer NOT NULL DEFAULT 0 CHECK(cantidad_liberada>=0),
  estado_linea varchar(30) NOT NULL DEFAULT 'RESERVADA'
    CHECK(estado_linea IN ('PENDIENTE_TRASLADO','RESERVADA','RECHAZADA','VENDIDA_PARCIAL','VENDIDA','LIBERADA')),
  CONSTRAINT uq_detalles_reserva_reserva_variante UNIQUE(reserva_id,variante_id)
);
ALTER TABLE comercial.detalles_reserva ADD COLUMN IF NOT EXISTS cantidad_pendiente_traslado integer NOT NULL DEFAULT 0;
ALTER TABLE comercial.detalles_reserva ADD COLUMN IF NOT EXISTS cantidad_vendida integer NOT NULL DEFAULT 0;
ALTER TABLE comercial.detalles_reserva ADD COLUMN IF NOT EXISTS cantidad_liberada integer NOT NULL DEFAULT 0;
ALTER TABLE comercial.detalles_reserva ADD COLUMN IF NOT EXISTS estado_linea varchar(30) NOT NULL DEFAULT 'RESERVADA';

CREATE TABLE IF NOT EXISTS inventario.traslados (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), reserva_id uuid REFERENCES comercial.reservas(id),
  sucursal_origen_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
  sucursal_destino_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
  estado inventario.estado_traslado NOT NULL DEFAULT 'SOLICITADO',
  solicitado_por_id uuid NOT NULL REFERENCES seguridad.usuarios(id),
  aprobado_por_id uuid REFERENCES seguridad.usuarios(id),
  fecha_solicitud timestamptz NOT NULL DEFAULT now(), fecha_aprobacion timestamptz,
  fecha_despacho timestamptz, fecha_recepcion timestamptz, motivo_rechazo text,
  clave_idempotencia uuid UNIQUE, hash_solicitud text,
  CONSTRAINT ck_traslados_origen_destino_distintos CHECK(sucursal_origen_id<>sucursal_destino_id)
);
ALTER TABLE inventario.traslados ADD COLUMN IF NOT EXISTS clave_idempotencia uuid;
ALTER TABLE inventario.traslados ADD COLUMN IF NOT EXISTS hash_solicitud text;

CREATE TABLE IF NOT EXISTS inventario.detalles_traslado (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  traslado_id uuid NOT NULL REFERENCES inventario.traslados(id) ON DELETE CASCADE,
  detalle_reserva_id uuid REFERENCES comercial.detalles_reserva(id),
  variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),
  cantidad integer NOT NULL CHECK(cantidad>0),
  CONSTRAINT uq_detalles_traslado_traslado_variante UNIQUE(traslado_id,variante_id)
);
ALTER TABLE inventario.detalles_traslado ADD COLUMN IF NOT EXISTS detalle_reserva_id uuid REFERENCES comercial.detalles_reserva(id);

CREATE TABLE IF NOT EXISTS comercial.ventas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), numero varchar(50) NOT NULL UNIQUE,
  cliente_id uuid REFERENCES seguridad.clientes(usuario_id),
  reserva_id uuid REFERENCES comercial.reservas(id),
  sucursal_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
  cajero_id uuid REFERENCES seguridad.usuarios(id),
  canal varchar(20) NOT NULL DEFAULT 'PRESENCIAL' CHECK(canal IN ('PRESENCIAL','WEB','MOVIL')),
  estado comercial.estado_venta NOT NULL DEFAULT 'PENDIENTE_PAGO',
  subtotal numeric(12,2) NOT NULL DEFAULT 0 CHECK(subtotal>=0),
  descuento numeric(12,2) NOT NULL DEFAULT 0 CHECK(descuento>=0),
  costo_entrega numeric(12,2) NOT NULL DEFAULT 0 CHECK(costo_entrega>=0),
  total numeric(12,2) NOT NULL DEFAULT 0 CHECK(total>=0),
  creada_en timestamptz NOT NULL DEFAULT now(), confirmada_en timestamptz,
  adelanto_descontado numeric(12,2) NOT NULL DEFAULT 0,
  clave_idempotencia uuid UNIQUE, hash_solicitud text
);
ALTER TABLE comercial.ventas ADD COLUMN IF NOT EXISTS adelanto_descontado numeric(12,2) NOT NULL DEFAULT 0;
ALTER TABLE comercial.ventas ADD COLUMN IF NOT EXISTS cajero_id uuid REFERENCES seguridad.usuarios(id);
ALTER TABLE comercial.ventas ADD COLUMN IF NOT EXISTS canal varchar(20) NOT NULL DEFAULT 'PRESENCIAL';
ALTER TABLE comercial.ventas ADD COLUMN IF NOT EXISTS costo_entrega numeric(12,2) NOT NULL DEFAULT 0;
ALTER TABLE comercial.ventas ADD COLUMN IF NOT EXISTS clave_idempotencia uuid;
ALTER TABLE comercial.ventas ADD COLUMN IF NOT EXISTS hash_solicitud text;

CREATE TABLE IF NOT EXISTS comercial.detalles_venta (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  venta_id uuid NOT NULL REFERENCES comercial.ventas(id) ON DELETE CASCADE,
  detalle_reserva_id uuid REFERENCES comercial.detalles_reserva(id),
  variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),
  cantidad integer NOT NULL CHECK(cantidad>0),
  precio_unitario numeric(12,2) NOT NULL CHECK(precio_unitario>=0),
  descuento numeric(12,2) NOT NULL DEFAULT 0 CHECK(descuento>=0),
  costo_promedio numeric(12,2) NOT NULL DEFAULT 0 CHECK(costo_promedio>=0),
  CONSTRAINT uq_detalles_venta_venta_variante UNIQUE(venta_id,variante_id)
);
ALTER TABLE comercial.detalles_venta ADD COLUMN IF NOT EXISTS detalle_reserva_id uuid REFERENCES comercial.detalles_reserva(id);
ALTER TABLE comercial.detalles_venta ADD COLUMN IF NOT EXISTS costo_promedio numeric(12,2) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS comercial.pagos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contexto varchar(20) NOT NULL CHECK(contexto IN ('RESERVA','VENTA')),
  reserva_id uuid REFERENCES comercial.reservas(id), venta_id uuid REFERENCES comercial.ventas(id),
  metodo varchar(30) NOT NULL CHECK(metodo IN ('EFECTIVO','TARJETA_CAJA','QR_CAJA','TRANSFERENCIA','STRIPE_TEST')),
  tipo_pago varchar(20) CHECK(tipo_pago IN ('ADELANTO','TOTAL','PAGO')),
  modalidad_adelanto varchar(20) CHECK(modalidad_adelanto IN ('MONTO_FIJO','PORCENTAJE')),
  monto numeric(12,2) NOT NULL CHECK(monto>0),
  no_reembolsable boolean NOT NULL DEFAULT false,
  estado varchar(20) NOT NULL DEFAULT 'PENDIENTE' CHECK(estado IN ('PENDIENTE','APROBADO','RECHAZADO','ANULADO')),
  referencia_externa varchar(160), proveedor_pago varchar(40), pagado_en timestamptz,
  clave_idempotencia uuid UNIQUE, hash_solicitud text,
  CONSTRAINT ck_pagos_contexto_referencia CHECK(
    (contexto='RESERVA' AND reserva_id IS NOT NULL) OR
    (contexto='VENTA' AND venta_id IS NOT NULL))
);
ALTER TABLE comercial.pagos ADD COLUMN IF NOT EXISTS no_reembolsable boolean NOT NULL DEFAULT false;
ALTER TABLE comercial.pagos ADD COLUMN IF NOT EXISTS tipo_pago varchar(20);
ALTER TABLE comercial.pagos ADD COLUMN IF NOT EXISTS modalidad_adelanto varchar(20);
ALTER TABLE comercial.pagos ADD COLUMN IF NOT EXISTS clave_idempotencia uuid;
ALTER TABLE comercial.pagos ADD COLUMN IF NOT EXISTS hash_solicitud text;

ALTER TABLE comercial.detalles_reserva DROP CONSTRAINT IF EXISTS ck_detalle_reserva_vendida_lte_reservada;
ALTER TABLE comercial.detalles_reserva DROP CONSTRAINT IF EXISTS ck_detalle_reserva_suma_consistente;
UPDATE comercial.detalles_reserva
  SET cantidad_reservada = cantidad_reservada - cantidad_vendida
  WHERE cantidad_vendida > 0 AND cantidad_reservada >= cantidad_vendida;

DO $checks$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_sucursales_modalidad_adelanto') THEN
    ALTER TABLE organizacion.sucursales ADD CONSTRAINT ck_sucursales_modalidad_adelanto
      CHECK(modalidad_adelanto IS NULL OR modalidad_adelanto IN ('MONTO_FIJO','PORCENTAJE'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_sucursales_valor_adelanto_nneg') THEN
    ALTER TABLE organizacion.sucursales ADD CONSTRAINT ck_sucursales_valor_adelanto_nneg CHECK(valor_adelanto>=0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_sucursales_adelanto_porcentaje_max') THEN
    ALTER TABLE organizacion.sucursales ADD CONSTRAINT ck_sucursales_adelanto_porcentaje_max
      CHECK(modalidad_adelanto IS NULL OR modalidad_adelanto<>'PORCENTAJE' OR valor_adelanto<=100);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_sucursales_adelanto_coherente') THEN
    ALTER TABLE organizacion.sucursales ADD CONSTRAINT ck_sucursales_adelanto_coherente
      CHECK(adelanto_activo=false OR (modalidad_adelanto IS NOT NULL AND valor_adelanto>0));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_inventario_disponible_nneg') THEN
    ALTER TABLE inventario.inventario_sucursal ADD CONSTRAINT ck_inventario_disponible_nneg CHECK(disponible>=0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_inventario_reservado_nneg') THEN
    ALTER TABLE inventario.inventario_sucursal ADD CONSTRAINT ck_inventario_reservado_nneg CHECK(reservado>=0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_inventario_comprometido_nneg') THEN
    ALTER TABLE inventario.inventario_sucursal ADD CONSTRAINT ck_inventario_comprometido_nneg CHECK(comprometido_traslado>=0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_inventario_en_transito_nneg') THEN
    ALTER TABLE inventario.inventario_sucursal ADD CONSTRAINT ck_inventario_en_transito_nneg CHECK(en_transito>=0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_detalle_reserva_cantidades_consistentes') THEN
    ALTER TABLE comercial.detalles_reserva ADD CONSTRAINT ck_detalle_reserva_cantidades_consistentes
      CHECK(cantidad_reservada+cantidad_pendiente_traslado+cantidad_vendida+cantidad_liberada<=cantidad_solicitada);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_ventas_adelanto_desc_nneg') THEN
    ALTER TABLE comercial.ventas ADD CONSTRAINT ck_ventas_adelanto_desc_nneg CHECK(adelanto_descontado>=0);
  END IF;
END
$checks$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_movimientos_clave_idempotencia
  ON inventario.movimientos_inventario(clave_idempotencia);
DROP INDEX IF EXISTS inventario.uq_movimientos_efecto_logico;
CREATE UNIQUE INDEX uq_movimientos_efecto_logico
  ON inventario.movimientos_inventario(
    referencia_tipo,referencia_id,tipo,variante_id,
    coalesce(sucursal_origen_id,'00000000-0000-0000-0000-000000000000'::uuid),
    coalesce(sucursal_destino_id,'00000000-0000-0000-0000-000000000000'::uuid),
    coalesce(linea_referencia_id,'00000000-0000-0000-0000-000000000000'::uuid))
  WHERE referencia_tipo IS NOT NULL AND referencia_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reserva_estado_vencimiento ON comercial.reservas(estado,vence_en);
CREATE INDEX IF NOT EXISTS idx_reservas_cliente ON comercial.reservas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_reservas_sucursal ON comercial.reservas(sucursal_destino_id);
CREATE INDEX IF NOT EXISTS idx_detalle_reserva_reserva ON comercial.detalles_reserva(reserva_id);
CREATE INDEX IF NOT EXISTS idx_traslado_estado ON inventario.traslados(estado,fecha_solicitud);
CREATE INDEX IF NOT EXISTS idx_traslados_reserva ON inventario.traslados(reserva_id);
CREATE INDEX IF NOT EXISTS idx_ventas_sucursal_fecha ON comercial.ventas(sucursal_id,creada_en DESC);
CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON comercial.ventas(cliente_id,creada_en DESC);
CREATE INDEX IF NOT EXISTS idx_pagos_reserva ON comercial.pagos(contexto,reserva_id);
CREATE INDEX IF NOT EXISTS idx_pagos_venta ON comercial.pagos(contexto,venta_id);

CREATE TABLE IF NOT EXISTS public.alembic_version (
  version_num varchar(32) NOT NULL PRIMARY KEY
);
DELETE FROM public.alembic_version;
INSERT INTO public.alembic_version(version_num) VALUES('0003_ciclo2_linea_invariante');

COMMIT;

