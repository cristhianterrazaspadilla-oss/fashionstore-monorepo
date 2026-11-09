"""Router Devoluciones y Mermas — CU20 y CU12.

Rutas:
- POST /devoluciones/solicitudes (CU20)
- POST /devoluciones/{devolucion_id}/inspecciones (CU20)
- GET /devoluciones/{devolucion_id} (CU20)
- POST /devoluciones (CU12 heredado)
- POST /mermas (CU20 / CU12)
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.posventa.services.devolucion_service import (
    DevolucionCrearDTO,
    DevolucionDTO,
    DevolucionService,
    DevolucionSolicitudDTO,
    InspeccionDTO,
    MermaCrearDTO,
    MermaDTO,
    MermaService,
)

router_devoluciones = APIRouter()
router_mermas = APIRouter()


@router_devoluciones.get(
    "/mias",
    response_model=List[DevolucionDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar solicitudes de devolución propias (CU20)",
)
async def listar_mis_devoluciones(
    limite: int = Query(50, ge=1, le=100),
    desplazamiento: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> List[DevolucionDTO]:
    return await DevolucionService(db).listar_mias(
        usuario, limite=limite, desplazamiento=desplazamiento
    )


@router_devoluciones.post(
    "/solicitudes",
    response_model=DevolucionDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar devolución física (CU20)",
    description=(
        "Cliente o Encargado. Registra solicitud dentro de los 15 días desde entrega con comprobante. "
        "Deja la prenda en custodia no vendible sin alterar inventario disponible hasta la inspección técnica."
    ),
)
async def solicitar_devolucion(
    datos: DevolucionSolicitudDTO,
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> DevolucionDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = DevolucionService(db)
    return await servicio.solicitar(usuario, datos, clave)


@router_devoluciones.post(
    "/{devolucion_id}/inspecciones",
    response_model=DevolucionDTO,
    status_code=status.HTTP_200_OK,
    summary="Recepción e inspección técnica de devolución (CU20)",
    description=(
        "Encargado o Administrador. Dictamina APTA_REPOSICION (reingresa a disponible con Kardex DEVOLUCION), "
        "APROBADA_REEMBOLSO (queda en cuarentena para resolución financiera) o RECHAZADA."
    ),
)
async def inspeccionar_devolucion(
    devolucion_id: uuid.UUID,
    datos: InspeccionDTO,
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> DevolucionDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = DevolucionService(db)
    return await servicio.inspeccionar(usuario, devolucion_id, datos, clave)


@router_devoluciones.get(
    "/{devolucion_id}",
    response_model=DevolucionDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar devolución por ID (CU20)",
)
async def obtener_devolucion(
    devolucion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> DevolucionDTO:
    servicio = DevolucionService(db)
    return await servicio.obtener_por_id(usuario, devolucion_id)


@router_devoluciones.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Registrar devolución parcial heredada (CU12)",
)
async def registrar_devolucion_heredada(
    datos: DevolucionCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = DevolucionService(db)
    devolucion, _ = await servicio.registrar(usuario, datos, clave)
    return devolucion


@router_mermas.post(
    "",
    response_model=MermaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar merma auditada (CU20 / CU12)",
    description="Encargado o Administrador. Reduce existencia disponible y emite Kardex MERMA.",
)
async def registrar_merma(
    datos: MermaCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> MermaDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = MermaService(db)
    return await servicio.registrar(usuario, datos, clave)
