"""Router de Posventa: Saldo Personal del Cliente — CU09 (B1 Finanzas).

Endpoints:
- GET /saldos/mio
- POST /ventas/{venta_id}/aplicar-saldo
- POST /compras/{pedido_id}/aplicar-saldo
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.posventa.schemas import (
    AplicarSaldoDTO,
    SaldoAplicadoDTO,
    SaldoResumenDTO,
)
from backend.app.core.modules.posventa.services.saldo_service import SaldoService
from backend.app.core.errores import (
    E400, E401, E403, E404, E409_NEGOCIO,
)

router = APIRouter()


@router.get(
    "/saldos/mio",
    response_model=SaldoResumenDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar libro de saldo propio (CU09)",
    description="Devuelve el saldo disponible, el saldo retenido por compras en curso y la lista append-only de movimientos.",
    responses={401: E401, 403: E403},
)
async def obtenerSaldoPropio(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> SaldoResumenDTO:
    from fastapi import HTTPException
    if not usuario.empresa_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario sin empresa asignada",
        )
    return await SaldoService(db).obtener_saldo_resumen(
        cliente_id=usuario.id,
        empresa_id=usuario.empresa_id,
    )


@router.post(
    "/ventas/{venta_id}/aplicar-saldo",
    response_model=SaldoAplicadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Aplicar saldo a venta presencial o digital (CU09)",
    description="Retención atómica bajo bloqueo FOR UPDATE de movimientos de saldo. Requiere header Idempotency-Key.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO},
)
async def aplicarSaldoVenta(
    venta_id: uuid.UUID,
    datos: AplicarSaldoDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> SaldoAplicadoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    return await SaldoService(db).aplicar_saldo_venta(
        usuario=usuario,
        venta_id=venta_id,
        monto_bob=datos.monto_bob,
        clave_idempotencia=clave,
        revision=datos.revision,
    )


@router.post(
    "/compras/{pedido_id}/aplicar-saldo",
    response_model=SaldoAplicadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Aplicar saldo a pedido de compra (CU09)",
    description="Retención atómica bajo bloqueo FOR UPDATE en comercial.movimientos_saldo. Requiere header Idempotency-Key.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO},
)
async def aplicarSaldoPedido(
    pedido_id: uuid.UUID,
    datos: AplicarSaldoDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> SaldoAplicadoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    return await SaldoService(db).aplicar_saldo_pedido(
        usuario=usuario,
        pedido_id=pedido_id,
        monto_bob=datos.monto_bob,
        clave_idempotencia=clave,
        revision=datos.revision,
    )
