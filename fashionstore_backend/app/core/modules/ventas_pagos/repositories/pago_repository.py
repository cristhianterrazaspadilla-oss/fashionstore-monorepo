"""Repositorio PagoRepository — CU11, CU15."""
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.modules.ventas_pagos.models import Pago


class PagoRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, pago: Pago) -> Pago:
        self.db.add(pago)
        await self.db.flush()
        return pago

    async def buscarPorId(self, pago_id: uuid.UUID) -> Optional[Pago]:
        result = await self.db.execute(select(Pago).where(Pago.id == pago_id))
        return result.scalars().first()

    async def buscarPorClave(self, clave: uuid.UUID) -> Optional[Pago]:
        result = await self.db.execute(select(Pago).where(Pago.clave_idempotencia == clave))
        return result.scalars().first()

    async def buscarAdelantoDeReserva(self, reserva_id: uuid.UUID) -> Optional[Pago]:
        """Unico adelanto confirmado por reserva (no acumula)."""
        result = await self.db.execute(
            select(Pago).where(
                Pago.contexto == "RESERVA",
                Pago.reserva_id == reserva_id,
                Pago.tipo_pago == "ADELANTO",
            )
        )
        return result.scalars().first()

    async def pagosDeVenta(self, venta_id: uuid.UUID, empresa_id=None) -> List[Pago]:
        query = select(Pago).where(Pago.contexto == "VENTA", Pago.venta_id == venta_id)
        if empresa_id is not None:
            query = query.where(Pago.empresa_id == empresa_id)
        result = await self.db.execute(
            query.order_by(Pago.pagado_en)
        )
        return list(result.scalars().all())
