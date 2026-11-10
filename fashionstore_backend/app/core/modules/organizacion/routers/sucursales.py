"""Router de Sucursales y Tarifas de Delivery — CU15 / CU03."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import require_rol_empresarial, get_usuario_actual
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.organizacion.schemas import (
    SucursalCrearDTO,
    SucursalActualizarDTO,
    SucursalDTO,
    ConfigurarTarifasDeliveryDTO,
    ConfigurarAdelantoDTO,
)
from backend.app.core.modules.organizacion.services.sucursal_service import SucursalService

router = APIRouter()


@router.post(
    "",
    response_model=SucursalDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nueva sucursal (CU15 / CU03)",
    description="Permite al Administrador registrar una sucursal con control de límite de plan bajo concurrencia.",
)
async def registrarSucursal(
    datos_sucursal: SucursalCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR")),
) -> SucursalDTO:
    servicio = SucursalService(db)
    return await servicio.crear(datos_sucursal, _admin)


@router.patch(
    "/{sucursal_id}",
    response_model=SucursalDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar sucursal y estado (CU15)",
    description="Permite modificar datos o activar/desactivar la sucursal con control optimista de revisión y comprobación de compromisos.",
)
async def actualizarSucursal(
    sucursal_id: uuid.UUID,
    datos_sucursal: SucursalActualizarDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR")),
) -> SucursalDTO:
    servicio = SucursalService(db)
    return await servicio.actualizar(sucursal_id, datos_sucursal, _admin)


@router.get(
    "",
    response_model=List[SucursalDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar sucursales (CU15 / CU03)",
    description="Retorna las sucursales del ámbito del usuario con opción de filtrar por ciudad_id.",
)
async def gestionarSucursales(
    ciudad_id: Optional[uuid.UUID] = Query(None, description="Filtrar sucursales por ID de ciudad"),
    solo_activas: bool = True,
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(get_usuario_actual),
) -> List[SucursalDTO]:
    servicio = SucursalService(db)
    return await servicio.listar(_user, ciudad_id=ciudad_id, solo_activas=solo_activas)


@router.get(
    "/{sucursal_id}",
    response_model=SucursalDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener detalle de sucursal (CU15 / CU03)",
)
async def obtenerSucursalPorId(
    sucursal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(get_usuario_actual),
) -> SucursalDTO:
    servicio = SucursalService(db)
    return await servicio.obtenerPorId(sucursal_id, _user)


@router.patch(
    "/{sucursal_id}/tarifas",
    response_model=SucursalDTO,
    status_code=status.HTTP_200_OK,
    summary="Configurar tarifas y cobertura de delivery por anillos (CU15 / CU03)",
    description="Actualiza la tarifa base, incremento por anillo y rango de cobertura de delivery para la sucursal.",
)
async def configurarTarifasDelivery(
    sucursal_id: uuid.UUID,
    datos_tarifas: ConfigurarTarifasDeliveryDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR")),
) -> SucursalDTO:
    servicio = SucursalService(db)
    return await servicio.actualizarTarifas(sucursal_id, datos_tarifas, _admin)


@router.patch(
    "/{sucursal_id}/adelanto",
    response_model=SucursalDTO,
    status_code=status.HTTP_200_OK,
    summary="Configurar política de adelanto de la sucursal (RN-03 / CU15)",
    description="Activa o desactiva el adelanto (MONTO_FIJO o PORCENTAJE con valor).",
)
async def configurarAdelanto(
    sucursal_id: uuid.UUID,
    datos_adelanto: ConfigurarAdelantoDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR")),
) -> SucursalDTO:
    servicio = SucursalService(db)
    return await servicio.actualizarAdelanto(sucursal_id, datos_adelanto, _admin)
