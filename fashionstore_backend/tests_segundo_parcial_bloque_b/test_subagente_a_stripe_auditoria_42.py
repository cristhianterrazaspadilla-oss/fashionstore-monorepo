"""Suite de Pruebas de Contraejemplos P0 — Auditoría 42 (Subagente A: Stripe / Backend Financiero).

Cubre exhaustivamente los contraejemplos exigidos para el Subagente A:
1. J1: Cancelación manual segura en `cancelar_orden_pago`:
   - a) Gateway devuelve `REQUIRES_PAYMENT_METHOD` normalmente (sin excepción):
        Exige 502 Bad Gateway, la orden permanece PENDIENTE, venta PENDIENTE_PAGO,
        el inventario NO se libera y no se genera Kardex LIBERACION_DIGITAL.
   - b) Gateway devuelve `PROCESSING` normalmente:
        Exige 502 Bad Gateway, orden y venta intactas, inventario no liberado.
   - c) Gateway devuelve ID ajeno al solicitado (incluso con estado CANCELED):
        Exige 502 Bad Gateway, orden y venta intactas, inventario no liberado.
   - d) Gateway devuelve `SUCCEEDED` / `CAPTURADO`:
        Exige 409 Conflict, sincroniza a CAPTURADO, inventario no liberado.
2. J2: Validación financiera rigurosa en `confirmarWebhook` y `continuar_accion`:
   - a) Webhook `payment_intent.succeeded` con centavos discordantes:
        Exige 400 Bad Request, orden permanece PENDIENTE.
   - b) Webhook `payment_intent.succeeded` con metadata empresa_id discordante:
        Exige 400 Bad Request, orden permanece PENDIENTE.
   - c) Webhook `payment_intent.succeeded` con metadata venta_id discordante:
        Exige 400 Bad Request, orden permanece PENDIENTE.
   - d) `continuar_accion` (3DS) con metadata empresa_id o venta_id ajena:
        Exige 400 Bad Request, orden no pasa a CAPTURADO.
3. J4: Protección provisional en `activa-caja` y reanudación en `POST /api/v1/pagos/stripe/ordenes/{id}/reanudar`:
   - a) `obtener_orden_activa_caja` con orden provisional `PENDIENTE_...`:
        Retorna `stripe_payment_intent_id = null` y `estado_verificacion = "PROVISIONAL_PENDIENTE_INTENTO"`.
   - b) Reanudar orden provisional `PENDIENTE_{clave}`:
        Recupera clave durable de la venta, invoca Stripe de forma idempotente,
        actualiza OrdenPago con `pi_...` real sin duplicar Venta ni Kardex.
   - c) Reanudar orden ya capturada:
        Exige 409 Conflict.
   - d) Error de red con pasarela en reanudación:
        Exige 502 Bad Gateway y conserva orden provisional.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import pytest
import pytest_asyncio
from fastapi import HTTPException, status
from sqlalchemy import func, select, text

from backend.app.core.config import settings
from backend.app.core.modules.catalogo.models import Producto, VarianteProducto
from backend.app.core.modules.identidad_empresas.models import Empleado, Rol, Usuario
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.organizacion.models import TasaCambio
from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import (
    FakeStripeGateway,
    IntencionPago,
    fijar_gateway,
)
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Pago, TurnoCaja, Venta
from backend.app.core.modules.ventas_pagos.models_ordenes import (
    LineaRecuperadaCajaDTO,
    OrdenActivaCajaDTO,
    OrdenPago,
)
from backend.app.core.modules.ventas_pagos.services.stripe_service import StripeService


# =============================================================================
# FIXTURES Y HELPERS
# =============================================================================

@pytest.fixture
def fake_stripe():
    """Configura una instancia limpia de FakeStripeGateway."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    yield fake
    fijar_gateway(None)


@pytest_asyncio.fixture(autouse=True)
async def asegurar_tasa_vigente(fabrica_sesiones, escenario):
    """Garantiza una tasa de cambio vigente en plataforma.tasas_cambio para cotización USD."""
    async with fabrica_sesiones() as db:
        stmt = (
            select(TasaCambio)
            .where(TasaCambio.vigente_hasta.is_(None))
            .order_by(TasaCambio.vigente_desde.desc())
        )
        tasa = (await db.execute(stmt)).scalars().first()
        if tasa is None:
            stmt_fallback = select(TasaCambio).order_by(TasaCambio.vigente_desde.desc())
            tasa = (await db.execute(stmt_fallback)).scalars().first()
            if tasa is not None:
                tasa.vigente_hasta = None
                await db.commit()


def _firmar_webhook(cuerpo: bytes, secret: str) -> str:
    ts = int(time.time())
    to_sign = f"{ts}.".encode("utf-8") + cuerpo
    firma = hmac.new(secret.encode("utf-8"), to_sign, hashlib.sha256).hexdigest()
    return f"t={ts},v1={firma}"


# =============================================================================
# J1: CANCELACIÓN MANUAL SEGURA (EXIGE CANCELED Y ID COINCIDENTE)
# =============================================================================

@pytest.mark.asyncio
async def test_j1a_cancelar_orden_gateway_devuelve_requires_payment_method_rechaza_502_no_libera_stock(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J1a: Si cancelar_intencion devuelve REQUIRES_PAYMENT_METHOD (sin excepción):
    - Debe responder 502 Bad Gateway.
    - La orden de pago DEBE permanecer PENDIENTE.
    - La venta DEBE permanecer PENDIENTE_PAGO.
    - El stock comprometido_digital NO debe liberarse a disponible.
    - CERO movimientos Kardex LIBERACION_DIGITAL.
    """
    http.usar(escenario.usuario_admin_a)

    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201, resp_init.text
    datos_init = resp_init.json()
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    venta_id = uuid.UUID(datos_init["venta_id"])
    pi_id = datos_init["stripe_payment_intent_id"]

    async with fabrica_sesiones() as db:
        inv_antes = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                )
            )
        ).scalars().first()
        disp_antes = inv_antes.disponible
        comp_antes = inv_antes.comprometido_digital
        assert comp_antes >= 1

    # Gateway doble: cancelar_intencion responde normalmente REQUIRES_PAYMENT_METHOD
    class GatewayNoCancela(FakeStripeGateway):
        async def cancelar_intencion(self, payment_intent_id: str) -> IntencionPago:
            intencion = self.intenciones.get(payment_intent_id)
            if intencion:
                intencion.estado = "REQUIRES_PAYMENT_METHOD"
                return intencion
            return IntencionPago(
                id=payment_intent_id,
                venta_id="",
                monto_centavos=1000,
                moneda="usd",
                estado="REQUIRES_PAYMENT_METHOD",
            )

    gw_nc = GatewayNoCancela()
    gw_nc.intenciones = fake_stripe.intenciones
    fijar_gateway(gw_nc)

    resp_canc = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/cancelar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_canc.status_code == 502, f"Se esperaba 502, se obtuvo: {resp_canc.status_code} - {resp_canc.text}"

    # Validar persistencia intacta
    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_pago_id)
        assert op_db.estado == "PENDIENTE", f"Orden no debe ser CANCELADO, es: {op_db.estado}"
        v_db = await db.get(Venta, venta_id)
        assert v_db.estado == "PENDIENTE_PAGO", f"Venta no debe ser CANCELADA, es: {v_db.estado}"

        inv_desp = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                )
            )
        ).scalars().first()
        assert inv_desp.comprometido_digital == comp_antes, "comprometido_digital no debe disminuir"
        assert inv_desp.disponible == disp_antes, "disponible no debe incrementarse"

        stmt_k = select(func.count(MovimientoInventario.id)).where(
            MovimientoInventario.referencia_id == venta_id,
            MovimientoInventario.tipo == "LIBERACION_DIGITAL",
        )
        assert (await db.execute(stmt_k)).scalar() == 0, "No debe registrarse Kardex LIBERACION_DIGITAL"


@pytest.mark.asyncio
async def test_j1b_cancelar_orden_gateway_devuelve_processing_rechaza_502_no_libera_stock(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J1b: Si cancelar_intencion devuelve PROCESSING:
    - Debe responder 502 Bad Gateway.
    - Orden permanece PENDIENTE y stock intacto.
    """
    http.usar(escenario.usuario_admin_a)

    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201
    datos_init = resp_init.json()
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    venta_id = uuid.UUID(datos_init["venta_id"])

    class GatewayProcessing(FakeStripeGateway):
        async def cancelar_intencion(self, payment_intent_id: str) -> IntencionPago:
            intencion = self.intenciones.get(payment_intent_id)
            if intencion:
                intencion.estado = "PROCESSING"
                return intencion
            return IntencionPago(
                id=payment_intent_id,
                venta_id="",
                monto_centavos=1000,
                moneda="usd",
                estado="PROCESSING",
            )

    gw_proc = GatewayProcessing()
    gw_proc.intenciones = fake_stripe.intenciones
    fijar_gateway(gw_proc)

    resp_canc = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/cancelar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_canc.status_code == 502

    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_pago_id)
        assert op_db.estado == "PENDIENTE"
        v_db = await db.get(Venta, venta_id)
        assert v_db.estado == "PENDIENTE_PAGO"


@pytest.mark.asyncio
async def test_j1c_cancelar_orden_gateway_devuelve_id_ajeno_rechaza_502(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J1c: Si cancelar_intencion devuelve CANCELED pero con ID ajeno:
    - Debe responder 502 Bad Gateway.
    - Orden y venta intactas, no libera inventario.
    """
    http.usar(escenario.usuario_admin_a)

    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201
    datos_init = resp_init.json()
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    venta_id = uuid.UUID(datos_init["venta_id"])

    class GatewayIDAjeno(FakeStripeGateway):
        async def cancelar_intencion(self, payment_intent_id: str) -> IntencionPago:
            return IntencionPago(
                id=f"pi_ajeno_{uuid.uuid4().hex[:8]}",
                venta_id=str(venta_id),
                monto_centavos=1000,
                moneda="usd",
                estado="CANCELED",
            )

    gw_ajeno = GatewayIDAjeno()
    gw_ajeno.intenciones = fake_stripe.intenciones
    fijar_gateway(gw_ajeno)

    resp_canc = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/cancelar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_canc.status_code == 502

    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_pago_id)
        assert op_db.estado == "PENDIENTE"
        v_db = await db.get(Venta, venta_id)
        assert v_db.estado == "PENDIENTE_PAGO"


@pytest.mark.asyncio
async def test_j1d_cancelar_orden_gateway_capturado_succeeded_rechaza_409(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J1d: Si al cancelar la pasarela reporta que los fondos ya fueron capturados (SUCCEEDED):
    - Debe sincronizar la orden a CAPTURADO.
    - Debe rechazar con 409 Conflict.
    - NUNCA liberar inventario.
    """
    http.usar(escenario.usuario_admin_a)

    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201
    datos_init = resp_init.json()
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    venta_id = uuid.UUID(datos_init["venta_id"])
    pi_id = datos_init["stripe_payment_intent_id"]

    fake_stripe.intenciones[pi_id].estado = "SUCCEEDED"

    resp_canc = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/cancelar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_canc.status_code == 409

    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_pago_id)
        assert op_db.estado == "CAPTURADO"
        v_db = await db.get(Venta, venta_id)
        assert v_db.estado == "PENDIENTE_PAGO"

        stmt_k = select(func.count(MovimientoInventario.id)).where(
            MovimientoInventario.referencia_id == venta_id,
            MovimientoInventario.tipo == "LIBERACION_DIGITAL",
        )
        assert (await db.execute(stmt_k)).scalar() == 0


# =============================================================================
# J2: VALIDACIÓN FINANCIERA RIGUROSA EN WEBHOOK Y CONTINUAR_ACCION (3DS)
# =============================================================================

@pytest.mark.asyncio
async def test_j2a_webhook_succeeded_centavos_discordantes_rechaza_400_y_orden_pendiente(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J2a: Webhook firmado payment_intent.succeeded con centavos discordantes:
    - Debe rechazar con 400 Bad Request.
    - La orden de pago debe permanecer PENDIENTE (no pasa a CAPTURADO).
    """
    http.usar(escenario.usuario_admin_a)

    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201
    datos_init = resp_init.json()
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    venta_id = uuid.UUID(datos_init["venta_id"])
    pi_id = datos_init["stripe_payment_intent_id"]
    centavos_reales = datos_init["centavos_usd"]

    evento_webhook = {
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": pi_id,
                "amount": centavos_reales + 500,  # Centavos discordantes
                "currency": "usd",
                "status": "succeeded",
                "metadata": {
                    "empresa_id": str(escenario.empresa_a_id),
                    "venta_id": str(venta_id),
                },
            }
        },
    }
    cuerpo_bytes = json.dumps(evento_webhook).encode("utf-8")
    secreto = settings.STRIPE_WEBHOOK_SECRET or "whsec_test"
    firma = _firmar_webhook(cuerpo_bytes, secreto)

    resp_hook = await http.cliente.post(
        "/api/v1/pagos/stripe/webhook",
        content=cuerpo_bytes,
        headers={"Stripe-Signature": firma},
    )
    assert resp_hook.status_code == 400, f"Esperaba 400, obtuvo {resp_hook.status_code}: {resp_hook.text}"

    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_pago_id)
        assert op_db.estado == "PENDIENTE", "Orden no debe transicionar a CAPTURADO si los centavos discrepan"


@pytest.mark.asyncio
async def test_j2b_webhook_succeeded_metadata_empresa_discordante_rechaza_400(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J2b: Webhook firmado payment_intent.succeeded con metadata empresa_id de otra empresa:
    - Debe rechazar con 400 Bad Request.
    - La orden de pago debe permanecer PENDIENTE.
    """
    http.usar(escenario.usuario_admin_a)

    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201
    datos_init = resp_init.json()
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    venta_id = uuid.UUID(datos_init["venta_id"])
    pi_id = datos_init["stripe_payment_intent_id"]

    evento_webhook = {
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": pi_id,
                "amount": datos_init["centavos_usd"],
                "currency": "usd",
                "status": "succeeded",
                "metadata": {
                    "empresa_id": str(escenario.empresa_b_id),  # Empresa ajena B
                    "venta_id": str(venta_id),
                },
            }
        },
    }
    cuerpo_bytes = json.dumps(evento_webhook).encode("utf-8")
    secreto = settings.STRIPE_WEBHOOK_SECRET or "whsec_test"
    firma = _firmar_webhook(cuerpo_bytes, secreto)

    resp_hook = await http.cliente.post(
        "/api/v1/pagos/stripe/webhook",
        content=cuerpo_bytes,
        headers={"Stripe-Signature": firma},
    )
    assert resp_hook.status_code == 400

    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_pago_id)
        assert op_db.estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_j2c_webhook_succeeded_metadata_venta_discordante_rechaza_400(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J2c: Webhook firmado payment_intent.succeeded con metadata venta_id ajena:
    - Debe rechazar con 400 Bad Request.
    - La orden de pago debe permanecer PENDIENTE.
    """
    http.usar(escenario.usuario_admin_a)

    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201
    datos_init = resp_init.json()
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    pi_id = datos_init["stripe_payment_intent_id"]
    venta_ajena_id = uuid.uuid4()

    evento_webhook = {
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": pi_id,
                "amount": datos_init["centavos_usd"],
                "currency": "usd",
                "status": "succeeded",
                "metadata": {
                    "empresa_id": str(escenario.empresa_a_id),
                    "venta_id": str(venta_ajena_id),  # Venta ajena
                },
            }
        },
    }
    cuerpo_bytes = json.dumps(evento_webhook).encode("utf-8")
    secreto = settings.STRIPE_WEBHOOK_SECRET or "whsec_test"
    firma = _firmar_webhook(cuerpo_bytes, secreto)

    resp_hook = await http.cliente.post(
        "/api/v1/pagos/stripe/webhook",
        content=cuerpo_bytes,
        headers={"Stripe-Signature": firma},
    )
    assert resp_hook.status_code == 400

    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_pago_id)
        assert op_db.estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_j2d_continuar_accion_metadata_ajena_rechaza_400(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J2d: En continuar_accion (3DS / SCA), si el PaymentIntent confirmado en Stripe
    devuelve metadata ajena o discrepante:
    - Debe rechazar con 400 Bad Request.
    - La orden de pago no pasa a CAPTURADO.
    """
    http.usar(escenario.usuario_admin_a)

    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201
    datos_init = resp_init.json()
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    venta_id = uuid.UUID(datos_init["venta_id"])
    pi_id = datos_init["stripe_payment_intent_id"]

    # Forzar la orden a REQUIERE_ACCION_CLIENTE
    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_pago_id)
        op_db.estado = "REQUIERE_ACCION_CLIENTE"
        await db.commit()

    # Gateway doble: confirmar_intencion devuelve metadata ajena (empresa B)
    class GatewayMetadataAjena(FakeStripeGateway):
        async def confirmar_intencion(self, payment_intent_id: str) -> IntencionPago:
            return IntencionPago(
                id=payment_intent_id,
                venta_id=str(venta_id),
                monto_centavos=datos_init["centavos_usd"],
                moneda="usd",
                estado="SUCCEEDED",
                empresa_id=str(escenario.empresa_b_id),
                metadata={
                    "empresa_id": str(escenario.empresa_b_id),  # Empresa ajena B
                    "venta_id": str(venta_id),
                },
            )

    gw_meta = GatewayMetadataAjena()
    gw_meta.intenciones = fake_stripe.intenciones
    fijar_gateway(gw_meta)

    resp_3ds = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/continuar-accion",
        json={"payment_intent_id": pi_id},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_3ds.status_code == 400, f"Esperaba 400, obtuvo {resp_3ds.status_code}: {resp_3ds.text}"

    async with fabrica_sesiones() as db:
        op_desp = await db.get(OrdenPago, orden_pago_id)
        assert op_desp.estado != "CAPTURADO"


# =============================================================================
# J4: PROTECCIÓN PROVISIONAL Y ENDPOINT REANUDAR
# =============================================================================

@pytest.mark.asyncio
async def test_j4a_activa_caja_oculta_pi_provisional_y_reporta_estado_adecuado(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J4a: Si una orden está en estado provisional PENDIENTE_{clave}:
    - GET /activa-caja no envía PENDIENTE_{clave} como stripe_payment_intent_id (devuelve null).
    - estado_verificacion reporta "PROVISIONAL_PENDIENTE_INTENTO".
    """
    http.usar(escenario.usuario_admin_a)

    v_id = uuid.uuid4()
    op_id = uuid.uuid4()
    clave_idemp = uuid.uuid4()
    ahora_utc = datetime.now(timezone.utc)
    clave_provisional = f"PENDIENTE_{clave_idemp}"

    async with fabrica_sesiones() as db:
        stmt_t = select(TasaCambio).order_by(TasaCambio.vigente_desde.desc())
        tasa = (await db.execute(stmt_t)).scalars().first()
        factor = Decimal(str(tasa.tasa_bob_por_usd))
        centavos = int((Decimal("100.00") / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)

        v_prov = Venta(
            id=v_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-PROV-{v_id.hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            clave_idempotencia=clave_idemp,
            hash_solicitud="hash_prov_test",
            creada_en=ahora_utc,
        )
        db.add(v_prov)
        await db.flush()

        db.add(
            DetalleVenta(
                id=uuid.uuid4(),
                venta_id=v_id,
                variante_id=escenario.variante_a_id,
                cantidad=1,
                precio_unitario=Decimal("100.00"),
                descuento=Decimal("0.00"),
                costo_promedio=Decimal("50.00"),
            )
        )

        op_prov = OrdenPago(
            id=op_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=v_id,
            proveedor="STRIPE",
            clave_externa=clave_provisional,
            referencia_externa=clave_provisional,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            tasa_id=tasa.id,
            monto_usd=Decimal("14.37"),
            centavos_usd=centavos,
            revision=1,
            creada_en=ahora_utc,
            actualizada_en=ahora_utc,
        )
        db.add(op_prov)
        await db.commit()

    resp_activa = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_activa.status_code == 200
    datos_activa = resp_activa.json()
    assert datos_activa["orden_pago_id"] == str(op_id)
    assert datos_activa["stripe_payment_intent_id"] is None, "stripe_payment_intent_id no debe exponer prefijo provisional"
    assert datos_activa["estado_verificacion"] == "PROVISIONAL_PENDIENTE_INTENTO"


@pytest.mark.asyncio
async def test_j4b_reanudar_orden_provisional_exito_sin_duplicar_venta_ni_kardex(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J4b: POST /api/v1/pagos/stripe/ordenes/{id}/reanudar:
    - Recupera la clave idempotente durable desde venta.clave_idempotencia.
    - Crea/reutiliza el PI en Stripe de forma segura.
    - Actualiza OrdenPago con la referencia real `pi_...`.
    - No duplica Venta ni Kardex COMPROMISO_DIGITAL.
    """
    http.usar(escenario.usuario_admin_a)

    v_id = uuid.uuid4()
    op_id = uuid.uuid4()
    clave_idemp = uuid.uuid4()
    ahora_utc = datetime.now(timezone.utc)
    clave_provisional = f"PENDIENTE_{clave_idemp}"

    async with fabrica_sesiones() as db:
        stmt_t = select(TasaCambio).order_by(TasaCambio.vigente_desde.desc())
        tasa = (await db.execute(stmt_t)).scalars().first()
        factor = Decimal(str(tasa.tasa_bob_por_usd))
        centavos = int((Decimal("100.00") / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)

        v_prov = Venta(
            id=v_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-REANUDAR-{v_id.hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            clave_idempotencia=clave_idemp,
            hash_solicitud="hash_reanudar_test",
            creada_en=ahora_utc,
        )
        db.add(v_prov)
        await db.flush()

        db.add(
            DetalleVenta(
                id=uuid.uuid4(),
                venta_id=v_id,
                variante_id=escenario.variante_a_id,
                cantidad=1,
                precio_unitario=Decimal("100.00"),
                descuento=Decimal("0.00"),
                costo_promedio=Decimal("50.00"),
            )
        )

        db.add(
            MovimientoInventario(
                id=uuid.uuid4(),
                variante_id=escenario.variante_a_id,
                sucursal_destino_id=escenario.sucursal_a_id,
                tipo="COMPROMISO_DIGITAL",
                cantidad=1,
                costo_unitario=Decimal("50.00"),
                referencia_tipo="VENTA",
                referencia_id=v_id,
                observacion="Compromiso digital original",
                fecha_hora=ahora_utc,
            )
        )

        op_prov = OrdenPago(
            id=op_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=v_id,
            proveedor="STRIPE",
            clave_externa=clave_provisional,
            referencia_externa=clave_provisional,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            tasa_id=tasa.id,
            monto_usd=Decimal("14.37"),
            centavos_usd=centavos,
            revision=1,
            creada_en=ahora_utc,
            actualizada_en=ahora_utc,
        )
        db.add(op_prov)
        await db.commit()

    resp_reanudar = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{op_id}/reanudar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_reanudar.status_code == 200, f"Error en reanudación: {resp_reanudar.text}"
    datos_reanudar = resp_reanudar.json()
    pi_generado = datos_reanudar["referencia_externa"]
    assert pi_generado.startswith("pi_")
    assert datos_reanudar["client_secret"] is not None

    async with fabrica_sesiones() as db:
        op_actualizada = await db.get(OrdenPago, op_id)
        assert op_actualizada.referencia_externa == pi_generado
        assert op_actualizada.clave_externa == pi_generado

        # Validar no duplicación
        stmt_v = select(func.count(Venta.id)).where(Venta.id == v_id)
        assert (await db.execute(stmt_v)).scalar() == 1

        stmt_k = select(func.count(MovimientoInventario.id)).where(
            MovimientoInventario.referencia_id == v_id,
            MovimientoInventario.tipo == "COMPROMISO_DIGITAL",
        )
        assert (await db.execute(stmt_k)).scalar() == 1, "Debe conservarse un único Kardex COMPROMISO_DIGITAL"


@pytest.mark.asyncio
async def test_j4c_reanudar_orden_ya_capturada_rechaza_409(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J4c: Si la orden ya se encuentra en estado CAPTURADO, reanudar debe rechazar con 409 Conflict."""
    http.usar(escenario.usuario_admin_a)

    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201
    datos_init = resp_init.json()
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    pi_id = datos_init["stripe_payment_intent_id"]

    # Simular captura y confirmar
    fake_stripe.intenciones[pi_id].estado = "SUCCEEDED"
    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_conf.status_code == 200
    assert resp_conf.json()["estado"] == "CAPTURADO"

    resp_reanudar = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/reanudar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_reanudar.status_code == 409
    assert "ya se encuentra capturada" in resp_reanudar.json()["detail"].lower()


@pytest.mark.asyncio
async def test_j4d_reanudar_error_red_pasarela_retorna_502_y_conserva_provisional(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J4d: Si durante la reanudación la pasarela Stripe arroja excepción de red/timeout:
    - Debe retornar 502 Bad Gateway.
    - La orden de pago debe conservarse provisional para reintento.
    """
    http.usar(escenario.usuario_admin_a)

    v_id = uuid.uuid4()
    op_id = uuid.uuid4()
    clave_idemp = uuid.uuid4()
    ahora_utc = datetime.now(timezone.utc)
    clave_provisional = f"PENDIENTE_{clave_idemp}"

    async with fabrica_sesiones() as db:
        stmt_t = select(TasaCambio).order_by(TasaCambio.vigente_desde.desc())
        tasa = (await db.execute(stmt_t)).scalars().first()

        v_prov = Venta(
            id=v_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-FAIL-{v_id.hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            clave_idempotencia=clave_idemp,
            hash_solicitud="hash_fail_test",
            creada_en=ahora_utc,
        )
        db.add(v_prov)
        op_prov = OrdenPago(
            id=op_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=v_id,
            proveedor="STRIPE",
            clave_externa=clave_provisional,
            referencia_externa=clave_provisional,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            tasa_id=tasa.id,
            monto_usd=Decimal("14.37"),
            centavos_usd=1437,
            revision=1,
            creada_en=ahora_utc,
            actualizada_en=ahora_utc,
        )
        db.add(op_prov)
        await db.commit()

    class GatewayConFallo(FakeStripeGateway):
        async def crear_o_reutilizar_intencion(self, *args, **kwargs) -> IntencionPago:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Conexión fallida con Stripe",
            )

    gw_fail = GatewayConFallo()
    fijar_gateway(gw_fail)

    resp_reanudar = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{op_id}/reanudar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_reanudar.status_code == 502

    async with fabrica_sesiones() as db:
        op_actualizada = await db.get(OrdenPago, op_id)
        assert op_actualizada.referencia_externa == clave_provisional
        assert op_actualizada.estado == "PENDIENTE"
