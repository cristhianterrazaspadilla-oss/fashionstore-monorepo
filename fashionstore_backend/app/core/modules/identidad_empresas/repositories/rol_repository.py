import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.identidad_empresas.models import Rol


class RolRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def buscarPorNombre(self, nombre: str) -> Optional[Rol]:
        query = select(Rol).where(Rol.nombre == nombre)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorId(self, rol_id: uuid.UUID) -> Optional[Rol]:
        query = select(Rol).where(Rol.id == rol_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def listar(self, solo_activos: bool = True) -> List[Rol]:
        query = select(Rol)
        if solo_activos:
            query = query.where(Rol.activo == True)
        query = query.order_by(Rol.nombre)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def crear(self, nombre: str, descripcion: Optional[str] = None) -> Rol:
        rol = Rol(nombre=nombre, descripcion=descripcion, activo=True)
        self.db.add(rol)
        await self.db.flush()
        return rol
