"""Ciclo 3 backend — tablas digitales, promociones, entregas e IA.

Crea, en orden (plan 01-plan-datos-infra-ciclo3.md):
  1. Tipo comercial.estado_entrega
  2. comercial.carritos -> 3. comercial.detalles_carrito
  4. comercial.pedidos_entrega
  5. catalogo.promociones -> 6. catalogo.promocion_variante
  7. inteligencia.historial_navegacion -> 8. inteligencia.solicitudes_ia
  9. comercial.registros_idempotencia (idempotencia genérica CU14/CU17)
  + columnas auxiliares: ventas.expira_en, detalles_venta.promocion_id
  + unicidad parcial Stripe (referencia_externa) e índices de consulta.

Idempotente (guardas IF NOT EXISTS). No toca datos de Ciclos 1-2.
NOTA asyncpg: una sola sentencia por op.execute (sin multi-statement).

Revision ID: 0004_ciclo3_backend
Revises: 0003_ciclo2_linea_invariante
"""
from alembic import op

revision = "0004_ciclo3_backend"
down_revision = "0003_ciclo2_linea_invariante"
branch_labels = None
depends_on = None

_TIPO_ENTREGA = (
    "DO $$ BEGIN "
    "IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
    "WHERE n.nspname = 'comercial' AND t.typname = 'estado_entrega') THEN "
    "CREATE TYPE comercial.estado_entrega AS ENUM "
    "('SOLICITADO','PREPARADO','LISTO_RECOJO','EN_REPARTO','RECOGIDO','ENTREGADO','CANCELADO'); "
    "END IF; END $$;"
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS inteligencia")
    op.execute(_TIPO_ENTREGA)

    # 2. comercial.carritos (un ACTIVO por cliente+canal vía índice parcial).
    op.execute(
        "CREATE TABLE IF NOT EXISTS comercial.carritos ("
        "id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "cliente_id uuid NOT NULL REFERENCES seguridad.clientes(usuario_id),"
        "canal varchar(10) NOT NULL DEFAULT 'WEB' CHECK (canal IN ('WEB','MOVIL')),"
        "estado varchar(20) NOT NULL DEFAULT 'ACTIVO' "
        "CHECK (estado IN ('ACTIVO','CONVERTIDO','ABANDONADO')),"
        "creada_en timestamptz NOT NULL DEFAULT now(),"
        "actualizada_en timestamptz NOT NULL DEFAULT now(),"
        "convertida_en timestamptz,"
        "venta_id uuid REFERENCES comercial.ventas(id))"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_carritos_activo_por_cliente_canal "
        "ON comercial.carritos (cliente_id, canal) WHERE estado = 'ACTIVO'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_carritos_cliente_estado "
        "ON comercial.carritos (cliente_id, estado)"
    )

    # 3. comercial.detalles_carrito (una variante por carrito).
    op.execute(
        "CREATE TABLE IF NOT EXISTS comercial.detalles_carrito ("
        "id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "carrito_id uuid NOT NULL REFERENCES comercial.carritos(id) ON DELETE CASCADE,"
        "variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),"
        "cantidad integer NOT NULL CHECK (cantidad > 0),"
        "agregado_en timestamptz NOT NULL DEFAULT now(),"
        "actualizado_en timestamptz NOT NULL DEFAULT now(),"
        "CONSTRAINT uq_detalle_carrito_carrito_variante UNIQUE (carrito_id, variante_id))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_detalle_carrito_carrito "
        "ON comercial.detalles_carrito (carrito_id)"
    )

    # 4. comercial.pedidos_entrega (1:1 con venta digital, snapshots congelados).
    op.execute(
        "CREATE TABLE IF NOT EXISTS comercial.pedidos_entrega ("
        "id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "venta_id uuid NOT NULL UNIQUE REFERENCES comercial.ventas(id) ON DELETE CASCADE,"
        "sucursal_id uuid NOT NULL REFERENCES organizacion.sucursales(id),"
        "cliente_id uuid NOT NULL REFERENCES seguridad.clientes(usuario_id),"
        "modalidad varchar(20) NOT NULL CHECK (modalidad IN ('RECOJO','DELIVERY')),"
        "estado varchar(20) NOT NULL DEFAULT 'SOLICITADO' CHECK (estado IN "
        "('SOLICITADO','PREPARADO','LISTO_RECOJO','EN_REPARTO','RECOGIDO','ENTREGADO','CANCELADO')),"
        "anillo_sucursal smallint, anillo_destino smallint,"
        "anillo_minimo smallint, anillo_maximo smallint, direccion text,"
        "tarifa_base numeric(12,2) NOT NULL DEFAULT 0 CHECK (tarifa_base >= 0),"
        "incremento_anillo numeric(12,2) NOT NULL DEFAULT 0 CHECK (incremento_anillo >= 0),"
        "costo_entrega numeric(12,2) NOT NULL DEFAULT 0 CHECK (costo_entrega >= 0),"
        "codigo_recojo varchar(20),"
        "creada_en timestamptz NOT NULL DEFAULT now(),"
        "actualizada_en timestamptz NOT NULL DEFAULT now(),"
        "CONSTRAINT ck_pedidos_delivery_requiere_datos CHECK "
        "((modalidad = 'RECOJO') OR (direccion IS NOT NULL AND anillo_destino IS NOT NULL)),"
        "CONSTRAINT ck_pedidos_recojo_sin_tarifa CHECK "
        "((modalidad = 'DELIVERY') OR (costo_entrega = 0)))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pedidos_sucursal_estado "
        "ON comercial.pedidos_entrega (sucursal_id, estado)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pedidos_venta ON comercial.pedidos_entrega (venta_id)"
    )

    # 5. catalogo.promociones.
    op.execute(
        "CREATE TABLE IF NOT EXISTS catalogo.promociones ("
        "id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "codigo varchar(40) NOT NULL UNIQUE, nombre varchar(180) NOT NULL, descripcion text,"
        "tipo varchar(20) NOT NULL CHECK (tipo IN ('PORCENTAJE','MONTO_FIJO')),"
        "valor numeric(12,2) NOT NULL CHECK (valor >= 0),"
        "activa boolean NOT NULL DEFAULT true,"
        "vigencia_inicio timestamptz, vigencia_fin timestamptz,"
        "creada_en timestamptz NOT NULL DEFAULT now(),"
        "actualizada_en timestamptz NOT NULL DEFAULT now(),"
        "creada_por uuid REFERENCES seguridad.usuarios(id),"
        "CONSTRAINT ck_promociones_porcentaje_max CHECK ((tipo <> 'PORCENTAJE') OR (valor <= 100)),"
        "CONSTRAINT ck_promociones_vigencia_coherente CHECK "
        "(vigencia_fin IS NULL OR vigencia_inicio IS NULL OR vigencia_inicio <= vigencia_fin))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_promociones_vigencia "
        "ON catalogo.promociones (activa, vigencia_inicio, vigencia_fin)"
    )

    # 6. catalogo.promocion_variante.
    op.execute(
        "CREATE TABLE IF NOT EXISTS catalogo.promocion_variante ("
        "promocion_id uuid NOT NULL REFERENCES catalogo.promociones(id) ON DELETE CASCADE,"
        "variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id) ON DELETE CASCADE,"
        "creada_en timestamptz NOT NULL DEFAULT now(),"
        "PRIMARY KEY (promocion_id, variante_id))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_promocion_variante_variante "
        "ON catalogo.promocion_variante (variante_id)"
    )

    # 7. inteligencia.historial_navegacion (auditoría sanitizada).
    op.execute(
        "CREATE TABLE IF NOT EXISTS inteligencia.historial_navegacion ("
        "id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "cliente_id uuid REFERENCES seguridad.clientes(usuario_id),"
        "usuario_id uuid REFERENCES seguridad.usuarios(id),"
        "variante_id uuid REFERENCES catalogo.variantes_producto(id),"
        "producto_id uuid REFERENCES catalogo.productos(id),"
        "evento varchar(40) NOT NULL,"
        "metadatos jsonb NOT NULL DEFAULT '{}'::jsonb,"
        "creada_en timestamptz NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_navegacion_cliente_fecha "
        "ON inteligencia.historial_navegacion (cliente_id, creada_en DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_navegacion_evento "
        "ON inteligencia.historial_navegacion (evento)"
    )

    # 8. inteligencia.solicitudes_ia (respuesta y datos embebidos).
    op.execute(
        "CREATE TABLE IF NOT EXISTS inteligencia.solicitudes_ia ("
        "id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "usuario_id uuid REFERENCES seguridad.usuarios(id),"
        "cliente_id uuid REFERENCES seguridad.clientes(usuario_id),"
        "tipo varchar(30) NOT NULL CHECK (tipo IN "
        "('RECOMENDACION','BUSQUEDA_VOZ','REPORTE','DECISION_INVENTARIO')),"
        "entrada text NOT NULL DEFAULT '', funcion_usada varchar(60),"
        "parametros jsonb NOT NULL DEFAULT '{}'::jsonb,"
        "respuesta text NOT NULL DEFAULT '', datos jsonb NOT NULL DEFAULT '{}'::jsonb,"
        "proveedor varchar(20) NOT NULL DEFAULT 'DETERMINISTA',"
        "latencia_ms integer NOT NULL DEFAULT 0 CHECK (latencia_ms >= 0),"
        "creada_en timestamptz NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_solicitudes_tipo_fecha "
        "ON inteligencia.solicitudes_ia (tipo, creada_en DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_solicitudes_usuario "
        "ON inteligencia.solicitudes_ia (usuario_id)"
    )

    # 9. comercial.registros_idempotencia (CU14 líneas, CU17 autorizaciones).
    op.execute(
        "CREATE TABLE IF NOT EXISTS comercial.registros_idempotencia ("
        "clave uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "hash_solicitud text NOT NULL, recurso_tipo varchar(40) NOT NULL,"
        "recurso_id uuid, respuesta jsonb NOT NULL DEFAULT '{}'::jsonb,"
        "creada_en timestamptz NOT NULL DEFAULT now(), expira_en timestamptz)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_idempotencia_expira "
        "ON comercial.registros_idempotencia (expira_en)"
    )

    # Columnas auxiliares en tablas de Ciclo 2 (decisiones aprobadas).
    op.execute("ALTER TABLE comercial.ventas ADD COLUMN IF NOT EXISTS expira_en timestamptz")
    op.execute(
        "ALTER TABLE comercial.detalles_venta ADD COLUMN IF NOT EXISTS promocion_id uuid "
        "REFERENCES catalogo.promociones(id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ventas_estado_expira "
        "ON comercial.ventas (estado, expira_en)"
    )
    # Referencia Stripe única cuando exista (pagos ya permiten STRIPE_TEST).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_pagos_referencia_externa "
        "ON comercial.pagos (referencia_externa) WHERE referencia_externa IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS comercial.uq_pagos_referencia_externa")
    op.execute("DROP INDEX IF EXISTS comercial.idx_ventas_estado_expira")
    op.execute("ALTER TABLE comercial.detalles_venta DROP COLUMN IF EXISTS promocion_id")
    op.execute("ALTER TABLE comercial.ventas DROP COLUMN IF EXISTS expira_en")
    op.execute("DROP TABLE IF EXISTS comercial.registros_idempotencia")
    op.execute("DROP TABLE IF EXISTS inteligencia.solicitudes_ia")
    op.execute("DROP TABLE IF EXISTS inteligencia.historial_navegacion")
    op.execute("DROP TABLE IF EXISTS catalogo.promocion_variante")
    op.execute("DROP TABLE IF EXISTS catalogo.promociones")
    op.execute("DROP TABLE IF EXISTS comercial.pedidos_entrega")
    op.execute("DROP TABLE IF EXISTS comercial.detalles_carrito")
    op.execute("DROP TABLE IF EXISTS comercial.carritos")
    op.execute("DROP TYPE IF EXISTS comercial.estado_entrega")
