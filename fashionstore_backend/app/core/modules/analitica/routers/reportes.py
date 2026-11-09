"""Presentacion Reportes — CU23 (RF24).

  consultarVentasSucursal() -> GET /reportes/ventas-sucursal
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.analitica.schemas import VentasSucursalDTO
from backend.app.core.modules.analitica.services.reporte_service import ReporteService

router = APIRouter()


@router.get(
    "/ventas-sucursal",
    response_model=VentasSucursalDTO,
    status_code=status.HTTP_200_OK,
    summary="Ventas de la sucursal por rango (CU23 / RF24)",
    description="Presentación consultarVentasSucursal() -> Controller ReporteService.ventasPorSucursal(). Encargado: solo su sucursal (otra -> 403). Administrador: cualquiera. Filtros desde/hasta (UTC, inclusivos); orden creada_en desc; paginado limit/offset. Costo total y margen bruto solo para ADMIN/ENCARGADO.",
)
async def consultarVentasSucursal(
    sucursal_id: uuid.UUID = Query(..., alias="sucursal"),
    desde: Optional[datetime] = Query(None, description="Fecha inicial (UTC, inclusiva)"),
    hasta: Optional[datetime] = Query(None, description="Fecha final (UTC, inclusiva)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> VentasSucursalDTO:
    servicio = ReporteService(db)
    return await servicio.ventasPorSucursal(
        usuario, sucursal_id, desde=desde, hasta=hasta, limit=limit, offset=offset
    )
