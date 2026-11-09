"""Router Posventa: Cambio de Prenda — CU08.

Rutas:
- POST /cambios
- POST /cambios/{cambio_id}/resolver-diferencia
- GET /cambios/{cambio_id}
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.posventa.services.cambio_service import (
    CambioDTO,
    CambioService,
    CambioSolicitudDTO,
    ResolverDiferenciaDTO,
)

router = APIRouter()


@router.get(
    "/mios",
    response_model=List[CambioDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar cambios propios (CU08)",
)
async def listar_mis_cambios(
    limite: int = Query(50, ge=1, le=100),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> List[CambioDTO]:
    return await CambioService(db).listar_mios(
        usuario, limite=limite, desplazamiento=desplazamiento
    )


@router.post(
    "",
    response_model=CambioDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar cambio de prenda (CU08)",
    description=(
        "Cliente o Encargado. Solicita cambio dentro de los 15 días desde entrega. "
        "Calcula valor reconocido de prendas originales y cotiza reemplazos emitiendo "
        "una nota de cambio vigente por 7 días. Requiere header Idempotency-Key."
    ),
)
async def solicitar_cambio(
    datos: CambioSolicitudDTO,
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> CambioDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = CambioService(db)
    return await servicio.solicitar(usuario, datos, clave)


@router.post(
    "/{cambio_id}/resolver-diferencia",
    response_model=CambioDTO,
    status_code=status.HTTP_200_OK,
    summary="Resolver diferencia financiera de cambio (CU08)",
    description=(
        "Resuelve la diferencia según las reglas contractuales: si hay reemplazo con saldo a favor "
        "del cliente, éste elige SALDO o REEMBOLSO (nunca ambos por el mismo importe). "
        "Si la diferencia es a favor de la tienda, exige PAGO_CLIENTE. Requiere header Idempotency-Key."
    ),
)
async def resolver_diferencia(
    cambio_id: uuid.UUID,
    datos: ResolverDiferenciaDTO,
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> CambioDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = CambioService(db)
    return await servicio.resolver_diferencia(usuario, cambio_id, datos, clave)


@router.get(
    "/{cambio_id}",
    response_model=CambioDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar cambio de prenda por ID (CU08)",
)
async def obtener_cambio(
    cambio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> CambioDTO:
    servicio = CambioService(db)
    return await servicio.obtener_por_id(usuario, cambio_id)
