"""Presentación Dashboard — CU19 (RF24). Se monta bajo /reportes."""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.analitica.schemas import DashboardDTO
from backend.app.core.modules.analitica.services.dashboard_service import DashboardService
from backend.app.core.errores import E400, E401, E403, E404

router = APIRouter()


@router.get(
    "/dashboard", response_model=DashboardDTO,
    summary="Dashboard e indicadores (CU19)",
    description="Ventas, ingresos y margen por periodo/sucursal, ticket promedio, top productos, "
    "stock crítico y valorización, conversión de reservas, estados de pedidos y efectividad de "
    "promociones. Todos los indicadores aplicables respetan desde/hasta/sucursal_id en UTC con "
    "desde<=hasta. RBAC (ADMIN global; ENCARGADO su sucursal) y respuestas tipadas con Decimal.",
    responses={400: E400, 401: E401, 403: E403, 404: E404},
)
async def consultarDashboard(
    desde: Optional[datetime] = Query(None),
    hasta: Optional[datetime] = Query(None),
    sucursal_id: Optional[uuid.UUID] = Query(None, alias="sucursal"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> DashboardDTO:
    return await DashboardService(db).indicadores(
        usuario, desde=desde, hasta=hasta, sucursal_id=sucursal_id
    )
