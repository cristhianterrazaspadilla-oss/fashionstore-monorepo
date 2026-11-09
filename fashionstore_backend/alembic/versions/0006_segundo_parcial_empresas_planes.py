"""Empresas, planes y ambito de los datos heredados.

Revision ID: 0006_empresas_planes
Revises: 0005_ciclo3_correcciones

La suscripcion de la empresa heredada se asigna por CU02 con fechas reales;
esta migracion no inventa una vigencia.
"""

from alembic import op

revision = "0006_empresas_planes"
down_revision = "0005_ciclo3_correcciones"
branch_labels = None
depends_on = None

EMPRESA_HEREDADA = "0ddf24a9-edeb-510f-b8e2-22d41847f477"
PLAN_BASICO = "bf1875d3-4533-5c2b-bf8c-138d59d24de8"
PLAN_PROFESIONAL = "a372fc96-f36b-59b5-aa93-f640ddcaf504"
ROL_SUPERADMIN = "6d441afe-4d2a-577c-b972-1d9cdbf5194f"

# Solo entidades con identidad empresarial propia; los detalles heredan el
# ambito de su cabecera y se validaran mediante las referencias relacionadas.
TABLAS_EMPRESARIALES = (
    "organizacion.sucursales",
    "catalogo.categorias",
    "catalogo.tallas",
    "catalogo.colores",
    "catalogo.temporadas",
    "catalogo.colecciones",
    "catalogo.proveedores",
    "catalogo.productos",
    "catalogo.variantes_producto",
    "catalogo.promociones",
    "inventario.lotes_recepcion",
    "inventario.traslados",
    "comercial.reservas",
    "comercial.ventas",
    "comercial.carritos",
    "inteligencia.historial_navegacion",
    "inteligencia.solicitudes_ia",
)


def upgrade() -> None:
    # Restricciones heredadas de Ciclo 3 que antes se reescribian al iniciar
    # FastAPI. Quedan versionadas en Alembic para que iniciar no ejecute DDL.
    op.execute("""
        ALTER TABLE inventario.movimientos_inventario
        DROP CONSTRAINT IF EXISTS movimientos_inventario_tipo_check
    """)
    op.execute("""
        ALTER TABLE inventario.movimientos_inventario
        ADD CONSTRAINT movimientos_inventario_tipo_check CHECK (
            tipo IN ('RECEPCION_PROVEEDOR','RESERVA','LIBERACION_RESERVA',
                     'COMPROMISO_TRASLADO','DESPACHO_TRASLADO','RECEPCION_TRASLADO',
                     'VENTA_PRESENCIAL','VENTA_DIGITAL','DEVOLUCION','MERMA','AJUSTE',
                     'COMPROMISO_DIGITAL','LIBERACION_DIGITAL')
        )
    """)
    op.execute("""
        ALTER TABLE inteligencia.historial_navegacion
        DROP CONSTRAINT IF EXISTS historial_navegacion_evento_check
    """)
    op.execute("""
        ALTER TABLE inteligencia.historial_navegacion
        ADD CONSTRAINT historial_navegacion_evento_check CHECK (
            evento IN ('VISTA_PRODUCTO','BUSQUEDA','AGREGA_CARRITO',
                       'AGREGA_RESERVA','PRUEBA_VIRTUAL','COMPRA')
        )
    """)
    # El pago hereda empresa de una sola cabecera. El CHECK anterior aceptaba
    # que ambos IDs estuvieran presentes y abría una referencia ambigua.
    op.execute("""
        ALTER TABLE comercial.pagos
        ADD CONSTRAINT ck_pagos_un_solo_recurso CHECK (
            (contexto = 'RESERVA' AND reserva_id IS NOT NULL AND venta_id IS NULL)
            OR
            (contexto = 'VENTA' AND venta_id IS NOT NULL AND reserva_id IS NULL)
        )
    """)
    op.execute("CREATE SCHEMA IF NOT EXISTS plataforma")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("""
        CREATE TABLE organizacion.empresas (
            id uuid PRIMARY KEY,
            codigo varchar(60) NOT NULL UNIQUE,
            nombre varchar(180) NOT NULL,
            estado varchar(24) NOT NULL DEFAULT 'PENDIENTE_PLAN',
            catalogo_version bigint NOT NULL DEFAULT 1,
            catalogo_actualizado_en timestamptz NOT NULL DEFAULT now(),
            plazo_cambios_dias integer NOT NULL DEFAULT 15,
            creada_en timestamptz NOT NULL DEFAULT now(),
            actualizada_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_empresas_estado CHECK (
                estado IN ('PENDIENTE_PLAN','ACTIVA','SUSPENDIDA')
            ),
            CONSTRAINT ck_empresas_catalogo_version CHECK (catalogo_version > 0),
            CONSTRAINT ck_empresas_plazo_cambios CHECK (plazo_cambios_dias > 0)
        )
    """)
    op.execute(f"""
        INSERT INTO organizacion.empresas (id, codigo, nombre, estado)
        VALUES ('{EMPRESA_HEREDADA}', 'fashionstore',
                'FashionStore - datos heredados', 'ACTIVA')
    """)
    op.execute("""
        CREATE TABLE plataforma.planes (
            id uuid PRIMARY KEY,
            codigo varchar(30) NOT NULL UNIQUE,
            nombre varchar(80) NOT NULL,
            max_sucursales_activas integer NOT NULL,
            reportes_generativos boolean NOT NULL DEFAULT false,
            modelos_ml boolean NOT NULL DEFAULT false,
            permite_operacion_offline boolean NOT NULL DEFAULT true,
            activo boolean NOT NULL DEFAULT true,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_planes_max_sucursales CHECK (max_sucursales_activas > 0)
        )
    """)
    op.execute(f"""
        INSERT INTO plataforma.planes
            (id, codigo, nombre, max_sucursales_activas,
             reportes_generativos, modelos_ml)
        VALUES
            ('{PLAN_BASICO}', 'BASICO', 'Basico', 2, false, false),
            ('{PLAN_PROFESIONAL}', 'PROFESIONAL', 'Profesional', 10, true, true)
    """)
    op.execute(f"""
        INSERT INTO seguridad.roles (id, nombre, descripcion, activo, creado_en)
        VALUES ('{ROL_SUPERADMIN}', 'SUPERADMIN',
                'Administracion de la plataforma', true, now())
        ON CONFLICT (nombre) DO NOTHING
    """)

    # Una persona de plataforma futura tendra empresa_id nulo. Los usuarios
    # heredados son de la empresa heredada, incluido el administrador actual.
    op.execute("ALTER TABLE seguridad.usuarios ADD COLUMN empresa_id uuid")
    op.execute(
        f"UPDATE seguridad.usuarios SET empresa_id = '{EMPRESA_HEREDADA}'"
    )
    op.execute("""
        ALTER TABLE seguridad.usuarios
        ADD CONSTRAINT fk_usuarios_empresa
        FOREIGN KEY (empresa_id) REFERENCES organizacion.empresas(id)
    """)
    op.execute("CREATE INDEX ix_seguridad_usuarios_empresa_id ON seguridad.usuarios (empresa_id)")
    op.execute("""
        CREATE FUNCTION seguridad.validar_usuario_empresa()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE nombre_rol text;
        BEGIN
            SELECT nombre INTO nombre_rol FROM seguridad.roles WHERE id = NEW.rol_id;
            IF nombre_rol = 'SUPERADMIN' AND NEW.empresa_id IS NOT NULL THEN
                RAISE EXCEPTION 'El superadministrador debe ser global'
                    USING ERRCODE = '23514';
            END IF;
            IF nombre_rol <> 'SUPERADMIN' AND NEW.empresa_id IS NULL THEN
                RAISE EXCEPTION 'El usuario empresarial requiere empresa'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND
               OLD.empresa_id IS DISTINCT FROM NEW.empresa_id THEN
                RAISE EXCEPTION 'No se puede trasladar un usuario entre empresas'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER tg_usuarios_empresa
        BEFORE INSERT OR UPDATE ON seguridad.usuarios
        FOR EACH ROW EXECUTE FUNCTION seguridad.validar_usuario_empresa()
    """)

    for tabla in TABLAS_EMPRESARIALES:
        op.execute(f"ALTER TABLE {tabla} ADD COLUMN empresa_id uuid")
        op.execute(f"UPDATE {tabla} SET empresa_id = '{EMPRESA_HEREDADA}'")
        op.execute(f"ALTER TABLE {tabla} ALTER COLUMN empresa_id SET NOT NULL")
        esquema, nombre = tabla.split(".", 1)
        op.execute(
            f"ALTER TABLE {tabla} ADD CONSTRAINT fk_{nombre}_empresa "
            "FOREIGN KEY (empresa_id) REFERENCES organizacion.empresas(id)"
        )
        op.execute(f"CREATE INDEX ix_{esquema}_{nombre}_empresa_id ON {tabla} (empresa_id)")

    # Las claves de negocio dejan de ser globales. Los UUID PK permanecen.
    for tabla, restriccion in (
        ("seguridad.usuarios", "usuarios_correo_electronico_key"),
        ("organizacion.sucursales", "sucursales_ciudad_id_nombre_key"),
        ("catalogo.categorias", "categorias_categoria_padre_id_nombre_key"),
        ("catalogo.tallas", "tallas_nombre_key"),
        ("catalogo.colores", "colores_nombre_key"),
        ("catalogo.temporadas", "temporadas_nombre_key"),
        ("catalogo.colecciones", "colecciones_nombre_key"),
        ("catalogo.proveedores", "proveedores_nit_key"),
        ("catalogo.variantes_producto", "variantes_producto_sku_key"),
        ("catalogo.variantes_producto", "variantes_producto_codigo_barras_key"),
        ("catalogo.promociones", "promociones_codigo_key"),
        ("comercial.reservas", "reservas_codigo_key"),
        ("comercial.ventas", "ventas_numero_key"),
    ):
        op.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {restriccion}")

    op.execute("""
        CREATE UNIQUE INDEX uq_usuarios_empresa_correo
        ON seguridad.usuarios (empresa_id, lower(correo_electronico))
        WHERE empresa_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_usuarios_plataforma_correo
        ON seguridad.usuarios (lower(correo_electronico))
        WHERE empresa_id IS NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_sucursales_empresa_ciudad_nombre
        ON organizacion.sucursales (empresa_id, ciudad_id, lower(nombre))
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_categorias_empresa_padre_nombre
        ON catalogo.categorias
        (empresa_id, coalesce(categoria_padre_id,
         '00000000-0000-0000-0000-000000000000'::uuid), lower(nombre))
    """)
    for tabla, columna in (
        ("tallas", "nombre"), ("colores", "nombre"),
        ("temporadas", "nombre"), ("colecciones", "nombre"),
    ):
        op.execute(
            f"CREATE UNIQUE INDEX uq_{tabla}_empresa_nombre "
            f"ON catalogo.{tabla} (empresa_id, lower({columna}))"
        )
    for tabla, columna, opcional in (
        ("catalogo.proveedores", "nit", True),
        ("catalogo.variantes_producto", "sku", False),
        ("catalogo.variantes_producto", "codigo_barras", True),
        ("catalogo.promociones", "codigo", False),
        ("comercial.reservas", "codigo", False),
        ("comercial.ventas", "numero", False),
    ):
        nombre = tabla.split(".", 1)[1]
        op.execute(
            f"CREATE UNIQUE INDEX uq_{nombre}_empresa_{columna} "
            f"ON {tabla} (empresa_id, {columna}) "
            + (f"WHERE {columna} IS NOT NULL" if opcional else "")
        )

    # Claves auxiliares para FKs compuestas entre entidades raiz.
    for tabla in ("seguridad.usuarios", *TABLAS_EMPRESARIALES):
        nombre = tabla.split(".", 1)[1]
        op.execute(
            f"ALTER TABLE {tabla} ADD CONSTRAINT uq_{nombre}_id_empresa "
            "UNIQUE (id, empresa_id)"
        )

    op.execute("""
        CREATE TABLE organizacion.suscripciones (
            id uuid PRIMARY KEY,
            empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
            plan_id uuid NOT NULL REFERENCES plataforma.planes(id),
            version integer NOT NULL,
            inicia_en timestamptz NOT NULL,
            vence_en timestamptz NOT NULL,
            creada_en timestamptz NOT NULL DEFAULT now(),
            creada_por uuid NOT NULL REFERENCES seguridad.usuarios(id),
            motivo text NOT NULL,
            CONSTRAINT ck_suscripciones_version CHECK (version > 0),
            CONSTRAINT ck_suscripciones_vigencia CHECK (inicia_en < vence_en),
            CONSTRAINT uq_suscripciones_empresa_version UNIQUE (empresa_id, version),
            CONSTRAINT ex_suscripciones_vigencias EXCLUDE USING gist
                (empresa_id WITH =, tstzrange(inicia_en, vence_en, '[)') WITH &&)
        )
    """)
    op.execute(
        "CREATE INDEX ix_suscripciones_empresa_vence "
        "ON organizacion.suscripciones (empresa_id, vence_en)"
    )
    op.execute("""
        CREATE FUNCTION organizacion.validar_autor_suscripcion()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE es_plataforma boolean;
        BEGIN
            SELECT r.nombre = 'SUPERADMIN' AND u.empresa_id IS NULL
            INTO es_plataforma
            FROM seguridad.usuarios u
            JOIN seguridad.roles r ON r.id = u.rol_id
            WHERE u.id = NEW.creada_por;
            IF es_plataforma IS DISTINCT FROM true THEN
                RAISE EXCEPTION 'La suscripcion requiere superadministrador de plataforma'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER tg_suscripciones_autor
        BEFORE INSERT OR UPDATE ON organizacion.suscripciones
        FOR EACH ROW EXECUTE FUNCTION organizacion.validar_autor_suscripcion()
    """)

    # Los detalles no duplican empresa_id. Esta comprobacion preserva su
    # ambito a traves de las entidades raiz, tambien cuando se escribe SQL.
    op.execute("""
        CREATE FUNCTION organizacion.empresa_de_recurso(tipo text, identificador uuid)
        RETURNS uuid LANGUAGE plpgsql STABLE AS $$
        DECLARE resultado uuid;
        BEGIN
            IF identificador IS NULL THEN RETURN NULL; END IF;
            CASE tipo
                WHEN 'empresa' THEN
                    SELECT id INTO resultado FROM organizacion.empresas WHERE id = identificador;
                WHEN 'usuario' THEN
                    SELECT empresa_id INTO resultado FROM seguridad.usuarios WHERE id = identificador;
                WHEN 'sucursal' THEN
                    SELECT empresa_id INTO resultado FROM organizacion.sucursales WHERE id = identificador;
                WHEN 'categoria' THEN
                    SELECT empresa_id INTO resultado FROM catalogo.categorias WHERE id = identificador;
                WHEN 'talla' THEN
                    SELECT empresa_id INTO resultado FROM catalogo.tallas WHERE id = identificador;
                WHEN 'color' THEN
                    SELECT empresa_id INTO resultado FROM catalogo.colores WHERE id = identificador;
                WHEN 'temporada' THEN
                    SELECT empresa_id INTO resultado FROM catalogo.temporadas WHERE id = identificador;
                WHEN 'coleccion' THEN
                    SELECT empresa_id INTO resultado FROM catalogo.colecciones WHERE id = identificador;
                WHEN 'proveedor' THEN
                    SELECT empresa_id INTO resultado FROM catalogo.proveedores WHERE id = identificador;
                WHEN 'producto' THEN
                    SELECT empresa_id INTO resultado FROM catalogo.productos WHERE id = identificador;
                WHEN 'variante' THEN
                    SELECT empresa_id INTO resultado FROM catalogo.variantes_producto WHERE id = identificador;
                WHEN 'promocion' THEN
                    SELECT empresa_id INTO resultado FROM catalogo.promociones WHERE id = identificador;
                WHEN 'lote' THEN
                    SELECT empresa_id INTO resultado FROM inventario.lotes_recepcion WHERE id = identificador;
                WHEN 'traslado' THEN
                    SELECT empresa_id INTO resultado FROM inventario.traslados WHERE id = identificador;
                WHEN 'reserva' THEN
                    SELECT empresa_id INTO resultado FROM comercial.reservas WHERE id = identificador;
                WHEN 'detalle_reserva' THEN
                    SELECT r.empresa_id INTO resultado
                    FROM comercial.detalles_reserva d
                    JOIN comercial.reservas r ON r.id = d.reserva_id
                    WHERE d.id = identificador;
                WHEN 'venta' THEN
                    SELECT empresa_id INTO resultado FROM comercial.ventas WHERE id = identificador;
                WHEN 'carrito' THEN
                    SELECT empresa_id INTO resultado FROM comercial.carritos WHERE id = identificador;
                ELSE
                    RAISE EXCEPTION 'Tipo de recurso no autorizado: %', tipo;
            END CASE;
            RETURN resultado;
        END;
        $$
    """)
    op.execute("""
        CREATE FUNCTION organizacion.validar_ambito_relaciones()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            datos jsonb := to_jsonb(NEW);
            empresa uuid;
            vinculada uuid;
            identificador uuid;
            indice integer;
        BEGIN
            IF TG_NARGS < 2 OR TG_NARGS % 2 <> 0 THEN
                RAISE EXCEPTION 'Argumentos de validacion incompletos';
            END IF;
            IF TG_OP = 'UPDATE' AND datos ? 'empresa_id' AND
               (to_jsonb(OLD) ->> 'empresa_id') IS DISTINCT FROM
               (datos ->> 'empresa_id') THEN
                RAISE EXCEPTION 'No se puede trasladar una entidad entre empresas'
                    USING ERRCODE = '23514';
            END IF;
            identificador := (datos ->> TG_ARGV[0])::uuid;
            empresa := organizacion.empresa_de_recurso(TG_ARGV[1], identificador);
            IF empresa IS NULL THEN
                RAISE EXCEPTION 'No se pudo determinar la empresa de %', TG_TABLE_NAME
                    USING ERRCODE = '23514';
            END IF;
            indice := 2;
            WHILE indice < TG_NARGS LOOP
                identificador := (datos ->> TG_ARGV[indice])::uuid;
                IF identificador IS NOT NULL THEN
                    vinculada := organizacion.empresa_de_recurso(
                        TG_ARGV[indice + 1], identificador
                    );
                    IF vinculada IS DISTINCT FROM empresa THEN
                        RAISE EXCEPTION 'Referencia ajena a la empresa en %.%',
                            TG_TABLE_SCHEMA, TG_TABLE_NAME
                            USING ERRCODE = '23514';
                    END IF;
                END IF;
                indice := indice + 2;
            END LOOP;
            RETURN NEW;
        END;
        $$
    """)
    validaciones = (
        ("seguridad.empleados", "usuario_id", "usuario", "sucursal_id", "sucursal"),
        ("catalogo.categorias", "empresa_id", "empresa", "categoria_padre_id", "categoria"),
        ("catalogo.productos", "empresa_id", "empresa", "categoria_id", "categoria",
         "proveedor_principal_id", "proveedor"),
        ("catalogo.variantes_producto", "empresa_id", "empresa", "producto_id", "producto",
         "talla_id", "talla", "color_id", "color"),
        ("catalogo.producto_temporada", "producto_id", "producto", "temporada_id", "temporada"),
        ("catalogo.producto_coleccion", "producto_id", "producto", "coleccion_id", "coleccion"),
        ("catalogo.promocion_variante", "promocion_id", "promocion", "variante_id", "variante"),
        ("inventario.lotes_recepcion", "empresa_id", "empresa", "proveedor_id", "proveedor",
         "sucursal_id", "sucursal", "recibido_por_id", "usuario",
         "temporada_id", "temporada", "coleccion_id", "coleccion"),
        ("inventario.detalles_lote_recepcion", "lote_id", "lote", "variante_id", "variante"),
        ("inventario.inventario_sucursal", "variante_id", "variante", "sucursal_id", "sucursal"),
        ("inventario.movimientos_inventario", "variante_id", "variante",
         "sucursal_origen_id", "sucursal", "sucursal_destino_id", "sucursal",
         "responsable_id", "usuario"),
        ("inventario.traslados", "empresa_id", "empresa", "reserva_id", "reserva",
         "sucursal_origen_id", "sucursal", "sucursal_destino_id", "sucursal",
         "solicitado_por_id", "usuario", "aprobado_por_id", "usuario"),
        ("inventario.detalles_traslado", "traslado_id", "traslado",
         "detalle_reserva_id", "detalle_reserva", "variante_id", "variante"),
        ("comercial.reservas", "empresa_id", "empresa", "cliente_id", "usuario",
         "sucursal_destino_id", "sucursal", "preparada_por", "usuario",
         "atendida_por", "usuario"),
        ("comercial.detalles_reserva", "reserva_id", "reserva", "variante_id", "variante"),
        ("comercial.ventas", "empresa_id", "empresa", "cliente_id", "usuario",
         "reserva_id", "reserva", "sucursal_id", "sucursal", "cajero_id", "usuario"),
        ("comercial.detalles_venta", "venta_id", "venta", "detalle_reserva_id", "detalle_reserva",
         "variante_id", "variante", "promocion_id", "promocion"),
        ("comercial.carritos", "empresa_id", "empresa", "cliente_id", "usuario",
         "venta_id", "venta"),
        ("comercial.detalles_carrito", "carrito_id", "carrito", "variante_id", "variante"),
        ("comercial.pedidos_entrega", "venta_id", "venta", "sucursal_id", "sucursal",
         "cliente_id", "usuario"),
        ("inteligencia.historial_navegacion", "empresa_id", "empresa", "cliente_id", "usuario",
         "usuario_id", "usuario", "producto_id", "producto", "variante_id", "variante"),
        ("inteligencia.solicitudes_ia", "empresa_id", "empresa", "cliente_id", "usuario",
         "usuario_id", "usuario"),
    )
    for tabla, *argumentos in validaciones:
        esquema, nombre = tabla.split(".", 1)
        parametros = ", ".join(f"'{argumento}'" for argumento in argumentos)
        op.execute(
            f"CREATE TRIGGER tg_{esquema}_{nombre}_ambito "
            f"BEFORE INSERT OR UPDATE ON {tabla} FOR EACH ROW "
            f"EXECUTE FUNCTION organizacion.validar_ambito_relaciones({parametros})"
        )


def downgrade() -> None:
    raise RuntimeError(
        "0006 contiene backfill empresarial y nuevas relaciones; "
        "restaurar el respaldo verificado en otra base para revertirla."
    )
