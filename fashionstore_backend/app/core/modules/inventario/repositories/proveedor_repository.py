import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.catalogo.models import Proveedor

class ProveedorRepository:
    def __init__(self, db: AsyncSession, empresa_id: Optional[uuid.UUID] = None):
        self.db = db
        self.empresa_id = empresa_id

    async def buscarPorId(self, proveedor_id: uuid.UUID) -> Optional[Proveedor]:
        query = select(Proveedor).where(Proveedor.id == proveedor_id)
        if self.empresa_id:
            query = query.where(Proveedor.empresa_id == self.empresa_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorNit(self, nit: str) -> Optional[Proveedor]:
        query = select(Proveedor).where(Proveedor.nit == nit.strip())
        if self.empresa_id:
            query = query.where(Proveedor.empresa_id == self.empresa_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def listar(self, solo_activos: bool = False) -> List[Proveedor]:
        query = select(Proveedor)
        if self.empresa_id:
            query = query.where(Proveedor.empresa_id == self.empresa_id)
        if solo_activos:
            query = query.where(Proveedor.activo == True)
        query = query.order_by(Proveedor.razon_social)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def crear(self, proveedor: Proveedor) -> Proveedor:
        self.db.add(proveedor)
        await self.db.flush()
        return proveedor
