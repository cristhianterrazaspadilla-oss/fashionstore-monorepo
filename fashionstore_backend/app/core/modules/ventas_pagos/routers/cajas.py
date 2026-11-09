"""Router de Caja Offline y Turnos — CU06 y CU07."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual, require_rol_empresarial
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.ventas_pagos.schemas import (
    TurnoCrearDTO,
    TurnoHabilitacionDTO,
    VentaOfflineCrearDTO,
    VentaOfflineResultadoDTO,
    TurnoCerrarDTO,
    TurnoCerradoDTO,
    TurnoRecuperarDTO,
)
from backend.app.core.modules.ventas_pagos.services.caja_service import CajaService

router = APIRouter(prefix="/cajas", tags=["Cajas y Turnos Offline"])

ROLES_OPERACION_CAJA = ("CAJERO", "ADMINISTRADOR", "PROPIETARIO", "ENCARGADO")
ROLES_SUPERVISION_CAJA = ("ADMINISTRADOR", "PROPIETARIO", "ENCARGADO")


@router.post(
    "/turnos",
    response_model=TurnoHabilitacionDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Habilitar turno de caja online con asignación de cupos exclusivos (CU06)",
    description="Asigna cupos exclusivos todo o nada a la caja deduciendo del libre e incrementando comprometido_caja. Requiere Idempotency-Key.",
)
async def habilitar_turno(
    dto: TurnoCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol_empresarial(*ROLES_OPERACION_CAJA)),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> TurnoHabilitacionDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = CajaService(db)
    return await servicio.habilitar_turno(dto, usuario, clave)


@router.get(
    "/turnos/activo",
    response_model=Optional[TurnoHabilitacionDTO],
    summary="Consultar turno activo del usuario o dispositivo (CU06)",
)
async def consultar_turno_activo(
    dispositivo_id: Optional[uuid.UUID] = Query(None, description="Filtrar por dispositivo específico"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol_empresarial(*ROLES_OPERACION_CAJA)),
) -> Optional[TurnoHabilitacionDTO]:
    servicio = CajaService(db)
    return await servicio.obtener_turno_activo(usuario, dispositivo_id=dispositivo_id)


@router.get(
    "/turnos/{turno_id}",
    response_model=TurnoHabilitacionDTO,
    summary="Consultar turno específico por ID (CU06)",
)
async def consultar_turno(
    turno_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol_empresarial(*ROLES_OPERACION_CAJA)),
) -> TurnoHabilitacionDTO:
    servicio = CajaService(db)
    return await servicio.obtener_turno(turno_id, usuario)


@router.post(
    "/turnos/{turno_id}/ventas",
    response_model=VentaOfflineResultadoDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Sincronizar venta offline en efectivo (CU07)",
    description="Registra la venta física efectuada offline en efectivo, valida y descuenta cupo local, registra pago en efectivo y movimiento de Kardex sin doble descuento.",
)
async def registrar_venta_offline(
    turno_id: uuid.UUID,
    dto: VentaOfflineCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol_empresarial(*ROLES_OPERACION_CAJA)),
) -> VentaOfflineResultadoDTO:
    servicio = CajaService(db)
    return await servicio.registrar_venta_offline(turno_id, dto, usuario)


@router.post(
    "/turnos/{turno_id}/cerrar",
    response_model=TurnoCerradoDTO,
    status_code=status.HTTP_200_OK,
    summary="Cerrar turno de caja y conciliar cupos sobrantes (CU06/CU07)",
    description="Cierra el turno supervisado. Si hay operaciones pendientes pasa a CONCILIACION. Si está limpio, devuelve cupos no consumidos al disponible libre.",
)
async def cerrar_turno(
    turno_id: uuid.UUID,
    dto: TurnoCerrarDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol_empresarial(*ROLES_OPERACION_CAJA)),
) -> TurnoCerradoDTO:
    servicio = CajaService(db)
    return await servicio.cerrar_turno(turno_id, dto, usuario)


@router.post(
    "/turnos/{turno_id}/recuperar",
    status_code=status.HTTP_200_OK,
    summary="Recuperar turno por caja perdida o fallo irrecuperable (CU06)",
    description="Pasa el turno a RECUPERACION congelando cupos para resolución manual supervisada.",
)
async def recuperar_turno(
    turno_id: uuid.UUID,
    dto: TurnoRecuperarDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol_empresarial(*ROLES_SUPERVISION_CAJA)),
) -> dict:
    servicio = CajaService(db)
    return await servicio.recuperar_turno(turno_id, dto, usuario)
