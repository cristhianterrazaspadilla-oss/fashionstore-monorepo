"""Ciclo 2 Entrega 1 — infraestructura: enums, tablas comercial/traslados,
columnas de idempotencia y adelanto, unicidad Kardex e indices.

Alineada con docu_general/fashionstore-base-datos-final.sql (banner CICLO 2)
mas los agregados exigidos por el skill y el plan:
  - clave_idempotencia / hash_solicitud en reservas, traslados, ventas, pagos
  - snapshot de adelanto en reservas; politica de adelanto en sucursales
  - cantidades + estado por linea en detalles_reserva
  - enlace detalle_traslado/detalle_venta -> detalle_reserva
  - unicidad Kardex por efecto logico
Aplicable sobre una base con Ciclo 1 y re-ejecutable (guardas IF NOT EXISTS).
No crea tablas de Ciclo 3.

Revision ID: 0001_ciclo2_entrega1
Revises:
Create Date: 2026-09-14
"""
from alembic import op

revision = "0001_ciclo2_entrega1"
down_revision = None
branch_labels = None
depends_on = None


def _agregar_constraint_si_falta(nombre: str, tabla_esquema: str, definicion: str) -> None:
    """Agrega un CHECK solo si no existe (bases creadas por SQL Ciclo 1 ya los tienen)."""
    esquema, tabla = tabla_esquema.split(".")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{nombre}'
            ) THEN
                ALTER TABLE {esquema}.{tabla} ADD CONSTRAINT {nombre} {definicion};
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS comercial")

    # 1. Tipos (orden exigido por el skill)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                           WHERE n.nspname = 'comercial' AND t.typname = 'estado_reserva') THEN
                CREATE TYPE comercial.estado_reserva AS ENUM
                ('PENDIENTE_TRASLADO','PENDIENTE','PREPARADA','ATENDIDA','COMPLETADA','CANCELADA','VENCIDA');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                           WHERE n.nspname = 'inventario' AND t.typname = 'estado_traslado') THEN
                CREATE TYPE inventario.estado_traslado AS ENUM
                ('SOLICITADO','APROBADO','RECHAZADO','DESPACHADO','RECIBIDO','CANCELADO');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                           WHERE n.nspname = 'comercial' AND t.typname = 'estado_venta') THEN
                CREATE TYPE comercial.estado_venta AS ENUM
                ('PENDIENTE_PAGO','PAGADA','CANCELADA','PARCIALMENTE_DEVUELTA','DEVUELTA');
            END IF;
        END
        $$;
        """
    )

    # 2. comercial.reservas (+ idempotencia y snapshot de adelanto)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS comercial.reservas (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          cliente_id uuid NOT NULL REFERENCES seguridad.clientes(usuario_id),
          sucursal_destino_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
          codigo varchar(50) NOT NULL UNIQUE,
          estado comercial.estado_reserva NOT NULL DEFAULT 'PENDIENTE',
          fecha_creacion timestamptz NOT NULL DEFAULT now(),
          fecha_visita timestamptz,
          vence_en timestamptz NOT NULL,
          observacion text,
          adelanto_modalidad varchar(20),
          adelanto_valor numeric(12,2),
          adelanto_monto numeric(12,2),
          clave_idempotencia uuid UNIQUE,
          hash_solicitud text,
          CONSTRAINT ck_reservas_codigo_formato CHECK (codigo LIKE 'FS-%')
        );
        """
    )

    # 3. comercial.detalles_reserva (+ cantidades y estado por linea)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS comercial.detalles_reserva (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          reserva_id uuid NOT NULL REFERENCES comercial.reservas(id) ON DELETE CASCADE,
          variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),
          cantidad_solicitada integer NOT NULL CHECK (cantidad_solicitada > 0),
          cantidad_reservada integer NOT NULL DEFAULT 0 CHECK (cantidad_reservada >= 0),
          cantidad_pendiente_traslado integer NOT NULL DEFAULT 0 CHECK (cantidad_pendiente_traslado >= 0),
          cantidad_vendida integer NOT NULL DEFAULT 0 CHECK (cantidad_vendida >= 0),
          cantidad_liberada integer NOT NULL DEFAULT 0 CHECK (cantidad_liberada >= 0),
          estado_linea varchar(30) NOT NULL DEFAULT 'RESERVADA'
            CHECK (estado_linea IN ('PENDIENTE_TRASLADO','RESERVADA','RECHAZADA','VENDIDA_PARCIAL','VENDIDA','LIBERADA')),
          CONSTRAINT uq_detalles_reserva_reserva_variante UNIQUE (reserva_id, variante_id),
          CONSTRAINT ck_detalle_reserva_cantidades_consistentes CHECK
            (cantidad_reservada + cantidad_pendiente_traslado + cantidad_vendida + cantidad_liberada <= cantidad_solicitada)
        );
        """
    )

    # 4. inventario.traslados (+ idempotencia)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS inventario.traslados (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          reserva_id uuid REFERENCES comercial.reservas(id),
          sucursal_origen_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
          sucursal_destino_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
          estado inventario.estado_traslado NOT NULL DEFAULT 'SOLICITADO',
          solicitado_por_id uuid NOT NULL REFERENCES seguridad.usuarios(id),
          aprobado_por_id uuid REFERENCES seguridad.usuarios(id),
          fecha_solicitud timestamptz NOT NULL DEFAULT now(),
          fecha_aprobacion timestamptz,
          fecha_despacho timestamptz,
          fecha_recepcion timestamptz,
          motivo_rechazo text,
          clave_idempotencia uuid UNIQUE,
          hash_solicitud text,
          CONSTRAINT ck_traslados_origen_destino_distintos CHECK (sucursal_origen_id <> sucursal_destino_id)
        );
        """
    )

    # 5. inventario.detalles_traslado (+ enlace a linea de reserva)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS inventario.detalles_traslado (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          traslado_id uuid NOT NULL REFERENCES inventario.traslados(id) ON DELETE CASCADE,
          detalle_reserva_id uuid REFERENCES comercial.detalles_reserva(id),
          variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),
          cantidad integer NOT NULL CHECK (cantidad > 0),
          CONSTRAINT uq_detalles_traslado_traslado_variante UNIQUE (traslado_id, variante_id)
        );
        """
    )

    # 6. comercial.ventas (+ idempotencia; canal/estado/costo_entrega listos p. Ciclo 3)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS comercial.ventas (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          numero varchar(50) NOT NULL UNIQUE,
          cliente_id uuid REFERENCES seguridad.clientes(usuario_id),
          reserva_id uuid REFERENCES comercial.reservas(id),
          sucursal_id uuid NOT NULL REFERENCES organizacion.sucursales(id),
          cajero_id uuid REFERENCES seguridad.usuarios(id),
          canal varchar(20) NOT NULL DEFAULT 'PRESENCIAL'
            CHECK (canal IN ('PRESENCIAL','WEB','MOVIL')),
          estado comercial.estado_venta NOT NULL DEFAULT 'PENDIENTE_PAGO',
          subtotal numeric(12,2) NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
          descuento numeric(12,2) NOT NULL DEFAULT 0 CHECK (descuento >= 0),
          costo_entrega numeric(12,2) NOT NULL DEFAULT 0 CHECK (costo_entrega >= 0),
          total numeric(12,2) NOT NULL DEFAULT 0 CHECK (total >= 0),
          creada_en timestamptz NOT NULL DEFAULT now(),
          confirmada_en timestamptz,
          clave_idempotencia uuid UNIQUE,
          hash_solicitud text
        );
        """
    )

    # 7. comercial.detalles_venta (+ costo congelado y enlace a linea de reserva)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS comercial.detalles_venta (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          venta_id uuid NOT NULL REFERENCES comercial.ventas(id) ON DELETE CASCADE,
          detalle_reserva_id uuid REFERENCES comercial.detalles_reserva(id),
          variante_id uuid NOT NULL REFERENCES catalogo.variantes_producto(id),
          cantidad integer NOT NULL CHECK (cantidad > 0),
          precio_unitario numeric(12,2) NOT NULL CHECK (precio_unitario >= 0),
          descuento numeric(12,2) NOT NULL DEFAULT 0 CHECK (descuento >= 0),
          costo_promedio numeric(12,2) NOT NULL DEFAULT 0 CHECK (costo_promedio >= 0),
          CONSTRAINT uq_detalles_venta_venta_variante UNIQUE (venta_id, variante_id)
        );
        """
    )

    # 8. comercial.pagos unificada (+ idempotencia; STRIPE_TEST/referencia listos p. Ciclo 3)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS comercial.pagos (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          contexto varchar(20) NOT NULL CHECK (contexto IN ('RESERVA','VENTA')),
          reserva_id uuid REFERENCES comercial.reservas(id),
          venta_id uuid REFERENCES comercial.ventas(id),
          metodo varchar(30) NOT NULL
            CHECK (metodo IN ('EFECTIVO','TARJETA_CAJA','QR_CAJA','TRANSFERENCIA','STRIPE_TEST')),
          tipo_pago varchar(20) CHECK (tipo_pago IN ('ADELANTO','TOTAL','PAGO')),
          modalidad_adelanto varchar(20) CHECK (modalidad_adelanto IN ('MONTO_FIJO','PORCENTAJE')),
          monto numeric(12,2) NOT NULL CHECK (monto > 0),
          no_reembolsable boolean NOT NULL DEFAULT false,
          estado varchar(20) NOT NULL DEFAULT 'PENDIENTE'
            CHECK (estado IN ('PENDIENTE','APROBADO','RECHAZADO','ANULADO')),
          referencia_externa varchar(160),
          proveedor_pago varchar(40),
          pagado_en timestamptz,
          clave_idempotencia uuid UNIQUE,
          hash_solicitud text,
          CONSTRAINT ck_pagos_contexto_referencia CHECK
            ((contexto = 'RESERVA' AND reserva_id IS NOT NULL) OR
             (contexto = 'VENTA' AND venta_id IS NOT NULL))
        );
        """
    )

    # 9. movimientos_inventario: idempotencia + unicidad por efecto logico
    op.execute("ALTER TABLE inventario.movimientos_inventario ADD COLUMN IF NOT EXISTS clave_idempotencia uuid")
    op.execute("ALTER TABLE inventario.movimientos_inventario ADD COLUMN IF NOT EXISTS linea_referencia_id uuid")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_movimientos_clave_idempotencia "
        "ON inventario.movimientos_inventario (clave_idempotencia)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_movimientos_efecto_logico
        ON inventario.movimientos_inventario (
          referencia_tipo, referencia_id, tipo, variante_id,
          COALESCE(sucursal_origen_id, '00000000-0000-0000-0000-000000000000'::uuid),
          COALESCE(sucursal_destino_id, '00000000-0000-0000-0000-000000000000'::uuid),
          COALESCE(linea_referencia_id, '00000000-0000-0000-0000-000000000000'::uuid)
        )
        WHERE referencia_tipo IS NOT NULL AND referencia_id IS NOT NULL
        """
    )

    # 10. organizacion.sucursales: politica de adelanto por sucursal
    op.execute("ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS adelanto_activo boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS modalidad_adelanto varchar(20)")
    op.execute("ALTER TABLE organizacion.sucursales ADD COLUMN IF NOT EXISTS valor_adelanto numeric(12,2) NOT NULL DEFAULT 0")
    _agregar_constraint_si_falta(
        "ck_sucursales_modalidad_adelanto", "organizacion.sucursales",
        "CHECK (modalidad_adelanto IS NULL OR modalidad_adelanto IN ('MONTO_FIJO','PORCENTAJE'))",
    )
    _agregar_constraint_si_falta(
        "ck_sucursales_valor_adelanto_nneg", "organizacion.sucursales",
        "CHECK (valor_adelanto >= 0)",
    )
    _agregar_constraint_si_falta(
        "ck_sucursales_adelanto_porcentaje_max", "organizacion.sucursales",
        "CHECK (modalidad_adelanto IS NULL OR modalidad_adelanto <> 'PORCENTAJE' OR valor_adelanto <= 100)",
    )
    _agregar_constraint_si_falta(
        "ck_sucursales_adelanto_coherente", "organizacion.sucursales",
        "CHECK ((adelanto_activo = FALSE) OR (modalidad_adelanto IS NOT NULL AND valor_adelanto > 0))",
    )

    # 11. CHECKs no negativos en inventario existente (ya existen si vino del SQL Ciclo 1)
    _agregar_constraint_si_falta(
        "ck_inventario_disponible_nneg", "inventario.inventario_sucursal",
        "CHECK (disponible >= 0)",
    )
    _agregar_constraint_si_falta(
        "ck_inventario_reservado_nneg", "inventario.inventario_sucursal",
        "CHECK (reservado >= 0)",
    )
    _agregar_constraint_si_falta(
        "ck_inventario_comprometido_nneg", "inventario.inventario_sucursal",
        "CHECK (comprometido_traslado >= 0)",
    )
    _agregar_constraint_si_falta(
        "ck_inventario_en_transito_nneg", "inventario.inventario_sucursal",
        "CHECK (en_transito >= 0)",
    )

    # 12. Indices de consulta (estado, vencimiento, sucursal, cliente, fecha)
    op.execute("CREATE INDEX IF NOT EXISTS idx_reserva_estado_vencimiento ON comercial.reservas (estado, vence_en)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reservas_cliente ON comercial.reservas (cliente_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reservas_sucursal ON comercial.reservas (sucursal_destino_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_detalle_reserva_reserva ON comercial.detalles_reserva (reserva_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_traslado_estado ON inventario.traslados (estado, fecha_solicitud)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_traslados_reserva ON inventario.traslados (reserva_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ventas_sucursal_fecha ON comercial.ventas (sucursal_id, creada_en DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON comercial.ventas (cliente_id, creada_en DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pagos_reserva ON comercial.pagos (contexto, reserva_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pagos_venta ON comercial.pagos (contexto, venta_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS comercial.pagos")
    op.execute("DROP TABLE IF EXISTS comercial.detalles_venta")
    op.execute("DROP TABLE IF EXISTS comercial.ventas")
    op.execute("DROP TABLE IF EXISTS inventario.detalles_traslado")
    op.execute("DROP TABLE IF EXISTS inventario.traslados")
    op.execute("DROP TABLE IF EXISTS comercial.detalles_reserva")
    op.execute("DROP TABLE IF EXISTS comercial.reservas")
    op.execute("DROP INDEX IF EXISTS inventario.uq_movimientos_efecto_logico")
    op.execute("DROP INDEX IF EXISTS inventario.uq_movimientos_clave_idempotencia")
    op.execute("ALTER TABLE inventario.movimientos_inventario DROP COLUMN IF EXISTS linea_referencia_id")
    op.execute("ALTER TABLE inventario.movimientos_inventario DROP COLUMN IF EXISTS clave_idempotencia")
    for cons in (
        "ck_sucursales_modalidad_adelanto", "ck_sucursales_valor_adelanto_nneg",
        "ck_sucursales_adelanto_porcentaje_max", "ck_sucursales_adelanto_coherente",
    ):
        op.execute(
            f"ALTER TABLE organizacion.sucursales DROP CONSTRAINT IF EXISTS {cons}"
        )
    op.execute("ALTER TABLE organizacion.sucursales DROP COLUMN IF EXISTS valor_adelanto")
    op.execute("ALTER TABLE organizacion.sucursales DROP COLUMN IF EXISTS modalidad_adelanto")
    op.execute("ALTER TABLE organizacion.sucursales DROP COLUMN IF EXISTS adelanto_activo")
    op.execute("DROP TYPE IF EXISTS comercial.estado_venta")
    op.execute("DROP TYPE IF EXISTS inventario.estado_traslado")
    op.execute("DROP TYPE IF EXISTS comercial.estado_reserva")
