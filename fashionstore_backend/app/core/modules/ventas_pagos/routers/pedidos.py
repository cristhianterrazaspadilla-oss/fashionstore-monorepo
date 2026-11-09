"""Router Pedidos y Carrito Durable — CU21.

Rutas:
- GET /carritos/mio
- POST /carritos/mio/lineas
- PATCH /carritos/mio/lineas/{linea_id}
- DELETE /carritos/mio/lineas/{linea_id}
- POST /carritos/mio/checkout
- GET /compras/{pedido_id}
- POST /compras/{pedido_id}/aceptar-oferta
"""
import uuid
from typing import Optional, Union

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.ventas_pagos.routers.carritos import checkout as checkout_legado
from backend.app.core.modules.ventas_pagos.schemas import CheckoutCrearDTO, CheckoutRespuestaDTO
from backend.app.core.errores import E400, E401, E403, E404, E409_NEGOCIO, E422
from backend.app.core.modules.ventas_pagos.services.pedido_service import (
    CarritoDurableDTO,
    CheckoutCarritoDTO,
    LineaCarritoCrearDTO,
    LineaCarritoModificarDTO,
    PedidoCompraDTO,
    PedidoService,
)

router = APIRouter()


@router.get(
    "/carritos/mio",
    response_model=CarritoDurableDTO,
    status_code=status.HTTP_200_OK,
    operation_id="consultar_carrito_mio_cu21",
    summary="Consultar carrito propio (CU21)",
    description="Retorna el carrito activo del cliente autenticado con total estimado y detalle de líneas.",
)
async def consultar_carrito(
    canal: str = Query("WEB", description="Canal de compra: WEB o MOVIL"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> CarritoDurableDTO:
    servicio = PedidoService(db)
    return await servicio.consultar_carrito(usuario, canal=canal.upper())


@router.post(
    "/carritos/mio/lineas",
    response_model=CarritoDurableDTO,
    status_code=status.HTTP_200_OK,
    operation_id="agregar_linea_carrito_cu21",
    summary="Agregar línea al carrito (CU21)",
    description="Agrega una variante al carrito sin comprometer stock de inventario. Idempotente.",
)
async def agregar_linea(
    datos: LineaCarritoCrearDTO,
    canal: str = Query("WEB"),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> CarritoDurableDTO:
    clave = validar_clave_idempotencia(clave_idempotencia) if clave_idempotencia else None
    servicio = PedidoService(db)
    return await servicio.agregar_linea(usuario, datos, canal=canal.upper(), clave=clave)


@router.patch(
    "/carritos/mio/lineas/{linea_id}",
    response_model=CarritoDurableDTO,
    status_code=status.HTTP_200_OK,
    operation_id="modificar_linea_carrito_cu21",
    summary="Modificar cantidad de línea (CU21)",
    description="Actualiza la cantidad deseada de una línea o variante en el carrito. Idempotente.",
)
async def modificar_linea(
    linea_id: uuid.UUID,
    datos: LineaCarritoModificarDTO,
    canal: str = Query("WEB"),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> CarritoDurableDTO:
    clave = validar_clave_idempotencia(clave_idempotencia) if clave_idempotencia else None
    servicio = PedidoService(db)
    return await servicio.modificar_linea(usuario, linea_id, datos, canal=canal.upper(), clave=clave)


@router.delete(
    "/carritos/mio/lineas/{linea_id}",
    response_model=CarritoDurableDTO,
    status_code=status.HTTP_200_OK,
    operation_id="quitar_linea_carrito_cu21",
    summary="Quitar línea del carrito (CU21)",
    description="Elimina una línea o variante del carrito activo. Idempotente.",
)
async def quitar_linea(
    linea_id: uuid.UUID,
    canal: str = Query("WEB"),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> CarritoDurableDTO:
    clave = validar_clave_idempotencia(clave_idempotencia) if clave_idempotencia else None
    servicio = PedidoService(db)
    return await servicio.quitar_linea(usuario, linea_id, canal=canal.upper(), clave=clave)


@router.post(
    "/carritos/mio/checkout",
    response_model=Union[CheckoutRespuestaDTO, PedidoCompraDTO],
    status_code=status.HTTP_201_CREATED,
    operation_id="checkout_pedido_compra_durable_cu21",
    summary="Checkout de carrito: crear pedido durable con oferta versionada (CU21)",
    description=(
        "Acepta el contrato legado CU14 cuando el cuerpo incluye canal y devuelve venta_id "
        "con stock comprometido. Sin canal en el cuerpo crea un PedidoCompra durable CU21 "
        "con oferta versionada y estados de pago/cumplimiento separados, sin comprometer "
        "stock antes del pago. Requiere Idempotency-Key."
    ),
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO, 422: E422},
)
async def checkout(
    datos: Union[CheckoutCrearDTO, CheckoutCarritoDTO],
    canal: str = Query("WEB"),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> Union[CheckoutRespuestaDTO, PedidoCompraDTO]:
    clave = validar_clave_idempotencia(clave_idempotencia)
    canal_normalizado = (canal or "WEB").upper()
    if canal_normalizado not in ("WEB", "MOVIL"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Canal inválido: WEB o MOVIL")
    if isinstance(datos, CheckoutCrearDTO):
        return await checkout_legado(
            datos=datos,
            canal=canal_normalizado,
            db=db,
            usuario=usuario,
            clave_idempotencia=str(clave),
        )
    servicio = PedidoService(db)
    return await servicio.checkout(usuario, datos, canal=canal_normalizado, clave=clave)


@router.get(
    "/compras/{pedido_id}",
    response_model=PedidoCompraDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar pedido de compra (CU21 / CU05)",
)
async def obtener_pedido(
    pedido_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> PedidoCompraDTO:
    servicio = PedidoService(db)
    return await servicio.obtener_pedido(usuario, pedido_id)


@router.post(
    "/compras/{pedido_id}/aceptar-oferta",
    response_model=PedidoCompraDTO,
    status_code=status.HTTP_200_OK,
    summary="Aceptar oferta vigente del pedido (CU21 / CU05)",
)
async def aceptar_oferta(
    pedido_id: uuid.UUID,
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> PedidoCompraDTO:
    clave = validar_clave_idempotencia(clave_idempotencia) if clave_idempotencia else None
    servicio = PedidoService(db)
    return await servicio.aceptar_oferta(usuario, pedido_id, clave=clave)
