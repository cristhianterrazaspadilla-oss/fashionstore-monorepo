"""Router Ventas — CU11, CU13, CU23."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.ventas_pagos.schemas import ComprobanteDTO, VentaDTO, VentaPresencialCrearDTO
from backend.app.core.modules.ventas_pagos.services.venta_service import VentaService

router = APIRouter()


@router.post(
    "/presenciales",
    response_model=ComprobanteDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar venta presencial y cobro en caja (CU11)",
    description="Cajero o Administrador de la sucursal. Venta directa o desde reserva ATENDIDA vigente (otro estado -> 409). Total o parcial: lo reservado no comprado se libera con Kardex LIBERACION_RESERVA. Precio y costo congelados por linea; adelanto descontado una sola vez; un metodo de caja; venta y pago confirmado en una sola transaccion (PAGADA, sin pendientes). Requiere header Idempotency-Key.",
)
async def registrarVentaPresencial(
    datos: VentaPresencialCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> ComprobanteDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    servicio = VentaService(db)
    comprobante, _ = await servicio.registrarPresencial(usuario, datos, clave)
    return comprobante


@router.get(
    "/{venta_id}",
    response_model=VentaDTO,
    summary="Consultar venta por id (CU11/CU13)",
    description="Propietario cliente, personal de la sucursal o Administrador. Costos congelados solo para ADMIN/ENCARGADO.",
)
async def consultarVenta(
    venta_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> VentaDTO:
    servicio = VentaService(db)
    return await servicio.obtener(usuario, venta_id)


@router.get(
    "/{venta_id}/comprobante",
    response_model=ComprobanteDTO,
    summary="Comprobante de venta con pagos (CU11)",
    description="Mismos permisos que la venta. Incluye pagos, codigo de reserva, sucursal y cajero.",
)
async def consultarComprobante(
    venta_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ComprobanteDTO:
    servicio = VentaService(db)
    return await servicio.obtenerComprobante(usuario, venta_id)
