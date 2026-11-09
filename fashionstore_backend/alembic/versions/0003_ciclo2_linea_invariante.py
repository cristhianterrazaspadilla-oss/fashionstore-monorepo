"""Ciclo 2 Entrega 5 — corrige el invariante de cantidades por linea.

reservada pasa a ser saldo actual (disminuye al vender/liberar); el
invariante correcto es reservada + pendiente + vendida + liberada <= solicitada.
Reemplaza ck_detalle_reserva_suma_consistente y
ck_detalle_reserva_vendida_lte_reservada por
ck_detalle_reserva_cantidades_consistentes.
"""
from alembic import op

revision = "0003_ciclo2_linea_invariante"
down_revision = "0002_ciclo2_entrega4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE comercial.detalles_reserva DROP CONSTRAINT IF EXISTS ck_detalle_reserva_vendida_lte_reservada")
    op.execute("ALTER TABLE comercial.detalles_reserva DROP CONSTRAINT IF EXISTS ck_detalle_reserva_suma_consistente")
    # Normaliza filas escritas con la semantica anterior (reservada en pico):
    # reservada pasa a ser saldo actual.
    op.execute(
        "UPDATE comercial.detalles_reserva "
        "SET cantidad_reservada = cantidad_reservada - cantidad_vendida "
        "WHERE cantidad_vendida > 0 AND cantidad_reservada >= cantidad_vendida"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_detalle_reserva_cantidades_consistentes') THEN
                ALTER TABLE comercial.detalles_reserva ADD CONSTRAINT ck_detalle_reserva_cantidades_consistentes
                CHECK (cantidad_reservada + cantidad_pendiente_traslado + cantidad_vendida + cantidad_liberada <= cantidad_solicitada);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE comercial.detalles_reserva DROP CONSTRAINT IF EXISTS ck_detalle_reserva_cantidades_consistentes")
