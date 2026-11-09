"""Router de Modelos de Machine Learning — CU10 (Pronóstico) y CU11 (Segmentación)."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.errores import E400, E401, E403, E404
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.analitica.schemas import (
    PronosticoDemandaPeticionDTO,
    PronosticoDemandaResultadoDTO,
    SegmentacionProductosPeticionDTO,
    SegmentacionProductosResultadoDTO,
)
from backend.app.core.modules.analitica.services.ml_service import MLService

router = APIRouter()


@router.get(
    "/pronosticos",
    response_model=PronosticoDemandaResultadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar pronósticos supervisados de demanda (CU10)",
    description="Solo Administrador empresarial. Proyección semanal por producto y sucursal sobre datos reales.",
    responses={400: E400, 401: E401, 403: E403, 404: E404},
)
async def consultarPronosticos(
    sucursal_id: Optional[uuid.UUID] = Query(None, alias="sucursal"),
    producto_id: Optional[uuid.UUID] = Query(None, alias="producto"),
    semanas: int = Query(4, ge=1, le=12),
    origen_datos: str = Query("AUTO"),
    semilla: int = Query(42),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> PronosticoDemandaResultadoDTO:
    dto = PronosticoDemandaPeticionDTO(
        sucursal_id=sucursal_id,
        producto_id=producto_id,
        semanas_adelante=semanas,
        origen_datos=origen_datos,
        semilla=semilla,
    )
    return await MLService(db).pronosticoDemanda(usuario, dto)


@router.post(
    "/entrenamientos/supervisado",
    response_model=PronosticoDemandaResultadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Entrenar modelo supervisado de demanda (CU10)",
    responses={400: E400, 401: E401, 403: E403, 404: E404},
)
async def entrenarSupervisado(
    datos: PronosticoDemandaPeticionDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> PronosticoDemandaResultadoDTO:
    return await MLService(db).pronosticoDemanda(usuario, datos)


@router.get(
    "/grupos-productos",
    response_model=SegmentacionProductosResultadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar segmentación no supervisada de productos (CU11)",
    description="Solo Administrador empresarial. Clústeres de productos por rotación y ventas con métricas y centroides.",
    responses={400: E400, 401: E401, 403: E403, 404: E404},
)
async def consultarSegmentacion(
    num_grupos: int = Query(4, ge=2, le=8),
    periodo_dias: int = Query(60, ge=7, le=365),
    origen_datos: str = Query("AUTO"),
    semilla: int = Query(42),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> SegmentacionProductosResultadoDTO:
    dto = SegmentacionProductosPeticionDTO(
        num_grupos=num_grupos,
        periodo_dias=periodo_dias,
        origen_datos=origen_datos,
        semilla=semilla,
    )
    return await MLService(db).segmentacionProductos(usuario, dto)


@router.post(
    "/entrenamientos/no-supervisado",
    response_model=SegmentacionProductosResultadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Entrenar segmentación no supervisada de productos (CU11)",
    responses={400: E400, 401: E401, 403: E403, 404: E404},
)
async def entrenarNoSupervisado(
    datos: SegmentacionProductosPeticionDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> SegmentacionProductosResultadoDTO:
    return await MLService(db).segmentacionProductos(usuario, datos)
