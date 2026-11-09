import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual, require_administrador_plataforma
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.organizacion.schemas import CiudadCrearDTO, CiudadActualizarDTO, CiudadDTO
from backend.app.core.modules.organizacion.services.ciudad_service import CiudadService

router = APIRouter()


@router.post(
    "",
    response_model=CiudadDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nueva ciudad (CU15 / CU03)",
    description="Solo el Administrador de Plataforma administra el catálogo global de ciudades.",
)
async def registrarCiudad(
    datos_ciudad: CiudadCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin_plataforma: Usuario = Depends(require_administrador_plataforma()),
) -> CiudadDTO:
    servicio = CiudadService(db)
    return await servicio.crear(datos_ciudad)


@router.patch(
    "/{ciudad_id}",
    response_model=CiudadDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar ciudad (CU15)",
    description="Solo el Administrador de Plataforma puede modificar una ciudad global.",
)
async def actualizarCiudad(
    ciudad_id: uuid.UUID,
    datos_ciudad: CiudadActualizarDTO,
    db: AsyncSession = Depends(get_db),
    _admin_plataforma: Usuario = Depends(require_administrador_plataforma()),
) -> CiudadDTO:
    servicio = CiudadService(db)
    return await servicio.actualizar(ciudad_id, datos_ciudad)


@router.get(
    "",
    response_model=List[CiudadDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar ciudades registradas (CU15 / CU03)",
    description="Retorna la lista de ciudades activas en la plataforma.",
)
async def listarCiudades(
    solo_activas: bool = True,
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(get_usuario_actual),
) -> List[CiudadDTO]:
    servicio = CiudadService(db)
    return await servicio.listar(solo_activas=solo_activas)


@router.get(
    "/{ciudad_id}",
    response_model=CiudadDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener detalle de ciudad por ID (CU15 / CU03)",
)
async def obtenerCiudadPorId(
    ciudad_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(get_usuario_actual),
) -> CiudadDTO:
    servicio = CiudadService(db)
    return await servicio.obtenerPorId(ciudad_id)
