"""Router para sincronización offline (CU04 / C34).

Endpoints:
- GET /api/v1/sincronizacion/referencia-horaria
- POST /api/v1/sincronizacion/operaciones
- GET /api/v1/sincronizacion/operaciones/{operacion_id}
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, Query, status
from backend.app.core.idempotencia import validar_clave_idempotencia
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.reservas_traslados.schemas_sincronizacion import (
    ConflictoOperacionModificadaDTO,
    ErrorOperacionModificadaDTO,
    OperacionDTO,
    ReferenciaHorariaDTO,
    ReferenciaHorariaCrearDTO,
    ReferenciaHorariaDetalleDTO,
    ResultadoOperacionDTO,
)
from backend.app.core.modules.reservas_traslados.services.sincronizacion_service import SincronizacionService

router = APIRouter()


@router.get(
    "/referencia-horaria",
    response_model=ReferenciaHorariaDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener referencia horaria del servidor central (CU04 / C34)",
    description=(
        "Emite una referencia horaria válida por 8 horas para creación de operaciones offline. "
        "Permite sincronizar posteriormente validando la fecha de creación dentro de dicha ventana."
    ),
)
async def obtenerReferenciaHoraria(
    dispositivo_id: Optional[uuid.UUID] = Query(None, description="UUID del dispositivo móvil o cliente web"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReferenciaHorariaDTO:
    servicio = SincronizacionService(db)
    return await servicio.emitirReferenciaHoraria(usuario, dispositivo_id=dispositivo_id)



@router.post(
    "/referencias-horarias",
    response_model=ReferenciaHorariaDetalleDTO,
    status_code=status.HTTP_200_OK,
    summary="Registrar/obtener referencia horaria sincronizada con el dispositivo (CU04 / C34)",
    description=(
        "Emite una referencia horaria vinculada a la empresa, usuario y dispositivo de la sesión. "
        "Exige Idempotency-Key y hora_local_en con offset de Bolivia. Valida tolerancia de 5 min. "
        "Fechas retornadas con offset America/La_Paz (-04:00)."
    ),
)
async def registrarReferenciaHoraria(
    datos: ReferenciaHorariaCrearDTO,
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReferenciaHorariaDetalleDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = SincronizacionService(db)
    return await servicio.crearReferenciaHoraria(usuario, datos, clave)


@router.post(
    "/operaciones",
    response_model=ResultadoOperacionDTO,
    status_code=status.HTTP_200_OK,
    responses={
        409: {"model": ErrorOperacionModificadaDTO, "description": "OPERACION_MODIFICADA"},
    },
    summary="Sincronizar operación diferida (CU04 / RF-SP-04 / RF-SP-11 / RF-SP-12)",
    description=(
        "Procesa una operación offline con semántica de una transacción por solicitud. "
        "Devuelve HTTP 200 con resultado durable incluso ante rechazo comercial (SIN_STOCK, SOLICITUD_VENCIDA) "
        "o conflicto temporal (TIEMPO_INCOHERENTE). Misma clave UUID con cuerpo idéntico devuelve el resultado "
        "persistido; misma clave con cuerpo distinto devuelve 409 OPERACION_MODIFICADA."
    ),
)
async def sincronizarOperacion(
    datos: OperacionDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ResultadoOperacionDTO:
    servicio = SincronizacionService(db)
    return await servicio.procesarOperacion(usuario, datos)


@router.get(
    "/operaciones/{operacion_id}",
    response_model=ResultadoOperacionDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar resultado durable de una operación por UUID (CU04)",
    description="Devuelve el resultado persistido de la operación dentro del ámbito de la empresa y actor autenticado (404 si es ajena o inexistente).",
)
async def consultarOperacion(
    operacion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ResultadoOperacionDTO:
    servicio = SincronizacionService(db)
    return await servicio.consultarOperacion(usuario, operacion_id)
