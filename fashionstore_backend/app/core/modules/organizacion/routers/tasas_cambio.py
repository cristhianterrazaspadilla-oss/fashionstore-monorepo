"""Router de Tasa de Cambio BOB/USD — CU12."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual, require_administrador_plataforma
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.organizacion.schemas import (
    TasaCambioCrearDTO,
    TasaCambioDTO,
    CotizacionMonedaDTO,
)
from backend.app.core.modules.organizacion.services.tasa_cambio_service import TasaCambioService

router = APIRouter()


@router.post(
    "",
    response_model=TasaCambioDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nueva tasa de cambio BOB/USD (CU12)",
    description="Solo el Administrador de Plataforma puede configurar la tasa oficial. Exige clave de idempotencia.",
)
async def registrar_tasa_cambio(
    dto: TasaCambioCrearDTO,
    idempotency_key: uuid.UUID = Header(..., alias="Idempotency-Key", description="Clave de idempotencia obligatoria"),
    db: AsyncSession = Depends(get_db),
    admin_plataforma: Usuario = Depends(require_administrador_plataforma()),
) -> TasaCambioDTO:
    servicio = TasaCambioService(db)
    return await servicio.crear_tasa(
        dto=dto,
        admin_plataforma=admin_plataforma,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/vigente",
    response_model=TasaCambioDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar tasa de cambio BOB/USD vigente (CU12)",
    description="Retorna la tasa vigente activa en la plataforma sin vigencias solapadas.",
)
async def obtener_tasa_vigente(
    momento: Optional[datetime] = Query(None, description="Momento temporal de consulta"),
    db: AsyncSession = Depends(get_db),
) -> TasaCambioDTO:
    servicio = TasaCambioService(db)
    return await servicio.obtener_tasa_vigente(momento)


@router.get(
    "/cotizar",
    response_model=CotizacionMonedaDTO,
    status_code=status.HTTP_200_OK,
    summary="Cotizar importe BOB a USD con redondeo HALF_UP a centavos (CU12)",
)
async def cotizar_moneda(
    monto_bob: Decimal = Query(..., gt=0, description="Importe en Bolivianos (BOB) a cotizar"),
    momento: Optional[datetime] = Query(None, description="Momento temporal para cotización histórica"),
    db: AsyncSession = Depends(get_db),
) -> CotizacionMonedaDTO:
    servicio = TasaCambioService(db)
    return await servicio.cotizar(monto_bob, momento=momento)


@router.get(
    "",
    response_model=List[TasaCambioDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar historial de tasas de cambio (CU12)",
)
async def listar_historial_tasas(
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(get_usuario_actual),
) -> List[TasaCambioDTO]:
    servicio = TasaCambioService(db)
    return await servicio.listar_historial()
