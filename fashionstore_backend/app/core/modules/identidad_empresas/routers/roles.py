from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.identidad_empresas.schemas import RolDTO
from backend.app.core.modules.identidad_empresas.services.rol_service import RolService

router = APIRouter()


@router.get(
    "",
    response_model=List[RolDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar roles del sistema (CU02 / RF02)",
    description="Retorna la lista de roles activos definidos en el sistema (ADMINISTRADOR, ENCARGADO, CAJERO, PROVEEDOR, CLIENTE)."
)
async def listarRoles(
    solo_activos: bool = True,
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(get_usuario_actual)
) -> List[RolDTO]:
    servicio = RolService(db)
    return await servicio.listar(solo_activos=solo_activos)
