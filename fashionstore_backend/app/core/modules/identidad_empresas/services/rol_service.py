from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.identidad_empresas.schemas import RolDTO
from backend.app.core.modules.identidad_empresas.repositories.rol_repository import RolRepository


class RolService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.rol_repo = RolRepository(db)

    async def listar(self, solo_activos: bool = True) -> List[RolDTO]:
        roles = await self.rol_repo.listar(solo_activos=solo_activos)
        return [
            RolDTO(
                id=r.id,
                nombre=r.nombre,
                descripcion=r.descripcion,
                activo=r.activo,
                creado_en=r.creado_en
            )
            for r in roles
        ]
