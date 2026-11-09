import uuid
from typing import List
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.catalogo.models import Proveedor
from backend.app.core.modules.inventario.schemas import ProveedorCrearDTO, ProveedorDTO
from backend.app.core.modules.inventario.repositories.proveedor_repository import ProveedorRepository

class ProveedorService:
    def __init__(self, db: AsyncSession, empresa_id: uuid.UUID | None = None):
        self.db = db
        self.empresa_id = empresa_id
        self.proveedor_repo = ProveedorRepository(db, empresa_id=empresa_id)

    async def crear(self, dto: ProveedorCrearDTO) -> ProveedorDTO:
        if self.empresa_id is None:
            raise HTTPException(status_code=400, detail="Usuario sin empresa asignada")
        if dto.nit:
            existente_nit = await self.proveedor_repo.buscarPorNit(dto.nit)
            if existente_nit:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe un proveedor con NIT '{dto.nit.strip()}'"
                )
        nuevo = Proveedor(
            empresa_id=self.empresa_id,
            razon_social=dto.razon_social.strip(),
            nit=dto.nit.strip() if dto.nit else None,
            contacto=dto.contacto.strip() if dto.contacto else None,
            telefono=dto.telefono.strip() if dto.telefono else None,
            correo_electronico=dto.correo_electronico.strip() if dto.correo_electronico else None,
            direccion=dto.direccion.strip() if dto.direccion else None,
            convenio=dto.convenio.strip() if dto.convenio else None,
            activo=dto.activo,
        )
        await self.proveedor_repo.crear(nuevo)
        await self.db.commit()
        await self.db.refresh(nuevo)
        return ProveedorDTO.model_validate(nuevo)

    async def listar(self, solo_activos: bool = False) -> List[ProveedorDTO]:
        proveedores = await self.proveedor_repo.listar(solo_activos=solo_activos)
        return [ProveedorDTO.model_validate(p) for p in proveedores]

    async def obtenerPorId(self, proveedor_id: uuid.UUID) -> ProveedorDTO:
        proveedor = await self.proveedor_repo.buscarPorId(proveedor_id)
        if not proveedor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado")
        return ProveedorDTO.model_validate(proveedor)
