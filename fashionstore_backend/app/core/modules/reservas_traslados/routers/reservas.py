"""Presentacion Reservas — CU08/CU10/CU24.

  crearBolsaReserva()/confirmarReserva() -> POST /reservas (201)
  consultarReserva() -> GET /reservas/{id} | /codigo/{codigo} | GET /reservas
  cancelarReserva() -> PATCH /reservas/{id}/cancelar (200)
  Job CU24 -> POST /reservas/expiracion/ejecutar (personal)
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual, require_rol_empresarial, require_roles
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.reservas_traslados.schemas import (
    ExpiracionResultadoDTO,
    ReservaCancelarDTO,
    ReservaCrearDTO,
    ReservaDTO,
    ReservaListaDTO,
)
from backend.app.core.modules.reservas_traslados.services.reserva_service import ReservaService

router = APIRouter()


@router.post(
    "",
    response_model=ReservaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Confirmar bolsa como reserva (CU08 / RF09-RF12)",
    description="Presentación confirmarReserva() -> Controller ReservaService.crear(). Atomica por lineas: stock local mueve disponible->reservado con Kardex RESERVA; sin stock requiere sucursal_origen_id explicito (PENDIENTE_TRASLADO). Sin stock ni origen -> 409 sin efectos. Requiere header Idempotency-Key.",
)
async def confirmarReserva(
    datos: ReservaCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol_empresarial("CLIENTE")),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> ReservaDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = ReservaService(db)
    reserva, _ = await servicio.crear(usuario, datos, clave)
    return reserva


@router.get(
    "",
    response_model=ReservaListaDTO,
    summary="Listar reservas por propietario, sucursal, estado o codigo (CU08)",
    description="Cliente: solo las propias (cliente_id ajeno -> 403). Encargado/Cajero: solo su sucursal (otra -> 403). Administrador: sin restriccion. Orden fecha_creacion desc. Paginado limit/offset.",
)
async def listarReservas(
    cliente_id: Optional[uuid.UUID] = Query(None),
    sucursal_id: Optional[uuid.UUID] = Query(None, alias="sucursal"),
    sucursal_destino_id: Optional[uuid.UUID] = Query(None),
    estado: Optional[str] = Query(None),
    codigo: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReservaListaDTO:
    servicio = ReservaService(db)
    destino = sucursal_destino_id or sucursal_id
    return await servicio.listar(
        usuario, cliente_id=cliente_id, sucursal_id=destino,
        estado=estado, codigo=codigo, limit=limit, offset=offset,
    )


@router.get(
    "/panel/cola",
    response_model=ReservaListaDTO,
    summary="Cola paginada de reservas por sucursal (CU10)",
    description="Presentación consultarPanelReservas() -> Controller ReservaService.panelSucursal(). Polling por la sucursal (sin websocket). Encargado: solo su sucursal. Filtros por estado; orden fecha_creacion desc; paginado limit/offset.",
)
async def consultarPanelReservas(
    sucursal_id: uuid.UUID = Query(..., alias="sucursal"),
    estado: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReservaListaDTO:
    servicio = ReservaService(db)
    return await servicio.panelSucursal(usuario, sucursal_id, estado=estado, limit=limit, offset=offset)


@router.get(
    "/codigo/{codigo}",
    response_model=ReservaDTO,
    summary="Localizar reserva por codigo (CU08/CU11)",
    description="Propietario o personal de la sucursal destino (otro cliente -> 403).",
)
async def localizarReservaPorCodigo(
    codigo: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReservaDTO:
    servicio = ReservaService(db)
    return await servicio.obtenerPorCodigo(usuario, codigo)


@router.get(
    "/{reserva_id}",
    response_model=ReservaDTO,
    summary="Consultar reserva por id (CU08)",
)
async def consultarReserva(
    reserva_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReservaDTO:
    servicio = ReservaService(db)
    return await servicio.obtener(usuario, reserva_id)


@router.patch(
    "/{reserva_id}/cancelar",
    response_model=ReservaDTO,
    status_code=status.HTTP_200_OK,
    summary="Cancelar reserva (CU08 / CU18)",
    description=(
        "Cliente propietario o Encargado/Administrador de la sucursal destino. "
        "Idempotente con header Idempotency-Key y control de concurrencia optimista mediante revision opcional. "
        "Si ya está CANCELADA devolver HTTP 200 idempotente sin duplicar Kardex. "
        "Si revision no coincide, responder 409 Conflict."
    ),
)
async def cancelarReserva(
    reserva_id: uuid.UUID,
    datos: Optional[ReservaCancelarDTO] = None,
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReservaDTO:
    servicio = ReservaService(db)
    revision = datos.revision if datos is not None else None
    return await servicio.cancelar(
        usuario, reserva_id, revision=revision, clave_idempotencia=clave_idempotencia
    )


@router.patch(
    "/{reserva_id}/preparar",
    response_model=ReservaDTO,
    summary="Preparar reserva en vestidor (CU10)",
    description="Encargado de la sucursal o Administrador. Solo PENDIENTE->PREPARADA; con traslados pendientes o vencida -> 409. Registra responsable y marca temporal. Repetir es idempotente.",
)
async def prepararReserva(
    reserva_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReservaDTO:
    servicio = ReservaService(db)
    return await servicio.preparar(usuario, reserva_id)


@router.patch(
    "/{reserva_id}/atender",
    response_model=ReservaDTO,
    summary="Atender reserva: cliente en vestidor (CU10)",
    description="Encargado de la sucursal o Administrador. Solo PREPARADA->ATENDIDA. Repetir es idempotente; otro origen -> 409.",
)
async def atenderReserva(
    reserva_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReservaDTO:
    servicio = ReservaService(db)
    return await servicio.atender(usuario, reserva_id)


@router.post(
    "/expiracion/ejecutar",
    response_model=ExpiracionResultadoDTO,
    summary="Ejecutar job de expiracion manualmente (CU24)",
    description="Encargado/Administrador. Procesa vencidas con advisory lock y SKIP LOCKED de forma idempotente. El scheduler automatico (cada 10 min) usa la misma funcion.",
)
async def ejecutarExpiracion(
    db: AsyncSession = Depends(get_db),
    _staff: Usuario = Depends(require_roles("ENCARGADO", "ADMINISTRADOR")),
) -> ExpiracionResultadoDTO:
    servicio = ReservaService(db)
    return await servicio.expirarVencidas(empresa_id=_staff.empresa_id)
