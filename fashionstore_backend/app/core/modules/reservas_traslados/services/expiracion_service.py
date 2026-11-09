"""Servicio ExpiracionService — CU26 / CU24: Expiración periódica reentrante de reservas.

Job atómico y reentrante para vencimiento automático de reservas por lotes.
Usa advisory lock en PostgreSQL (pg_try_advisory_lock), SKIP LOCKED para
concurrencia sin bloqueos mutuos, y libera inventario emitiendo movimientos
Kardex con tipo 'LIBERACION_RESERVA'.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.reloj import RelojSistema
from backend.app.core.modules.reservas_traslados.schemas import ExpiracionResultadoDTO
from backend.app.core.modules.reservas_traslados.services.reserva_service import (
    ADVISORY_LOCK_EXPRIACION,
    ReservaService,
)


class ExpiracionService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.reserva_service = ReservaService(db, reloj=self.reloj)

    async def expirar_reservas_vencidas(
        self,
        ahora: Optional[datetime] = None,
        limite: int = 100,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> ExpiracionResultadoDTO:
        """Ejecuta la expiración de reservas vencidas de manera reentrante.

        - Idempotente y concurrente con advisory lock de PostgreSQL.
        - Libera el inventario reservado y registra movimiento Kardex LIBERACION_RESERVA.
        - Retorna un ExpiracionResultadoDTO con el detalle de reservas procesadas.
        """
        return await self.reserva_service.expirarVencidas(
            ahora=ahora, limite=limite, empresa_id=empresa_id
        )

    async def expirarVencidas(
        self,
        ahora: Optional[datetime] = None,
        limite: int = 100,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> ExpiracionResultadoDTO:
        return await self.expirar_reservas_vencidas(
            ahora=ahora, limite=limite, empresa_id=empresa_id
        )
