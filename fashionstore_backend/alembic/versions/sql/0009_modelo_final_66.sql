-- Expansion del esquema 0008. Ejecutar mediante Alembic desde una copia probada.
-- No contiene CREATE DATABASE ni datos sintéticos.

ALTER TABLE organizacion.empresas
    ADD COLUMN zona_horaria varchar(80) NOT NULL DEFAULT 'America/La_Paz';

CREATE TABLE seguridad.dispositivos_autorizados (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    usuario_id uuid NOT NULL,
    sucursal_id uuid,
    canal varchar(12) NOT NULL CHECK (canal IN ('PWA','FLUTTER')),
    dispositivo_id uuid NOT NULL,
    push_destino_cifrado bytea,
    push_destino_hash varchar(64),
    estado varchar(16) NOT NULL DEFAULT 'ACTIVO' CHECK (estado IN ('ACTIVO','REVOCADO')),
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    creado_en timestamptz NOT NULL DEFAULT now(),
    revocado_en timestamptz,
    UNIQUE (id, empresa_id),
    UNIQUE (empresa_id, usuario_id, canal, dispositivo_id),
    FOREIGN KEY (usuario_id, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id),
    FOREIGN KEY (sucursal_id, empresa_id) REFERENCES organizacion.sucursales(id, empresa_id)
);

CREATE TABLE plataforma.tasas_cambio (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    version integer NOT NULL UNIQUE CHECK (version > 0),
    tasa_bob_por_usd numeric(18,8) NOT NULL CHECK (tasa_bob_por_usd > 0),
    vigente_desde timestamptz NOT NULL,
    vigente_hasta timestamptz,
    motivo text NOT NULL,
    creada_por uuid REFERENCES seguridad.usuarios(id),
    creada_en timestamptz NOT NULL DEFAULT now(),
    CHECK (vigente_hasta IS NULL OR vigente_desde < vigente_hasta),
    EXCLUDE USING gist (tstzrange(vigente_desde, vigente_hasta, '[)') WITH &&)
);

CREATE TABLE organizacion.politicas_posventa (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    version integer NOT NULL CHECK (version > 0),
    vigente_desde timestamptz NOT NULL,
    vigente_hasta timestamptz,
    plazo_voluntario_dias integer NOT NULL DEFAULT 15 CHECK (plazo_voluntario_dias > 0),
    plazo_espera_dias integer NOT NULL DEFAULT 7 CHECK (plazo_espera_dias > 0),
    plazo_oferta_horas integer NOT NULL DEFAULT 48 CHECK (plazo_oferta_horas > 0),
    objetivo_reembolso_horas integer NOT NULL DEFAULT 48 CHECK (objetivo_reembolso_horas > 0),
    reglas jsonb NOT NULL DEFAULT '{}'::jsonb,
    creada_por uuid REFERENCES seguridad.usuarios(id),
    creada_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, empresa_id),
    UNIQUE (empresa_id, version),
    CHECK (vigente_hasta IS NULL OR vigente_desde < vigente_hasta),
    EXCLUDE USING gist (empresa_id WITH =, tstzrange(vigente_desde, vigente_hasta, '[)') WITH &&)
);

CREATE TABLE comercial.pedidos_compra (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    cliente_id uuid NOT NULL,
    sucursal_id uuid NOT NULL,
    operacion_id uuid,
    metodo_preparado_id uuid,
    estado varchar(36) NOT NULL DEFAULT 'BORRADOR',
    estado_pago varchar(36) NOT NULL DEFAULT 'SIN_PAGO',
    estado_cumplimiento varchar(36) NOT NULL DEFAULT 'SIN_ASIGNACION',
    modalidad varchar(12) NOT NULL CHECK (modalidad IN ('RECOJO','DELIVERY')),
    direccion text,
    subtotal_bob numeric(14,2) NOT NULL DEFAULT 0 CHECK (subtotal_bob >= 0),
    descuento_bob numeric(14,2) NOT NULL DEFAULT 0 CHECK (descuento_bob >= 0),
    envio_bob numeric(14,2) NOT NULL DEFAULT 0 CHECK (envio_bob >= 0),
    total_bob numeric(14,2) NOT NULL DEFAULT 0 CHECK (total_bob >= 0),
    consentimiento_hash varchar(64),
    condiciones_version varchar(80),
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    creado_en timestamptz NOT NULL DEFAULT now(),
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, empresa_id),
    UNIQUE (empresa_id, operacion_id),
    FOREIGN KEY (cliente_id, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id),
    FOREIGN KEY (sucursal_id, empresa_id) REFERENCES organizacion.sucursales(id, empresa_id),
    CHECK (modalidad <> 'DELIVERY' OR direccion IS NOT NULL),
    CHECK (total_bob = subtotal_bob - descuento_bob + envio_bob)
);

CREATE INDEX ix_pedidos_compra_cliente_estado ON comercial.pedidos_compra (empresa_id, cliente_id, estado, creado_en DESC);

CREATE TABLE comercial.detalles_pedido (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    pedido_id uuid NOT NULL,
    variante_id uuid NOT NULL,
    cantidad integer NOT NULL CHECK (cantidad > 0),
    precio_unitario_bob numeric(14,2) NOT NULL CHECK (precio_unitario_bob >= 0),
    descuento_bob numeric(14,2) NOT NULL DEFAULT 0 CHECK (descuento_bob >= 0),
    total_bob numeric(14,2) NOT NULL CHECK (total_bob >= 0),
    oferta_revision integer,
    UNIQUE (id, empresa_id),
    UNIQUE (pedido_id, variante_id),
    FOREIGN KEY (pedido_id, empresa_id) REFERENCES comercial.pedidos_compra(id, empresa_id),
    FOREIGN KEY (variante_id, empresa_id) REFERENCES catalogo.variantes_producto(id, empresa_id),
    CHECK (total_bob = cantidad * precio_unitario_bob - descuento_bob)
);

CREATE TABLE comercial.ofertas_compra (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    pedido_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    documento jsonb NOT NULL,
    documento_hash varchar(64) NOT NULL,
    subtotal_bob numeric(14,2) NOT NULL CHECK (subtotal_bob >= 0),
    descuento_bob numeric(14,2) NOT NULL CHECK (descuento_bob >= 0),
    envio_bob numeric(14,2) NOT NULL CHECK (envio_bob >= 0),
    total_bob numeric(14,2) NOT NULL CHECK (total_bob >= 0),
    tasa_id uuid REFERENCES plataforma.tasas_cambio(id),
    total_usd numeric(14,2),
    vigente_hasta timestamptz NOT NULL,
    aceptada_en timestamptz,
    creada_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, empresa_id),
    UNIQUE (pedido_id, revision),
    FOREIGN KEY (pedido_id, empresa_id) REFERENCES comercial.pedidos_compra(id, empresa_id),
    CHECK (total_bob = subtotal_bob - descuento_bob + envio_bob),
    CHECK (total_usd IS NULL OR total_usd >= 0)
);

CREATE TABLE comercial.metodos_preparados (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    cliente_id uuid NOT NULL,
    proveedor varchar(32) NOT NULL,
    cliente_proveedor_cifrado bytea NOT NULL,
    metodo_proveedor_cifrado bytea NOT NULL,
    preparacion_proveedor_cifrado bytea,
    estado varchar(16) NOT NULL CHECK (estado IN ('LISTO','REVOCADO','PENDIENTE')),
    creado_en timestamptz NOT NULL DEFAULT now(),
    revocado_en timestamptz,
    UNIQUE (id, empresa_id),
    FOREIGN KEY (cliente_id, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id)
);

ALTER TABLE comercial.pedidos_compra
    ADD CONSTRAINT fk_pedido_metodo_empresa FOREIGN KEY (metodo_preparado_id, empresa_id)
    REFERENCES comercial.metodos_preparados(id, empresa_id);

CREATE TABLE comercial.ordenes_pago (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    contexto varchar(12) NOT NULL CHECK (contexto IN ('PEDIDO','CAMBIO','RESERVA','VENTA')),
    pedido_id uuid,
    reserva_id uuid,
    venta_id uuid,
    cambio_id uuid,
    proveedor varchar(32) NOT NULL,
    clave_externa varchar(120) NOT NULL,
    referencia_externa varchar(180),
    estado varchar(32) NOT NULL,
    monto_bob numeric(14,2) NOT NULL CHECK (monto_bob >= 0),
    tasa_id uuid REFERENCES plataforma.tasas_cambio(id),
    monto_usd numeric(14,2),
    centavos_usd bigint,
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    creada_en timestamptz NOT NULL DEFAULT now(),
    actualizada_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, empresa_id),
    UNIQUE (proveedor, clave_externa),
    UNIQUE (proveedor, referencia_externa),
    FOREIGN KEY (pedido_id, empresa_id) REFERENCES comercial.pedidos_compra(id, empresa_id),
    FOREIGN KEY (reserva_id, empresa_id) REFERENCES comercial.reservas(id, empresa_id),
    FOREIGN KEY (venta_id, empresa_id) REFERENCES comercial.ventas(id, empresa_id),
    CHECK (num_nonnulls(pedido_id, reserva_id, venta_id, cambio_id) = 1),
    CHECK ((contexto = 'PEDIDO' AND pedido_id IS NOT NULL) OR
           (contexto = 'CAMBIO' AND cambio_id IS NOT NULL) OR
           (contexto = 'RESERVA' AND reserva_id IS NOT NULL) OR
           (contexto = 'VENTA' AND venta_id IS NOT NULL)),
    CHECK (monto_usd IS NULL OR monto_usd >= 0),
    CHECK (centavos_usd IS NULL OR centavos_usd >= 0)
);

CREATE TABLE comercial.eventos_proveedor (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    orden_pago_id uuid,
    proveedor varchar(32) NOT NULL,
    evento_externo_id varchar(180) NOT NULL,
    tipo varchar(100) NOT NULL,
    payload_hash varchar(64) NOT NULL,
    payload_ref text,
    estado varchar(20) NOT NULL DEFAULT 'RECIBIDO',
    recibido_en timestamptz NOT NULL DEFAULT now(),
    procesado_en timestamptz,
    UNIQUE (proveedor, evento_externo_id),
    FOREIGN KEY (orden_pago_id, empresa_id) REFERENCES comercial.ordenes_pago(id, empresa_id)
);

CREATE TABLE comercial.turnos_caja (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    sucursal_id uuid NOT NULL,
    cajero_id uuid NOT NULL,
    dispositivo_id uuid NOT NULL,
    caja_codigo varchar(80) NOT NULL,
    estado varchar(20) NOT NULL DEFAULT 'ABIERTO' CHECK (estado IN ('ABIERTO','CONCILIACION','CERRADO','RECUPERACION')),
    inicio_en timestamptz NOT NULL,
    vence_en timestamptz NOT NULL,
    version_precios varchar(80) NOT NULL,
    cupos_hash varchar(64) NOT NULL,
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    creado_en timestamptz NOT NULL DEFAULT now(),
    cerrado_en timestamptz,
    UNIQUE (id, empresa_id),
    FOREIGN KEY (sucursal_id, empresa_id) REFERENCES organizacion.sucursales(id, empresa_id),
    FOREIGN KEY (cajero_id, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id),
    CHECK (inicio_en < vence_en)
);

CREATE UNIQUE INDEX uq_turno_caja_dispositivo_abierto ON comercial.turnos_caja (empresa_id, dispositivo_id)
    WHERE estado IN ('ABIERTO','CONCILIACION','RECUPERACION');

CREATE TABLE inventario.cupos_caja (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    turno_id uuid NOT NULL,
    variante_id uuid NOT NULL,
    sucursal_id uuid NOT NULL,
    otorgado integer NOT NULL CHECK (otorgado > 0),
    consumido integer NOT NULL DEFAULT 0 CHECK (consumido >= 0),
    liberado integer NOT NULL DEFAULT 0 CHECK (liberado >= 0),
    precio_autorizado_bob numeric(14,2) NOT NULL CHECK (precio_autorizado_bob >= 0),
    version_precios varchar(80) NOT NULL,
    creado_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, empresa_id),
    UNIQUE (turno_id, variante_id),
    FOREIGN KEY (turno_id, empresa_id) REFERENCES comercial.turnos_caja(id, empresa_id),
    FOREIGN KEY (variante_id, empresa_id) REFERENCES catalogo.variantes_producto(id, empresa_id),
    FOREIGN KEY (sucursal_id, empresa_id) REFERENCES organizacion.sucursales(id, empresa_id),
    CHECK (consumido + liberado <= otorgado)
);

CREATE TABLE inventario.conteos_caja (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    turno_id uuid NOT NULL,
    variante_id uuid NOT NULL,
    cantidad_esperada integer NOT NULL CHECK (cantidad_esperada >= 0),
    cantidad_contada integer NOT NULL CHECK (cantidad_contada >= 0),
    motivo text NOT NULL,
    registrado_por uuid NOT NULL,
    registrado_en timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (turno_id, empresa_id) REFERENCES comercial.turnos_caja(id, empresa_id),
    FOREIGN KEY (variante_id, empresa_id) REFERENCES catalogo.variantes_producto(id, empresa_id),
    FOREIGN KEY (registrado_por, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id)
);

ALTER TABLE comercial.detalles_venta
    ADD CONSTRAINT uq_detalles_venta_id_venta UNIQUE (id, venta_id);

CREATE TABLE comercial.devoluciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    venta_id uuid NOT NULL,
    cliente_id uuid NOT NULL,
    sucursal_id uuid NOT NULL,
    estado varchar(32) NOT NULL DEFAULT 'SOLICITADA',
    motivo_codigo varchar(60) NOT NULL,
    motivo_descripcion text,
    responsabilidad_tienda boolean,
    politica_id uuid,
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    solicitada_en timestamptz NOT NULL DEFAULT now(),
    recibida_en timestamptz,
    inspeccionada_en timestamptz,
    resuelta_en timestamptz,
    UNIQUE (id, empresa_id),
    UNIQUE (id, venta_id),
    FOREIGN KEY (venta_id, empresa_id) REFERENCES comercial.ventas(id, empresa_id),
    FOREIGN KEY (cliente_id, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id),
    FOREIGN KEY (sucursal_id, empresa_id) REFERENCES organizacion.sucursales(id, empresa_id),
    FOREIGN KEY (politica_id, empresa_id) REFERENCES organizacion.politicas_posventa(id, empresa_id)
);

CREATE INDEX ix_devoluciones_venta_estado ON comercial.devoluciones (empresa_id, venta_id, estado);

CREATE TABLE comercial.detalles_devolucion (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    devolucion_id uuid NOT NULL,
    venta_id uuid NOT NULL,
    detalle_venta_id uuid NOT NULL,
    cantidad_solicitada integer NOT NULL CHECK (cantidad_solicitada > 0),
    cantidad_recibida integer NOT NULL DEFAULT 0 CHECK (cantidad_recibida >= 0),
    cantidad_aceptada integer NOT NULL DEFAULT 0 CHECK (cantidad_aceptada >= 0),
    cantidad_rechazada integer NOT NULL DEFAULT 0 CHECK (cantidad_rechazada >= 0),
    condicion_fisica varchar(40),
    responsabilidad_tienda boolean,
    inspeccionado_por uuid,
    evidencia_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (id, empresa_id),
    UNIQUE (devolucion_id, detalle_venta_id),
    FOREIGN KEY (devolucion_id, empresa_id) REFERENCES comercial.devoluciones(id, empresa_id),
    FOREIGN KEY (devolucion_id, venta_id) REFERENCES comercial.devoluciones(id, venta_id),
    FOREIGN KEY (detalle_venta_id, venta_id) REFERENCES comercial.detalles_venta(id, venta_id),
    FOREIGN KEY (inspeccionado_por, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id),
    CHECK (cantidad_recibida <= cantidad_solicitada),
    CHECK (cantidad_aceptada + cantidad_rechazada <= cantidad_recibida)
);

CREATE TABLE comercial.cambios (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    venta_id uuid NOT NULL,
    cliente_id uuid NOT NULL,
    sucursal_id uuid NOT NULL,
    nota_codigo varchar(80) NOT NULL,
    estado varchar(32) NOT NULL DEFAULT 'SOLICITADO',
    motivo_codigo varchar(60) NOT NULL,
    motivo_descripcion text,
    politica_id uuid,
    modalidad_reemplazo varchar(12) CHECK (modalidad_reemplazo IN ('RECOJO','DELIVERY')),
    direccion text,
    valor_reconocido_bob numeric(14,2) NOT NULL DEFAULT 0 CHECK (valor_reconocido_bob >= 0),
    diferencia_bob numeric(14,2) NOT NULL DEFAULT 0,
    vence_espera_en timestamptz,
    oferta_revision integer,
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    creado_en timestamptz NOT NULL DEFAULT now(),
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, empresa_id),
    UNIQUE (id, venta_id),
    UNIQUE (empresa_id, nota_codigo),
    FOREIGN KEY (venta_id, empresa_id) REFERENCES comercial.ventas(id, empresa_id),
    FOREIGN KEY (cliente_id, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id),
    FOREIGN KEY (sucursal_id, empresa_id) REFERENCES organizacion.sucursales(id, empresa_id),
    FOREIGN KEY (politica_id, empresa_id) REFERENCES organizacion.politicas_posventa(id, empresa_id)
);

CREATE TABLE comercial.detalles_cambio (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    cambio_id uuid NOT NULL,
    venta_id uuid NOT NULL,
    tipo_linea varchar(12) NOT NULL CHECK (tipo_linea IN ('ORIGINAL','REEMPLAZO')),
    detalle_venta_id uuid,
    variante_reemplazo_id uuid,
    cantidad integer NOT NULL CHECK (cantidad > 0),
    precio_unitario_bob numeric(14,2),
    estado varchar(30) NOT NULL DEFAULT 'PENDIENTE',
    UNIQUE (id, empresa_id),
    FOREIGN KEY (cambio_id, empresa_id) REFERENCES comercial.cambios(id, empresa_id),
    FOREIGN KEY (cambio_id, venta_id) REFERENCES comercial.cambios(id, venta_id),
    FOREIGN KEY (detalle_venta_id, venta_id) REFERENCES comercial.detalles_venta(id, venta_id),
    FOREIGN KEY (variante_reemplazo_id, empresa_id) REFERENCES catalogo.variantes_producto(id, empresa_id),
    CHECK ((tipo_linea = 'ORIGINAL' AND detalle_venta_id IS NOT NULL AND variante_reemplazo_id IS NULL)
        OR (tipo_linea = 'REEMPLAZO' AND variante_reemplazo_id IS NOT NULL AND detalle_venta_id IS NULL)),
    CHECK (precio_unitario_bob IS NULL OR precio_unitario_bob >= 0)
);

ALTER TABLE comercial.ordenes_pago
    ADD CONSTRAINT fk_orden_cambio_empresa FOREIGN KEY (cambio_id, empresa_id)
    REFERENCES comercial.cambios(id, empresa_id);

CREATE TABLE comercial.movimientos_saldo (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    cliente_id uuid NOT NULL,
    tipo varchar(16) NOT NULL CHECK (tipo IN ('CREDITO','DEBITO','RETENCION','LIBERACION','RESTAURACION')),
    monto_bob numeric(14,2) NOT NULL CHECK (monto_bob > 0),
    origen_tipo varchar(24) NOT NULL,
    origen_id uuid NOT NULL,
    referencia_unica uuid NOT NULL,
    estado varchar(20) NOT NULL DEFAULT 'CONFIRMADO',
    creado_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, empresa_id),
    UNIQUE (empresa_id, referencia_unica, tipo),
    FOREIGN KEY (cliente_id, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id)
);

CREATE INDEX ix_movimientos_saldo_cuenta ON comercial.movimientos_saldo (empresa_id, cliente_id, creado_en, id);

CREATE TABLE comercial.obligaciones_reembolso (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    cliente_id uuid NOT NULL,
    origen_tipo varchar(20) NOT NULL CHECK (origen_tipo IN ('PEDIDO','DEVOLUCION','CAMBIO','VENTA')),
    origen_id uuid NOT NULL,
    motivo_codigo varchar(60) NOT NULL,
    estado varchar(30) NOT NULL DEFAULT 'PENDIENTE_AUTORIZACION',
    monto_bob numeric(14,2) NOT NULL CHECK (monto_bob >= 0),
    politica_id uuid,
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    creada_en timestamptz NOT NULL DEFAULT now(),
    autorizada_en timestamptz,
    completada_en timestamptz,
    UNIQUE (id, empresa_id),
    UNIQUE (empresa_id, origen_tipo, origen_id, motivo_codigo),
    FOREIGN KEY (cliente_id, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id),
    FOREIGN KEY (politica_id, empresa_id) REFERENCES organizacion.politicas_posventa(id, empresa_id)
);

ALTER TABLE comercial.pagos ADD COLUMN empresa_id uuid;

UPDATE comercial.pagos AS p SET empresa_id = COALESCE(
    (SELECT r.empresa_id FROM comercial.reservas AS r WHERE r.id = p.reserva_id),
    (SELECT v.empresa_id FROM comercial.ventas AS v WHERE v.id = p.venta_id)
);

ALTER TABLE comercial.pagos
    ALTER COLUMN empresa_id SET NOT NULL,
    ADD CONSTRAINT fk_pagos_empresa FOREIGN KEY (empresa_id) REFERENCES organizacion.empresas(id),
    ADD CONSTRAINT uq_pagos_id_empresa UNIQUE (id, empresa_id);

CREATE TABLE comercial.componentes_reembolso (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    obligacion_id uuid NOT NULL,
    pago_id uuid,
    medio varchar(20) NOT NULL CHECK (medio IN ('STRIPE','EFECTIVO','SALDO')),
    monto_bob numeric(14,2) NOT NULL CHECK (monto_bob >= 0),
    monto_usd numeric(14,2),
    centavos_usd bigint,
    tasa_bob_por_usd numeric(18,8),
    estado varchar(30) NOT NULL DEFAULT 'PENDIENTE',
    UNIQUE (id, empresa_id),
    UNIQUE (obligacion_id, pago_id, medio),
    FOREIGN KEY (obligacion_id, empresa_id) REFERENCES comercial.obligaciones_reembolso(id, empresa_id),
    FOREIGN KEY (pago_id, empresa_id) REFERENCES comercial.pagos(id, empresa_id),
    CHECK (monto_usd IS NULL OR monto_usd >= 0),
    CHECK (centavos_usd IS NULL OR centavos_usd >= 0)
);

CREATE TABLE comercial.ejecuciones_reembolso (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    componente_id uuid NOT NULL,
    clave_ejecucion uuid NOT NULL,
    proveedor varchar(32),
    referencia_externa varchar(180),
    estado varchar(30) NOT NULL DEFAULT 'EN_PROCESO',
    intento integer NOT NULL DEFAULT 1 CHECK (intento > 0),
    creada_en timestamptz NOT NULL DEFAULT now(),
    resuelta_en timestamptz,
    UNIQUE (id, empresa_id),
    UNIQUE (empresa_id, clave_ejecucion),
    UNIQUE (proveedor, referencia_externa),
    FOREIGN KEY (componente_id, empresa_id) REFERENCES comercial.componentes_reembolso(id, empresa_id)
);

CREATE TABLE comercial.eventos_outbox (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    recurso_tipo varchar(50) NOT NULL,
    recurso_id uuid NOT NULL,
    transicion varchar(60) NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    dispositivo_id uuid,
    payload jsonb NOT NULL,
    estado varchar(20) NOT NULL DEFAULT 'PENDIENTE',
    intentos integer NOT NULL DEFAULT 0 CHECK (intentos >= 0),
    proximo_intento_en timestamptz,
    creado_en timestamptz NOT NULL DEFAULT now(),
    entregado_en timestamptz,
    UNIQUE (id, empresa_id),
    UNIQUE NULLS NOT DISTINCT (empresa_id, recurso_tipo, recurso_id, transicion, revision, dispositivo_id)
);

CREATE INDEX ix_outbox_pendiente ON comercial.eventos_outbox (estado, proximo_intento_en)
    WHERE estado IN ('PENDIENTE','REINTENTO');

CREATE TABLE comercial.notificaciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    usuario_id uuid NOT NULL,
    outbox_id uuid,
    tipo varchar(50) NOT NULL,
    titulo varchar(180) NOT NULL,
    cuerpo text NOT NULL,
    recurso_tipo varchar(50),
    recurso_id uuid,
    creada_en timestamptz NOT NULL DEFAULT now(),
    leida_en timestamptz,
    UNIQUE (id, empresa_id),
    UNIQUE NULLS NOT DISTINCT (empresa_id, usuario_id, outbox_id),
    FOREIGN KEY (usuario_id, empresa_id) REFERENCES seguridad.usuarios(id, empresa_id),
    FOREIGN KEY (outbox_id, empresa_id) REFERENCES comercial.eventos_outbox(id, empresa_id)
);

CREATE INDEX ix_notificaciones_bandeja ON comercial.notificaciones (empresa_id, usuario_id, creada_en DESC, id);

CREATE TABLE comercial.comprobantes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    tipo varchar(40) NOT NULL,
    recurso_tipo varchar(40) NOT NULL,
    recurso_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    documento jsonb NOT NULL,
    documento_hash varchar(64) NOT NULL,
    uri_archivo text,
    creado_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, empresa_id),
    UNIQUE (empresa_id, recurso_tipo, recurso_id, tipo, version)
);

CREATE TABLE inteligencia.modelos_ml (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
    tipo varchar(30) NOT NULL CHECK (tipo IN ('PRONOSTICO','AGRUPACION')),
    version integer NOT NULL CHECK (version > 0),
    origen_datos varchar(12) NOT NULL CHECK (origen_datos IN ('REAL','SINTETICO')),
    semilla bigint,
    dataset_version varchar(100) NOT NULL,
    dataset_hash varchar(64) NOT NULL,
    metricas jsonb NOT NULL,
    artefacto_uri text NOT NULL,
    artefacto_hash varchar(64) NOT NULL,
    resultado_uri text NOT NULL,
    resultado_hash varchar(64) NOT NULL,
    esquema_resultado_version integer NOT NULL DEFAULT 1 CHECK (esquema_resultado_version > 0),
    creado_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, empresa_id),
    UNIQUE (empresa_id, tipo, version),
    CHECK (origen_datos <> 'SINTETICO' OR semilla IS NOT NULL)
);

-- Ampliaciones de agregados existentes sin pérdida de IDs ni filas.
ALTER TABLE comercial.operaciones_sincronizacion
    DROP CONSTRAINT ck_operaciones_estado;

ALTER TABLE comercial.operaciones_sincronizacion
    ADD CONSTRAINT ck_operaciones_estado CHECK (estado IN (
        'ACEPTADA','RECHAZADA','REQUIERE_ACEPTACION_PRECIO','PENDIENTE_PAGO',
        'REGISTRADA_CENTRAL','CONCILIACION_REQUERIDA','CONFLICTO',
        'PAGADO_PENDIENTE_ASIGNACION','CONFIRMADO','REEMBOLSO_PENDIENTE',
        'REEMBOLSADO','PENDIENTE_INTERVENCION','REQUIERE_NUEVA_ACEPTACION',
        'REQUIERE_ACCION_CLIENTE','CANCELACION_EN_CONCILIACION','CANCELADA')),
    ADD CONSTRAINT ck_operaciones_tipo_version CHECK (
        (tipo = 'SOLICITAR_RESERVA' AND version_esquema = 1) OR
        (tipo = 'REGISTRAR_VENTA_CAJA' AND version_esquema = 1) OR
        (tipo = 'SOLICITAR_COMPRA' AND version_esquema IN (1,2,3)));

ALTER TABLE inventario.inventario_sucursal
    ADD COLUMN comprometido_caja integer NOT NULL DEFAULT 0 CHECK (comprometido_caja >= 0),
    ADD COLUMN comprometido_digital integer NOT NULL DEFAULT 0 CHECK (comprometido_digital >= 0),
    ADD COLUMN comprometido_cambio integer NOT NULL DEFAULT 0 CHECK (comprometido_cambio >= 0);

ALTER TABLE comercial.ventas
    ADD COLUMN pedido_compra_id uuid,
    ADD COLUMN turno_caja_id uuid,
    ADD COLUMN vendida_local_en timestamptz,
    ADD COLUMN recibida_central_en timestamptz,
    ADD COLUMN entregada_en timestamptz;

ALTER TABLE comercial.ventas
    ADD CONSTRAINT fk_ventas_pedido_empresa FOREIGN KEY (pedido_compra_id, empresa_id)
        REFERENCES comercial.pedidos_compra(id, empresa_id),
    ADD CONSTRAINT fk_ventas_turno_empresa FOREIGN KEY (turno_caja_id, empresa_id)
        REFERENCES comercial.turnos_caja(id, empresa_id);

CREATE UNIQUE INDEX uq_ventas_pedido ON comercial.ventas (empresa_id, pedido_compra_id)
    WHERE pedido_compra_id IS NOT NULL;

ALTER TABLE comercial.pagos
    ADD COLUMN pedido_compra_id uuid,
    ADD COLUMN cambio_id uuid,
    ADD COLUMN orden_pago_id uuid,
    ADD COLUMN tasa_id uuid,
    ADD COLUMN monto_usd numeric(14,2),
    ADD COLUMN centavos_usd bigint,
    ADD COLUMN efectivo_recibido_bob numeric(14,2),
    ADD COLUMN cambio_entregado_bob numeric(14,2),
    ADD COLUMN origen_legado boolean NOT NULL DEFAULT false;

UPDATE comercial.pagos SET origen_legado = true;

ALTER TABLE comercial.pagos
    DROP CONSTRAINT pagos_contexto_check,
    DROP CONSTRAINT ck_pagos_contexto_referencia,
    DROP CONSTRAINT ck_pagos_un_solo_recurso;

ALTER TABLE comercial.pagos
    ADD CONSTRAINT ck_pagos_contexto_final CHECK (contexto IN ('PEDIDO','CAMBIO','RESERVA','VENTA')),
    ADD CONSTRAINT ck_pagos_un_origen_final CHECK (
        num_nonnulls(reserva_id, venta_id, pedido_compra_id, cambio_id) = 1 AND
        ((contexto = 'RESERVA' AND reserva_id IS NOT NULL) OR
         (contexto = 'VENTA' AND venta_id IS NOT NULL) OR
         (contexto = 'PEDIDO' AND pedido_compra_id IS NOT NULL) OR
         (contexto = 'CAMBIO' AND cambio_id IS NOT NULL))),
    ADD CONSTRAINT ck_pagos_importes_final CHECK (
        (monto_usd IS NULL OR monto_usd >= 0) AND
        (centavos_usd IS NULL OR centavos_usd >= 0) AND
        (efectivo_recibido_bob IS NULL OR efectivo_recibido_bob >= 0) AND
        (cambio_entregado_bob IS NULL OR cambio_entregado_bob >= 0)),
    ADD CONSTRAINT fk_pagos_pedido_empresa FOREIGN KEY (pedido_compra_id, empresa_id)
        REFERENCES comercial.pedidos_compra(id, empresa_id),
    ADD CONSTRAINT fk_pagos_cambio_empresa FOREIGN KEY (cambio_id, empresa_id)
        REFERENCES comercial.cambios(id, empresa_id),
    ADD CONSTRAINT fk_pagos_orden_empresa FOREIGN KEY (orden_pago_id, empresa_id)
        REFERENCES comercial.ordenes_pago(id, empresa_id),
    ADD CONSTRAINT fk_pagos_tasa FOREIGN KEY (tasa_id)
        REFERENCES plataforma.tasas_cambio(id);

DROP TRIGGER tg_comercial_pedidos_entrega_ambito ON comercial.pedidos_entrega;

ALTER TABLE comercial.pedidos_entrega
    ADD COLUMN empresa_id uuid;

UPDATE comercial.pedidos_entrega AS e SET empresa_id =
    (SELECT v.empresa_id FROM comercial.ventas AS v WHERE v.id = e.venta_id);

ALTER TABLE comercial.pedidos_entrega
    ALTER COLUMN empresa_id SET NOT NULL,
    ADD CONSTRAINT fk_pedidos_entrega_empresa FOREIGN KEY (empresa_id) REFERENCES organizacion.empresas(id),
    ADD CONSTRAINT uq_pedidos_entrega_id_empresa UNIQUE (id, empresa_id),
    ADD CONSTRAINT fk_entrega_venta_empresa FOREIGN KEY (venta_id, empresa_id)
        REFERENCES comercial.ventas(id, empresa_id),
    ADD CONSTRAINT fk_entrega_sucursal_empresa FOREIGN KEY (sucursal_id, empresa_id)
        REFERENCES organizacion.sucursales(id, empresa_id),
    ADD CONSTRAINT fk_entrega_cliente_empresa FOREIGN KEY (cliente_id, empresa_id)
        REFERENCES seguridad.usuarios(id, empresa_id);

ALTER TABLE comercial.pedidos_entrega
    ALTER COLUMN venta_id DROP NOT NULL,
    ADD COLUMN cambio_id uuid;

ALTER TABLE comercial.pedidos_entrega
    ADD CONSTRAINT ck_entrega_un_origen CHECK (num_nonnulls(venta_id, cambio_id) = 1),
    ADD CONSTRAINT fk_entrega_cambio_empresa FOREIGN KEY (cambio_id, empresa_id)
        REFERENCES comercial.cambios(id, empresa_id);

CREATE UNIQUE INDEX uq_entrega_cambio ON comercial.pedidos_entrega (empresa_id, cambio_id)
    WHERE cambio_id IS NOT NULL;

ALTER TABLE inteligencia.solicitudes_ia
    ADD COLUMN filtros_autorizados jsonb,
    ADD COLUMN snapshot_uri text,
    ADD COLUMN snapshot_hash varchar(64),
    ADD COLUMN exportacion_uri text,
    ADD COLUMN estado varchar(30),
    ADD COLUMN revision integer NOT NULL DEFAULT 1 CHECK (revision > 0);
