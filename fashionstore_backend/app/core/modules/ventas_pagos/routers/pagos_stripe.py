"""Router Pagos Stripe — CU15 y CU22 (E2 Stripe Test Mode)."""
import json
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.ventas_pagos.models_ordenes import (
    ContinuarAccionDTO,
    LineaRecuperadaCajaDTO,
    MetodoConfirmarDTO,
    MetodoPrepararDTO,
    MetodoPreparadoDTO,
    OrdenActivaCajaDTO,
    OrdenPagoCrearDTO,
    OrdenPagoDTO,
)
from backend.app.core.modules.ventas_pagos.schemas import EstadoPagoDTO, IntencionCrearDTO, IntencionDTO
from backend.app.core.modules.ventas_pagos.services.stripe_service import StripeService
from backend.app.core.errores import (
    E400, E401, E403, E404, E409_IDEM, E409_NEGOCIO, E502, E503_STRIPE,
)

router = APIRouter()


@router.post(
    "/stripe/intenciones", response_model=IntencionDTO, status_code=status.HTTP_201_CREATED,
    summary="Crear o reutilizar PaymentIntent (CU15)",
    description="Cliente propietario o Administrador. Una intención por venta: FAILED reutiliza el "
    "PaymentIntent vigente; CANCELED crea uno nuevo. Requiere header Idempotency-Key.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO, 502: E502, 503: E503_STRIPE},
)
async def crearIntencion(
    datos: IntencionCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> IntencionDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    dto, _ = await StripeService(db).crearIntencion(usuario, datos.venta_id, clave)
    return dto


@router.post(
    "/stripe/intenciones/reintento", response_model=IntencionDTO, status_code=status.HTTP_200_OK,
    summary="Reintentar pago dentro de la ventana (CU15)",
    description="Reutiliza la intención vigente (FAILED) o crea una nueva (CANCELED) mientras la venta "
    "siga PENDIENTE_PAGO y no expire.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO, 502: E502, 503: E503_STRIPE},
)
async def reintentarIntencion(
    datos: IntencionCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> IntencionDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    dto, _ = await StripeService(db).crearIntencion(usuario, datos.venta_id, clave)
    return dto


@router.get(
    "/stripe/estado/{venta_id}", response_model=EstadoPagoDTO,
    summary="Consultar estado de pago para polling (CU15)",
    description="El frontend consulta; nunca confirma pagos directamente.",
    responses={401: E401, 403: E403, 404: E404},
)
async def estadoPago(
    venta_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> EstadoPagoDTO:
    return await StripeService(db).estado(usuario, venta_id)


@router.post(
    "/stripe/webhook", status_code=status.HTTP_200_OK,
    summary="Webhook firmado de Stripe (CU15)",
    description="Única confirmación definitiva. Verifica la firma con el cuerpo HTTP crudo.",
    response_model=dict,
    responses={400: E400, 401: E401, 404: E404},
)
async def webhookStripe(
    request: Request,
    db: AsyncSession = Depends(get_db),
    firma: Optional[str] = Header(None, alias="Stripe-Signature"),
):
    cuerpo = await request.body()
    try:
        evento = json.loads(cuerpo.decode("utf-8") or "{}")
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cuerpo del webhook inválido")
    return await StripeService(db).confirmarWebhook(cuerpo, firma, evento)


@router.post(
    "/stripe/expiracion/ejecutar", status_code=status.HTTP_200_OK,
    summary="Ejecutar expiración de ventas vencidas (CU15)",
    description="Solo ADMINISTRADOR (job manual en pruebas). Advisory lock + SKIP LOCKED.",
    response_model=dict,
    responses={401: E401, 403: E403},
)
async def ejecutarExpiracion(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    from backend.app.core.permisos import es_admin
    from fastapi import HTTPException

    if not es_admin(usuario):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el Administrador")
    return await StripeService(db).cancelarVencidas()


# =========================================================================
# Capacidades E2 — CU22 (Métodos Preparados y Órdenes de Pago)
# =========================================================================

@router.post(
    "/stripe/metodos/preparar",
    response_model=MetodoPreparadoDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Preparar método de pago online (SetupIntent CU22)",
    description="Inicia un SetupIntent para vincular y autorizar un método de pago del cliente. Requiere header Idempotency-Key.",
    responses={400: E400, 401: E401, 403: E403, 502: E502, 503: E503_STRIPE},
)
async def prepararMetodoPago(
    datos: MetodoPrepararDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> MetodoPreparadoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    return await StripeService(db).preparar_metodo(
        usuario=usuario,
        clave_idempotencia=clave,
        huella_dispositivo=datos.huella_dispositivo,
    )


@router.get(
    "/stripe/metodos/{id}",
    response_model=MetodoPreparadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar método preparado (CU22)",
    description="Consulta el estado de un método preparado previamente online.",
    responses={401: E401, 403: E403, 404: E404},
)
async def consultarMetodoPreparado(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> MetodoPreparadoDTO:
    return await StripeService(db).obtener_metodo_preparado(usuario=usuario, preparacion_pago_id=id)


@router.post(
    "/stripe/metodos/{id}/confirmar",
    response_model=MetodoPreparadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Confirmar método preparado (SetupIntent CU22)",
    description="Confirma el SetupIntent en la pasarela o consulta su éxito, recupera customer y payment_method y marca el método LISTO.",
    responses={400: E400, 401: E401, 403: E403, 404: E404},
)
async def confirmarMetodoPreparado(
    id: uuid.UUID,
    datos: Optional[MetodoConfirmarDTO] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> MetodoPreparadoDTO:
    payment_method_id = datos.payment_method_id if datos else None
    return await StripeService(db).confirmar_metodo_preparado(
        usuario=usuario,
        preparacion_pago_id=id,
        payment_method_id=payment_method_id,
    )


@router.post(
    "/stripe/ordenes",
    response_model=OrdenPagoDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear orden de pago conectada unificada (CU22)",
    description="Calcula deuda por servidor, congela moneda/tasa/centavos y emite intención conectada o interactiva. Requiere header Idempotency-Key.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO, 502: E502, 503: E503_STRIPE},
)
async def crearOrdenPago(
    datos: OrdenPagoCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> OrdenPagoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    return await StripeService(db).crear_orden_pago(
        usuario=usuario,
        datos=datos,
        clave_idempotencia=clave,
    )


@router.get(
    "/stripe/ordenes/activa-caja",
    response_model=Optional[OrdenActivaCajaDTO],
    status_code=status.HTTP_200_OK,
    summary="Recuperar orden activa de caja (CU19/H4)",
    description="Recupera la orden de pago activa (PENDIENTE o CAPTURADO) del cajero para la sucursal/turno, refrescando el client_secret si está pendiente.",
    responses={401: E401, 403: E403},
)
async def recuperarOrdenActivaCaja(
    sucursal_id: uuid.UUID,
    turno_caja_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> Optional[OrdenActivaCajaDTO]:
    return await StripeService(db).obtener_orden_activa_caja(
        usuario=usuario,
        sucursal_id=sucursal_id,
        turno_caja_id=turno_caja_id,
    )


@router.get(
    "/stripe/ordenes/{id}",
    response_model=OrdenPagoDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar orden de pago (CU22)",
    description="Consulta los importes congelados y el estado de la orden de pago.",
    responses={401: E401, 403: E403, 404: E404},
)
async def consultarOrdenPago(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> OrdenPagoDTO:
    return await StripeService(db).obtener_orden_pago(usuario=usuario, orden_pago_id=id)


@router.post(
    "/stripe/ordenes/{id}/confirmar",
    response_model=OrdenPagoDTO,
    status_code=status.HTTP_200_OK,
    summary="Confirmar o sincronizar orden de pago con Stripe (CU19/CU22)",
    description="Sincroniza y confirma una OrdenPago PENDIENTE consultando la pasarela Stripe; transiciona a CAPTURADO si fue exitosa.",
    responses={400: E400, 401: E401, 403: E403, 404: E404},
)
async def confirmarOrdenPago(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> OrdenPagoDTO:
    return await StripeService(db).confirmar_orden_pago(
        usuario=usuario,
        orden_pago_id=id,
    )


@router.post(
    "/stripe/ordenes/{id}/cancelar",
    response_model=OrdenPagoDTO,
    status_code=status.HTTP_200_OK,
    summary="Cancelar orden de pago (CU19/CU22)",
    description="Cancela una orden de pago en estado PENDIENTE o REQUIERE_ACCION_CLIENTE y su venta asociada si procede. Rechaza con 409 si los fondos ya fueron capturados.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO},
)
async def cancelarOrdenPago(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> OrdenPagoDTO:
    return await StripeService(db).cancelar_orden_pago(
        usuario=usuario,
        orden_pago_id=id,
    )


@router.post(
    "/stripe/ordenes/{id}/continuar-accion",
    response_model=OrdenPagoDTO,
    status_code=status.HTTP_200_OK,
    summary="Continuar acción requerida (3DS / SCA CU22)",
    description="Transiciona una orden en REQUIERE_ACCION_CLIENTE a CAPTURADO tras confirmación del SDK cliente. Requiere header Idempotency-Key.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO},
)
async def continuarAccionOrden(
    id: uuid.UUID,
    datos: ContinuarAccionDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> OrdenPagoDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    return await StripeService(db).continuar_accion(
        usuario=usuario,
        orden_pago_id=id,
        clave_idempotencia=clave,
        payment_intent_id=datos.payment_intent_id,
    )


@router.post(
    "/stripe/ordenes/{id}/reanudar",
    response_model=OrdenPagoDTO,
    status_code=status.HTTP_200_OK,
    summary="Reanudar orden de pago provisional o pendiente (CU19/CU22 - J4)",
    description="Reanuda una orden provisional o pendiente recuperando la clave idempotente durable de la venta sin duplicar venta ni Kardex.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO, 502: E502},
)
async def reanudarOrdenPago(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> OrdenPagoDTO:
    return await StripeService(db).reanudar_orden_pago(
        usuario=usuario,
        orden_pago_id=id,
    )
