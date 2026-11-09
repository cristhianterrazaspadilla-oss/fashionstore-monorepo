"""Modelo objetivo de 66 tablas para los 27 CU del segundo parcial.

Revision ID: 0009_modelo_final_66
Revises: 0008_cierre_cu03_cu04_cu16_cu18

Solo expansion desde 0008. No inventa filas de negocio, tasas ni vigencias.
El SQL fuente esta en sql/0009_modelo_final_66.sql.
"""

from pathlib import Path

from alembic import op


revision = "0009_modelo_final_66"
down_revision = "0008_cierre_cu03_cu04_cu16_cu18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = (Path(__file__).parent / "sql" / "0009_modelo_final_66.sql").read_text(encoding="utf-8")
    for statement in sql.split(";\n"):
        statement = statement.strip()
        if statement:
            op.execute(statement)


def downgrade() -> None:
    raise RuntimeError(
        "0009 contiene obligaciones financieras y movimientos; restaurar un respaldo "
        "verificado para revertir en vez de borrar datos con downgrade."
    )
