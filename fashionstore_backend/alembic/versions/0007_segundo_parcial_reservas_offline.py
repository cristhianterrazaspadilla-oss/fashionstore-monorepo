"""Catalogo versionado y resultado durable de sincronizacion de reservas.

Revision ID: 0007_reservas_offline
Revises: 0006_empresas_planes
"""

from alembic import op

revision = "0007_reservas_offline"
down_revision = "0006_empresas_planes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE comercial.referencias_horarias (
            id uuid PRIMARY KEY,
            empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
            usuario_id uuid NOT NULL REFERENCES seguridad.usuarios(id),
            dispositivo_id uuid NOT NULL,
            emitida_en timestamptz NOT NULL,
            vence_en timestamptz NOT NULL,
            CONSTRAINT ck_referencias_horarias_vigencia
                CHECK (emitida_en < vence_en),
            CONSTRAINT fk_referencias_usuario_empresa
                FOREIGN KEY (usuario_id, empresa_id)
                REFERENCES seguridad.usuarios(id, empresa_id),
            CONSTRAINT uq_referencias_ambito
                UNIQUE (id, empresa_id, usuario_id, dispositivo_id)
        )
    """)
    op.execute("""
        CREATE INDEX ix_referencias_usuario_dispositivo_vence
        ON comercial.referencias_horarias
        (empresa_id, usuario_id, dispositivo_id, vence_en)
    """)
    op.execute("""
        CREATE TABLE comercial.operaciones_sincronizacion (
            id uuid PRIMARY KEY,
            empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
            usuario_id uuid NOT NULL REFERENCES seguridad.usuarios(id),
            operacion_id uuid NOT NULL,
            tipo varchar(40) NOT NULL,
            version_esquema integer NOT NULL,
            dispositivo_id uuid NOT NULL,
            secuencia_local bigint NOT NULL,
            creada_local_en timestamptz NOT NULL,
            recibida_en timestamptz NOT NULL,
            aceptada_en timestamptz,
            referencia_horaria_id uuid,
            hash_solicitud varchar(64) NOT NULL,
            solicitud jsonb NOT NULL,
            estado varchar(40) NOT NULL,
            codigo varchar(40) NOT NULL,
            detalle text NOT NULL,
            resultado jsonb NOT NULL,
            recurso_id uuid,
            revision integer NOT NULL DEFAULT 1,
            CONSTRAINT ck_operaciones_version CHECK (version_esquema > 0),
            CONSTRAINT ck_operaciones_secuencia CHECK (secuencia_local > 0),
            CONSTRAINT ck_operaciones_revision CHECK (revision > 0),
            CONSTRAINT ck_operaciones_hash CHECK (
                hash_solicitud ~ '^[0-9a-f]{64}$'
            ),
            CONSTRAINT ck_operaciones_tipo CHECK (
                tipo IN ('SOLICITAR_RESERVA','SOLICITAR_COMPRA','REGISTRAR_VENTA_CAJA')
            ),
            CONSTRAINT ck_operaciones_estado CHECK (
                estado IN ('ACEPTADA','RECHAZADA','REQUIERE_ACEPTACION_PRECIO',
                           'PENDIENTE_PAGO','REGISTRADA_CENTRAL',
                           'CONCILIACION_REQUERIDA','CONFLICTO')
            ),
            CONSTRAINT ck_operaciones_aceptacion CHECK (
                estado <> 'ACEPTADA' OR
                (aceptada_en IS NOT NULL AND recurso_id IS NOT NULL)
            ),
            CONSTRAINT uq_operaciones_actor_uuid
                UNIQUE (empresa_id, usuario_id, operacion_id),
            CONSTRAINT uq_operaciones_id_empresa UNIQUE (id, empresa_id),
            CONSTRAINT fk_operaciones_usuario_empresa
                FOREIGN KEY (usuario_id, empresa_id)
                REFERENCES seguridad.usuarios(id, empresa_id),
            CONSTRAINT fk_operaciones_referencia
                FOREIGN KEY (referencia_horaria_id, empresa_id, usuario_id,
                             dispositivo_id)
                REFERENCES comercial.referencias_horarias
                    (id, empresa_id, usuario_id, dispositivo_id)
        )
    """)
    op.execute("""
        CREATE INDEX ix_operaciones_actor_recibida
        ON comercial.operaciones_sincronizacion
        (empresa_id, usuario_id, recibida_en)
    """)
    op.execute("""
        CREATE INDEX ix_operaciones_recurso
        ON comercial.operaciones_sincronizacion (tipo, recurso_id)
        WHERE recurso_id IS NOT NULL
    """)

    # Los registros antiguos conservan el vencimiento calculado antes de CU18.
    # El servicio debe fijar origen_plazo_en para cada nueva reserva.
    op.execute("""
        ALTER TABLE comercial.reservas
        ADD COLUMN origen_plazo_en timestamptz,
        ADD COLUMN operacion_sincronizacion_id uuid
    """)
    op.execute("""
        ALTER TABLE comercial.reservas
        ADD CONSTRAINT uq_reservas_operacion_sincronizacion
            UNIQUE (operacion_sincronizacion_id),
        ADD CONSTRAINT fk_reservas_operacion_empresa
            FOREIGN KEY (operacion_sincronizacion_id, empresa_id)
            REFERENCES comercial.operaciones_sincronizacion (id, empresa_id),
        ADD CONSTRAINT ck_reservas_origen_plazo
            CHECK (origen_plazo_en IS NULL OR vence_en >= origen_plazo_en),
        ADD CONSTRAINT ck_reservas_operacion_origen
            CHECK (operacion_sincronizacion_id IS NULL
                   OR origen_plazo_en IS NOT NULL)
    """)
    op.execute("""
        CREATE INDEX ix_reservas_empresa_estado_vence
        ON comercial.reservas (empresa_id, estado, vence_en)
    """)

    # Metadato de publicacion: incrementa al variar el catalogo visible.
    # No guarda una copia de precios o cantidades en la empresa.
    op.execute("""
        CREATE FUNCTION organizacion.marcar_catalogo_actualizado()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE empresa uuid;
        BEGIN
            IF TG_TABLE_SCHEMA = 'inventario' THEN
                SELECT empresa_id INTO empresa
                FROM catalogo.variantes_producto
                WHERE id = (CASE WHEN TG_OP = 'DELETE'
                                 THEN OLD.variante_id ELSE NEW.variante_id END);
            ELSIF TG_TABLE_NAME = 'imagenes_producto' THEN
                SELECT empresa_id INTO empresa FROM catalogo.productos
                WHERE id = (CASE WHEN TG_OP = 'DELETE'
                                 THEN OLD.producto_id ELSE NEW.producto_id END);
            ELSIF TG_TABLE_NAME = 'promocion_variante' THEN
                SELECT empresa_id INTO empresa FROM catalogo.promociones
                WHERE id = (CASE WHEN TG_OP = 'DELETE'
                                 THEN OLD.promocion_id ELSE NEW.promocion_id END);
            ELSE
                empresa := CASE WHEN TG_OP = 'DELETE'
                               THEN OLD.empresa_id ELSE NEW.empresa_id END;
            END IF;
            IF empresa IS NOT NULL THEN
                UPDATE organizacion.empresas
                SET catalogo_version = catalogo_version + 1,
                    catalogo_actualizado_en = clock_timestamp(),
                    actualizada_en = clock_timestamp()
                WHERE id = empresa;
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$
    """)
    for tabla in (
        "organizacion.sucursales",
        "catalogo.categorias", "catalogo.tallas", "catalogo.colores",
        "catalogo.temporadas", "catalogo.colecciones",
        "catalogo.productos", "catalogo.variantes_producto",
        "catalogo.imagenes_producto", "catalogo.promociones",
        "catalogo.promocion_variante", "inventario.inventario_sucursal",
    ):
        nombre = tabla.split(".", 1)[1]
        op.execute(
            f"CREATE TRIGGER tg_{nombre}_catalogo "
            f"AFTER INSERT OR UPDATE OR DELETE ON {tabla} "
            "FOR EACH ROW EXECUTE FUNCTION "
            "organizacion.marcar_catalogo_actualizado()"
        )


def downgrade() -> None:
    raise RuntimeError(
        "0007 puede contener resultados comerciales durables; "
        "restaurar el respaldo verificado en otra base para revertirla."
    )
