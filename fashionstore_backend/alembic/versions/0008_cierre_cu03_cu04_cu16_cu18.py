"""Cierre contratos CU03, CU04, CU16, CU18 (revision 0.3.2).

Revision ID: 0008_cierre_cu03_cu04_cu16_cu18
Revises: 0007_reservas_offline
"""

from alembic import op

revision = "0008_cierre_cu03_cu04_cu16_cu18"
down_revision = "0007_reservas_offline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Tabla catalogo.color_componentes
    op.execute("""
        CREATE TABLE catalogo.color_componentes (
            id uuid PRIMARY KEY,
            empresa_id uuid NOT NULL REFERENCES organizacion.empresas(id),
            color_id uuid NOT NULL,
            componente_id uuid NOT NULL,
            orden integer NOT NULL DEFAULT 0,
            CONSTRAINT ck_color_componente_distinto
                CHECK (color_id <> componente_id),
            CONSTRAINT ck_color_componente_orden_nneg
                CHECK (orden >= 0),
            CONSTRAINT uq_color_componente
                UNIQUE (color_id, componente_id),
            CONSTRAINT uq_color_componentes_id_empresa
                UNIQUE (id, empresa_id),
            CONSTRAINT fk_color_componentes_color_empresa
                FOREIGN KEY (color_id, empresa_id)
                REFERENCES catalogo.colores(id, empresa_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_color_componentes_componente_empresa
                FOREIGN KEY (componente_id, empresa_id)
                REFERENCES catalogo.colores(id, empresa_id)
                ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE INDEX ix_color_componentes_empresa_id
        ON catalogo.color_componentes (empresa_id)
    """)
    op.execute("""
        CREATE INDEX ix_color_componentes_componente_id
        ON catalogo.color_componentes (componente_id)
    """)
    op.execute("""
        CREATE TRIGGER tg_color_componentes_catalogo
        AFTER INSERT OR UPDATE OR DELETE ON catalogo.color_componentes
        FOR EACH ROW EXECUTE FUNCTION organizacion.marcar_catalogo_actualizado()
    """)

    # 2. catalogo.promociones: cantidad_minima
    op.execute("""
        ALTER TABLE catalogo.promociones
        ADD COLUMN cantidad_minima integer NOT NULL DEFAULT 1
        CONSTRAINT ck_promociones_cantidad_minima CHECK (cantidad_minima >= 1)
    """)

    # 3. comercial.referencias_horarias
    op.execute("""
        ALTER TABLE comercial.referencias_horarias
        ADD COLUMN hora_local_en timestamptz,
        ADD COLUMN tolerancia_segundos integer NOT NULL DEFAULT 300,
        ADD COLUMN politica_version integer NOT NULL DEFAULT 1,
        ADD COLUMN desfase_segundos integer,
        ADD COLUMN clave_idempotencia uuid,
        ADD COLUMN hash_solicitud varchar(64)
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_referencias_empresa_idempotencia
        ON comercial.referencias_horarias (empresa_id, clave_idempotencia)
        WHERE clave_idempotencia IS NOT NULL
    """)

    # 4. comercial.reservas: revision
    op.execute("""
        ALTER TABLE comercial.reservas
        ADD COLUMN revision integer NOT NULL DEFAULT 1
        CONSTRAINT ck_reservas_revision CHECK (revision >= 1)
    """)


def downgrade() -> None:
    raise RuntimeError(
        "0008 puede contener referencias horarias e inventario de componentes en produccion; "
        "restaurar respaldo verificado para revertir."
    )
