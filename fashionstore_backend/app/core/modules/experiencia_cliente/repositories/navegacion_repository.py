"""Repositorio NavegacionRepository — CU17, CU18."""
import uuid
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.experiencia_cliente.models import HistorialNavegacion


class NavegacionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def registrar(self, evento: HistorialNavegacion) -> HistorialNavegacion:
        self.db.add(evento)
        await self.db.flush()
        return evento

    async def historialCliente(self, cliente_id: uuid.UUID, limit: int = 100) -> List[HistorialNavegacion]:
        r = await self.db.execute(
            select(HistorialNavegacion)
            .where(HistorialNavegacion.cliente_id == cliente_id)
            .order_by(HistorialNavegacion.creada_en.desc())
            .limit(limit)
        )
        return list(r.scalars().all())
