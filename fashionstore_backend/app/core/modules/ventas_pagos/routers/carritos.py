"""Router Carritos y checkout — CU14 (RF14, RF15, RF16)."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.ventas_pagos.schemas import (
    CarritoDTO,
    CheckoutCrearDTO,
    CheckoutRespuestaDTO,
    CoberturaDTO,
    LineaActualizarDTO,
    LineaAgregarDTO,
)
from backend.app.core.modules.ventas_pagos.services.carrito_service import CarritoService
from backend.app.core.errores import (
    E400, E401, E403, E404, E409_AMBITO, E409_IDEM, E409_NEGOCIO, E422,
)

router = APIRouter()
CANALES = ("WEB", "MOVIL")


def _canal(canal: str) -> str:
    c = (canal or "WEB").upper()
    if c not in CANALES:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Canal inválido: WEB o MOVIL")
    return c


@router.get(
    "/mio", response_model=CarritoDTO, summary="Obtener mi carrito activo (CU14)",
    description="Cliente propietario. Crea el carrito ACTIVO si no existe. "
    "Muestra promoción vigente estimada por línea (se congela en el checkout).",
    responses={401: E401, 403: E403},
)
async def obtenerMiCarrito(
    canal: str = Query("WEB", description="WEB o MOVIL"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> CarritoDTO:
    return await CarritoService(db).obtener_mio(usuario, _canal(canal))


@router.post(
    "/mio/lineas", response_model=CarritoDTO, status_code=status.HTTP_200_OK,
    summary="Agregar línea al carrito (CU14)",
    description="Idempotente (header Idempotency-Key obligatorio, ámbito por "
    "usuario+operación AGREGAR). Agregar no compromete inventario. Revalida "
    "variante activa. Misma clave+usuario+payload devuelve el carrito; "
    "distinto payload 409; otro propietario nunca recibe datos ajenos (409).",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_IDEM, 422: E422},
    openapi_extra={"headers": ["Idempotency-Key"]},
)
async def agregarLinea(
    datos: LineaAgregarDTO,
    canal: str = Query("WEB"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> CarritoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    dto, _ = await CarritoService(db).agregar(usuario, datos, _canal(canal), clave)
    return dto


@router.patch(
    "/mio/lineas/{variante_id}", response_model=CarritoDTO, summary="Modificar cantidad (CU14)",
    description="Idempotente (header Idempotency-Key obligatorio, ámbito por usuario+operación MODIFICAR).",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_IDEM, 422: E422},
)
async def modificarLinea(
    variante_id: uuid.UUID,
    datos: LineaActualizarDTO,
    canal: str = Query("WEB"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> CarritoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    dto, _ = await CarritoService(db).modificar(usuario, variante_id, datos, _canal(canal), clave)
    return dto


@router.delete(
    "/mio/lineas/{variante_id}", response_model=CarritoDTO, summary="Quitar línea (CU14)",
    description="Idempotente (header Idempotency-Key obligatorio, ámbito por usuario+operación QUITAR).",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_IDEM},
)
async def quitarLinea(
    variante_id: uuid.UUID,
    canal: str = Query("WEB"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> CarritoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    dto, _ = await CarritoService(db).quitar(usuario, variante_id, _canal(canal), clave)
    return dto


@router.delete(
    "/mio", response_model=CarritoDTO, summary="Vaciar carrito (CU14)",
    description="Idempotente (header Idempotency-Key obligatorio, ámbito por usuario+operación VACIAR).",
    responses={400: E400, 401: E401, 403: E403, 409: E409_IDEM},
)
async def vaciarCarrito(
    canal: str = Query("WEB"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> CarritoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    dto, _ = await CarritoService(db).vaciar(usuario, _canal(canal), clave)
    return dto


@router.get(
    "/mio/cobertura", response_model=CoberturaDTO, summary="Sucursales que cubren el carrito (CU14)",
    description="Solo lectura, sin bloqueo ni reserva. Ordena primero las que cubren todo.",
    responses={401: E401, 403: E403},
)
async def coberturaCarrito(
    canal: str = Query("WEB"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> CoberturaDTO:
    return await CarritoService(db).cobertura(usuario, _canal(canal))


@router.post(
    "/mio/checkout-legado", response_model=CheckoutRespuestaDTO, status_code=status.HTTP_201_CREATED,
    summary="Confirmar compra digital (CU14)",
    description="Canal WEB o MOVIL, modalidad RECOJO o DELIVERY, una sola sucursal. Crea venta "
    "PENDIENTE_PAGO, compromete stock 60 min (SELECT FOR UPDATE ordenado + Kardex), congela "
    "precio/descuento/promoción/costo/tarifa y crea el pedido SOLICITADO. Si ninguna sucursal "
    "cubre todo o el carrito no tiene cobertura (409) sin efectos. Idempotencia por usuario: "
    "misma clave+usuario+payload devuelve la venta; distinto payload 409; otra venta del mismo "
    "UUID de otro propietario nunca se devuelve (409 IDEMPOTENCIA_AMBITO); se verifica que la "
    "venta pertenece al usuario actual.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO, 422: E422},
)
async def checkout(
    datos: CheckoutCrearDTO,
    canal: str = Query("WEB", description="Debe coincidir con datos.canal"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> CheckoutRespuestaDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    try:
        dto, _ = await CarritoService(db).checkout(usuario, datos, _canal(canal), clave)
        return dto
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en checkout: {type(e).__name__}: {str(e)}"
        )
