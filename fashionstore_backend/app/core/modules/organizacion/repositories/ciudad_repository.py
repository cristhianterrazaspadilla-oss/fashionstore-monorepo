import uuid
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.organizacion.models import Ciudad


class CiudadRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def buscarPorId(self, ciudad_id: uuid.UUID) -> Optional[Ciudad]:
        query = select(Ciudad).where(Ciudad.id == ciudad_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorNombre(self, nombre: str) -> Optional[Ciudad]:
        query = select(Ciudad).where(Ciudad.nombre.ilike(nombre.strip()))
        result = await self.db.execute(query)
        return result.scalars().first()

    async def listar(self, solo_activas: bool = True) -> List[Ciudad]:
        query = select(Ciudad)
        if solo_activas:
            query = query.where(Ciudad.activo == True)
        query = query.order_by(Ciudad.nombre)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def crear(self, nombre: str) -> Ciudad:
        ciudad = Ciudad(nombre=nombre.strip(), activo=True)
        self.db.add(ciudad)
        await self.db.flush()
        return ciudad

    async def actualizar(
        self, ciudad_id: uuid.UUID, nombre: Optional[str] = None, activo: Optional[bool] = None
    ) -> Optional[Ciudad]:
        valores = {}
        if nombre is not None:
            valores["nombre"] = nombre.strip()
        if activo is not None:
            valores["activo"] = activo
        if valores:
            query = update(Ciudad).where(Ciudad.id == ciudad_id).values(**valores)
            await self.db.execute(query)
        return await self.buscarPorId(ciudad_id)
