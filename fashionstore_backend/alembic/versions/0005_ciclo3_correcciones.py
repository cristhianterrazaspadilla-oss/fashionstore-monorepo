"""Ciclo 3 correcciones — idempotencia aislada por actor y operación.

Aísla comercial.registros_idempotencia por (clave, usuario, tipo, operación):
misma clave de otro usuario nunca devuelve datos ajenos. Convierte la PK
global (clave) en compuesta (clave, usuario_id, recurso_tipo, operacion) con
backfill de filas legacy al usuario cero y operacion=recurso_tipo.

Revision ID: 0005_ciclo3_correcciones
Revises: 0004_ciclo3_backend
"""

from alembic import op

revision = "0005_ciclo3_correcciones"
down_revision = "0004_ciclo3_backend"
branch_labels = None
depends_on = None

_USUARIO_CERO = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE comercial.registros_idempotencia "
        "ADD COLUMN IF NOT EXISTS usuario_id uuid"
    )
    op.execute(
        "ALTER TABLE comercial.registros_idempotencia "
        "ADD COLUMN IF NOT EXISTS operacion varchar(80)"
    )
    op.execute(
        "UPDATE comercial.registros_idempotencia "
        "SET operacion = recurso_tipo WHERE operacion IS NULL"
    )
    op.execute(
        f"UPDATE comercial.registros_idempotencia "
        f"SET usuario_id = '{_USUARIO_CERO}'::uuid WHERE usuario_id IS NULL"
    )
    op.execute(
        "ALTER TABLE comercial.registros_idempotencia "
        "ALTER COLUMN operacion SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE comercial.registros_idempotencia "
        "ALTER COLUMN usuario_id SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE comercial.registros_idempotencia "
        "DROP CONSTRAINT IF EXISTS registros_idempotencia_pkey"
    )
    op.execute(
        "ALTER TABLE comercial.registros_idempotencia "
        "ADD CONSTRAINT registros_idempotencia_pkey "
        "PRIMARY KEY (clave, usuario_id, recurso_tipo, operacion)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_idempotencia_usuario_expira "
        "ON comercial.registros_idempotencia (usuario_id, expira_en)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS comercial.idx_idempotencia_usuario_expira"
    )
    op.execute(
        "ALTER TABLE comercial.registros_idempotencia "
        "DROP CONSTRAINT IF EXISTS registros_idempotencia_pkey"
    )
    # La PK compuesta permite el mismo UUID externo en ámbitos distintos;
    # al volver a la PK global se conserva una fila por clave (la más
    # reciente). Los registros son caché efímera (TTL 1-24 h), sin pérdida
    # de negocio.
    op.execute(
        "DELETE FROM comercial.registros_idempotencia a USING "
        "comercial.registros_idempotencia b "
        "WHERE a.clave = b.clave AND a.ctid < b.ctid"
    )
    op.execute(
        "ALTER TABLE comercial.registros_idempotencia "
        "ADD CONSTRAINT registros_idempotencia_pkey PRIMARY KEY (clave)"
    )
    op.execute(
        "ALTER TABLE comercial.registros_idempotencia "
        "DROP COLUMN IF EXISTS operacion"
    )
    op.execute(
        "ALTER TABLE comercial.registros_idempotencia "
        "DROP COLUMN IF EXISTS usuario_id"
    )
