import uuid
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.organizacion.schemas import CiudadCrearDTO, CiudadActualizarDTO, CiudadDTO
from backend.app.core.modules.organizacion.repositories.ciudad_repository import CiudadRepository


class CiudadService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ciudad_repo = CiudadRepository(db)

    async def crear(self, dto: CiudadCrearDTO) -> CiudadDTO:
        existente = await self.ciudad_repo.buscarPorNombre(dto.nombre)
        if existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La ciudad '{dto.nombre.strip()}' ya se encuentra registrada en el sistema"
            )

        nueva_ciudad = await self.ciudad_repo.crear(dto.nombre)
        await self.db.commit()
        await self.db.refresh(nueva_ciudad)

        return CiudadDTO(
            id=nueva_ciudad.id,
            nombre=nueva_ciudad.nombre,
            activo=nueva_ciudad.activo
        )

    async def actualizar(self, ciudad_id: uuid.UUID, dto: CiudadActualizarDTO) -> CiudadDTO:
        ciudad = await self.ciudad_repo.buscarPorId(ciudad_id)
        if not ciudad:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ciudad no encontrada",
            )

        if dto.nombre and dto.nombre.strip().lower() != ciudad.nombre.lower():
            existente = await self.ciudad_repo.buscarPorNombre(dto.nombre)
            if existente and existente.id != ciudad_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"La ciudad '{dto.nombre.strip()}' ya se encuentra registrada en el sistema",
                )

        actualizada = await self.ciudad_repo.actualizar(
            ciudad_id=ciudad_id,
            nombre=dto.nombre,
            activo=dto.activo,
        )
        await self.db.commit()
        await self.db.refresh(actualizada)
        return CiudadDTO(
            id=actualizada.id,
            nombre=actualizada.nombre,
            activo=actualizada.activo,
        )

    async def listar(self, solo_activas: bool = True) -> List[CiudadDTO]:
        ciudades = await self.ciudad_repo.listar(solo_activas=solo_activas)
        return [
            CiudadDTO(
                id=c.id,
                nombre=c.nombre,
                activo=c.activo
            )
            for c in ciudades
        ]

    async def obtenerPorId(self, ciudad_id: uuid.UUID) -> CiudadDTO:
        ciudad = await self.ciudad_repo.buscarPorId(ciudad_id)
        if not ciudad:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ciudad no encontrada"
            )
        return CiudadDTO(
            id=ciudad.id,
            nombre=ciudad.nombre,
            activo=ciudad.activo
        )
