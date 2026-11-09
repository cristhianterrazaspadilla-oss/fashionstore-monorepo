from fastapi import APIRouter, Depends, Query, status
from typing import Optional
from datetime import datetime
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.identidad_empresas.schemas import RegistroClienteDTO, ClientePerfilDTO
from backend.app.core.modules.ventas_pagos.schemas import HistorialComprasDTO
from backend.app.core.modules.identidad_empresas.services.cliente_service import ClienteService
from backend.app.core.modules.ventas_pagos.services.venta_service import VentaService

router = APIRouter()


@router.post(
    "",
    response_model=ClientePerfilDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nuevo cliente (CU01 / RF01)",
    description="Crea una nueva cuenta de cliente con rol CLIENTE y estado ACTIVO tras validar que el correo no esté duplicado."
)
async def registrarCliente(
    datos_registro: RegistroClienteDTO,
    db: AsyncSession = Depends(get_db)
) -> ClientePerfilDTO:
    servicio = ClienteService(db)
    return await servicio.registrar(datos_registro)


@router.get(
    "/{cliente_id}/compras",
    response_model=HistorialComprasDTO,
    status_code=status.HTTP_200_OK,
    summary="Historial de compras del cliente (CU13 / RF16)",
    description="Presentación consultarHistorialCompras() -> Controller VentaService.historialCliente(). Propietario o Administrador (otro cliente -> 403). Filtros por rango de fechas; orden creada_en desc; paginado limit/offset. Costos congelados solo para Administrador."
)
async def consultarHistorialCompras(
    cliente_id: uuid.UUID,
    desde: Optional[datetime] = Query(None, description="Fecha inicial (UTC, inclusiva)"),
    hasta: Optional[datetime] = Query(None, description="Fecha final (UTC, inclusiva)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual)
) -> HistorialComprasDTO:
    servicio = VentaService(db)
    return await servicio.historialCliente(
        usuario, cliente_id, desde=desde, hasta=hasta, limit=limit, offset=offset,
    )
