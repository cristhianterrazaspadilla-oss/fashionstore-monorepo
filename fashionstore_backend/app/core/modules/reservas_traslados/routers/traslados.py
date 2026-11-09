"""Presentacion Traslados — CU09 (RF21, RF22).

  solicitarTraslado() -> POST /traslados/solicitudes (reintento de linea RECHAZADA)
  aprobarTraslado() -> PATCH /traslados/{id}/aprobar (origen)
  despacharTraslado() -> PATCH /traslados/{id}/despachar (origen)
  recibirTraslado() -> PATCH /traslados/{id}/recibir (destino)
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.reservas_traslados.schemas import TrasladoDTO, TrasladoListaDTO, TrasladoRechazarDTO, TrasladoSolicitarDTO
from backend.app.core.modules.reservas_traslados.services.traslado_service import TrasladoService

router = APIRouter()


@router.post(
    "/solicitudes",
    response_model=TrasladoDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar traslado para una linea rechazada (CU09)",
    description="Reintento con otro origen antes del vencimiento (misma variante y cantidad). Requiere header Idempotency-Key. Origen con stock insuficiente -> 409; linea no rechazada o traslado activo -> 409.",
)
async def solicitarTraslado(
    datos: TrasladoSolicitarDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> TrasladoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = TrasladoService(db)
    traslado, _ = await servicio.solicitar(usuario, datos, clave)
    return traslado


@router.get(
    "",
    response_model=TrasladoListaDTO,
    summary="Listar traslados por estado, sucursal o reserva (CU09)",
    description="Cliente: exige reserva_id propia. Encargado: exige filtro por su sucursal. Administrador: libre. Orden fecha_solicitud desc. Paginado con total/limit/offset.",
)
async def listarTraslados(
    estado: Optional[str] = Query(None),
    sucursal_origen_id: Optional[uuid.UUID] = Query(None),
    sucursal_destino_id: Optional[uuid.UUID] = Query(None),
    reserva_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> TrasladoListaDTO:
    servicio = TrasladoService(db)
    return await servicio.listar(
        usuario, estado=estado, sucursal_origen_id=sucursal_origen_id,
        sucursal_destino_id=sucursal_destino_id, reserva_id=reserva_id,
        limit=limit, offset=offset,
    )


@router.get(
    "/{traslado_id}",
    response_model=TrasladoDTO,
    summary="Consultar traslado por id (CU09)",
)
async def consultarTraslado(
    traslado_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> TrasladoDTO:
    servicio = TrasladoService(db)
    return await servicio.obtener(usuario, traslado_id)


@router.patch(
    "/{traslado_id}/aprobar",
    response_model=TrasladoDTO,
    summary="Aprobar traslado (CU09)",
    description="Encargado de origen o Administrador. Mueve disponible->comprometido en origen con Kardex COMPROMISO_TRASLADO. Repetir es idempotente; otro estado -> 409.",
)
async def aprobarTraslado(
    traslado_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> TrasladoDTO:
    servicio = TrasladoService(db)
    return await servicio.aprobar(usuario, traslado_id)


@router.patch(
    "/{traslado_id}/rechazar",
    response_model=TrasladoDTO,
    summary="Rechazar traslado por linea (CU09)",
    description="Encargado de origen o Administrador, solo desde SOLICITADO (despues de aprobar -> 409). Marca la linea RECHAZADA; si no quedan pendientes y hay lineas atendibles la reserva pasa a PENDIENTE; si todas quedan rechazadas se CANCELA y libera lo local.",
)
async def rechazarTraslado(
    traslado_id: uuid.UUID,
    datos: TrasladoRechazarDTO = TrasladoRechazarDTO(),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> TrasladoDTO:
    servicio = TrasladoService(db)
    return await servicio.rechazar(usuario, traslado_id, datos)


@router.patch(
    "/{traslado_id}/despachar",
    response_model=TrasladoDTO,
    summary="Despachar traslado (CU09)",
    description="Encargado de origen o Administrador, solo desde APROBADO. Mueve comprometido->en_transito en origen con Kardex DESPACHO_TRASLADO. Repetir es idempotente.",
)
async def despacharTraslado(
    traslado_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> TrasladoDTO:
    servicio = TrasladoService(db)
    return await servicio.despachar(usuario, traslado_id)


@router.patch(
    "/{traslado_id}/recibir",
    response_model=TrasladoDTO,
    summary="Recibir traslado en destino (CU09)",
    description="Encargado de destino o Administrador, solo desde DESPACHADO (antes -> 409). Con reserva activa: transito->reservado en destino; con reserva cancelada/vencida: queda disponible en destino. Kardex RECEPCION_TRASLADO unico. Repetir es idempotente.",
)
async def recibirTraslado(
    traslado_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> TrasladoDTO:
    servicio = TrasladoService(db)
    return await servicio.recibir(usuario, traslado_id)
