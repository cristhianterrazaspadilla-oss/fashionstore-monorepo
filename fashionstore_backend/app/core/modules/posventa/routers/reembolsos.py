"""Router Posventa: Gestión de Reembolsos — CU27 (B1 Finanzas).

Endpoints:
- POST /reembolsos
- GET /reembolsos/{reembolso_id}
- POST /reembolsos/{reembolso_id}/autorizar
- POST /reembolsos/{reembolso_id}/ejecutar
- POST /reembolsos/{reembolso_id}/conciliar
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.posventa.schemas import (
    ReembolsoAutorizarDTO,
    ReembolsoDetalleDTO,
    ReembolsoEjecutarDTO,
    ReembolsoSolicitudDTO,
)
from backend.app.core.modules.posventa.services.reembolso_service import ReembolsoService
from backend.app.core.errores import (
    E400, E401, E403, E404, E409_NEGOCIO,
)

router = APIRouter()


@router.get(
    "/mios",
    response_model=List[ReembolsoDetalleDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar reembolsos propios (CU27)",
)
async def listar_mis_reembolsos(
    limite: int = Query(50, ge=1, le=100),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> List[ReembolsoDetalleDTO]:
    return await ReembolsoService(db).listar_mios(
        usuario, limite=limite, desplazamiento=desplazamiento
    )


@router.post(
    "",
    response_model=ReembolsoDetalleDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar reembolso (CU27)",
    description="Deriva componentes y pagos capturados en servidor. Devuelve por medio original. Requiere header Idempotency-Key.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO},
)
@router.post(
    "/",
    response_model=ReembolsoDetalleDTO,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def solicitarReembolso(
    datos: ReembolsoSolicitudDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> ReembolsoDetalleDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    return await ReembolsoService(db).solicitar_reembolso(
        usuario=usuario,
        datos=datos,
        clave_idempotencia=clave,
    )


@router.get(
    "/{reembolso_id}",
    response_model=ReembolsoDetalleDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar detalle de reembolso (CU27)",
    description="Cliente titular o personal autorizado (Encargado / Administrador).",
    responses={401: E401, 403: E403, 404: E404},
)
async def consultarReembolso(
    reembolso_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReembolsoDetalleDTO:
    return await ReembolsoService(db).obtener_reembolso(usuario=usuario, reembolso_id=reembolso_id)


@router.post(
    "/{reembolso_id}/autorizar",
    response_model=ReembolsoDetalleDTO,
    status_code=status.HTTP_200_OK,
    summary="Autorizar reembolso (CU27)",
    description="Solo Encargado o Administrador. Transiciona la obligación a AUTORIZADO. Requiere header Idempotency-Key.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO},
)
async def autorizarReembolso(
    reembolso_id: uuid.UUID,
    datos: Optional[ReembolsoAutorizarDTO] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> ReembolsoDetalleDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    motivo = datos.motivo_aprobacion if datos else None
    return await ReembolsoService(db).autorizar_reembolso(
        usuario=usuario,
        reembolso_id=reembolso_id,
        clave_idempotencia=clave,
        motivo=motivo,
    )


@router.post(
    "/{reembolso_id}/ejecutar",
    response_model=ReembolsoDetalleDTO,
    status_code=status.HTTP_200_OK,
    summary="Ejecutar desembolso de reembolso (CU27)",
    description="Solo Encargado o Administrador. Devuelve a pasarela (centavos originales) o restaura saldo. No muta stock. Requiere header Idempotency-Key.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO},
)
async def ejecutarReembolso(
    reembolso_id: uuid.UUID,
    datos: ReembolsoEjecutarDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> ReembolsoDetalleDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    return await ReembolsoService(db).ejecutar_reembolso(
        usuario=usuario,
        reembolso_id=reembolso_id,
        clave_ejecucion=datos.clave_ejecucion,
        clave_idempotencia=clave,
    )


@router.post(
    "/{reembolso_id}/conciliar",
    response_model=ReembolsoDetalleDTO,
    status_code=status.HTTP_200_OK,
    summary="Conciliar reembolso incierto (CU27)",
    description="Solo Administrador. Reconcilia pagos o retenciones inciertas. Requiere header Idempotency-Key.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO},
)
async def conciliarReembolso(
    reembolso_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> ReembolsoDetalleDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    return await ReembolsoService(db).conciliar_reembolso(
        usuario=usuario,
        reembolso_id=reembolso_id,
        clave_idempotencia=clave,
    )
