import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.inventario.models import LoteRecepcion

class LoteRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, lote: LoteRecepcion) -> LoteRecepcion:
        """Persistir lote (y sus detalles via cascade). No hace commit, solo flush."""
        self.db.add(lote)
        await self.db.flush()
        return lote

    async def buscarPorId(self, lote_id: uuid.UUID) -> Optional[LoteRecepcion]:
        query = (
            select(LoteRecepcion)
            .options(selectinload(LoteRecepcion.detalles))
            .where(LoteRecepcion.id == lote_id)
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def listar(self, limit: int = 50, offset: int = 0) -> List[LoteRecepcion]:
        query = (
            select(LoteRecepcion)
            .options(selectinload(LoteRecepcion.detalles))
            .order_by(LoteRecepcion.fecha_recepcion.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())
