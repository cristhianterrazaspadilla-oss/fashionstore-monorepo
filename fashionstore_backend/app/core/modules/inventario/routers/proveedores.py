from typing import List
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import require_rol_empresarial
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.inventario.schemas import ProveedorCrearDTO, ProveedorDTO
from backend.app.core.modules.inventario.services.proveedor_service import ProveedorService

router = APIRouter()

@router.post(
    "",
    response_model=ProveedorDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar proveedor (CU04 / RF06)",
    description="Presentación gestionarProveedores() -> Controller ProveedorService.crear() -> Datos ProveedorRepository.crear()"
)
async def gestionarProveedores(
    datos: ProveedorCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> ProveedorDTO:
    servicio = ProveedorService(db, empresa_id=_admin.empresa_id)
    return await servicio.crear(datos)

@router.get(
    "",
    response_model=List[ProveedorDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar proveedores (CU04)",
)
async def listarProveedores(
    solo_activos: bool = Query(False, description="Filtrar solo activos"),
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR", "ENCARGADO"))
) -> List[ProveedorDTO]:
    servicio = ProveedorService(db, empresa_id=_user.empresa_id)
    return await servicio.listar(solo_activos=solo_activos)
