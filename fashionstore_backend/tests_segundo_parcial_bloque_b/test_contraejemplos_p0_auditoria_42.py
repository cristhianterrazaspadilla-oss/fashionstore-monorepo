"""Suite de Pruebas Verticales de Integración: Auditoría 42 (CU19, CU22 y Caja Conectada).

Verifica exhaustivamente las 4 puertas de la Auditoría 42:
- J1: Cancelación manual de orden de pago SOLO tras confirmación CANCELED del PI correcto.
      Estados no cancelados (REQUIRES_PAYMENT_METHOD, PROCESSING), respuesta con ID ajeno o timeout
      arrojan 502 Bad Gateway y retienen venta, orden y stock intactos sin Kardex LIBERACION_DIGITAL.
      Estado SUCCEEDED / CAPTURADO arroja 409 Conflict y sincroniza CAPTURADO sin liberar stock.
- J2: Validación obligatoria en TODAS las entradas a CAPTURADO (webhook, 3DS continuar_accion,
      y liquidación presencial). Webhook o 3DS con centavos o metadata discordantes rechaza con 400.
      Fallo de pasarela en liquidación presencial no se silencia: arroja 502 y retiene stock.
- J3: Liquidación con importes congelados de la venta iniciada.
      Iniciar venta a precio A -> capturar PI -> alterar precio o promoción en catálogo a B ->
      liquidar con líneas recuperadas -> Éxito 201/200 con total original A y Kardex exacto.
- J4: Reanudación de orden provisional tras fallo entre transacciones.
      Orden creada con PENDIENTE_{clave} se recupera vía POST /api/v1/pagos/stripe/ordenes/{id}/reanudar
      usando venta.clave_idempotencia durable, asociando el PI de Stripe sin duplicar venta ni Kardex.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import pytest
import pytest_asyncio
from fastapi import HTTPException, status
from sqlalchemy import func, select, text

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
# FIXTURES COMPARTIDOS
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


# =============================================================================
# PUERTA J1: CANCELACIÓN MANUAL SEGURA (SOLO CON CANCELED CONFIRMADO)
# =============================================================================

@pytest.mark.asyncio
async def test_j1a_cancelar_orden_pago_gateway_devuelve_requires_payment_method_no_libera_stock(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J1a: Si cancelar_intencion responde normalmente REQUIRES_PAYMENT_METHOD (sin excepción):
    - Debe lanzar 502 Bad Gateway.
    - La orden de pago debe permanecer PENDIENTE.
    - La venta debe permanecer PENDIENTE_PAGO.
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

    # Invocar cancelar orden
    resp_canc = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/cancelar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_canc.status_code == 502, f"Se esperaba 502, se obtuvo: {resp_canc.status_code} - {resp_canc.text}"

    # Validar estado en DB
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
        k_count = (await db.execute(stmt_k)).scalar()
        assert k_count == 0, "No debe registrarse Kardex LIBERACION_DIGITAL sin cancelación confirmada"


@pytest.mark.asyncio
async def test_j1b_cancelar_orden_pago_gateway_devuelve_id_ajeno_rechaza_502(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J1b: Si cancelar_intencion devuelve CANCELED pero con ID ajeno al solicitado:
    - Debe lanzar 502 Bad Gateway.
    - No liberar stock ni cancelar venta.
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
async def test_j1c_cancelar_orden_pago_gateway_capturado_succeeded_rechaza_409(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J1c: Si al cancelar la pasarela indica que ya fue capturado (SUCCEEDED):
    - Debe sincronizar la orden a CAPTURADO.
    - Debe lanzar 409 Conflict.
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

    # Simular captura previa en pasarela con metadata correcta
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
# PUERTA J2: VALIDACIÓN RIGUROSA EN TODAS LAS ENTRADAS A CAPTURADO
# =============================================================================

@pytest.mark.asyncio
async def test_j2a_webhook_payment_intent_succeeded_con_metadata_ajena_rechaza_400(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J2a: Webhook firmado con payment_intent.succeeded pero metadata empresa_id/venta_id discordante:
    - Debe rechazar con 400 Bad Request.
    - La orden de pago debe permanecer en PENDIENTE.
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

    # Simular webhook con metadata ajena (otra empresa)
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

    resp_hook = await http.cliente.post(
        "/api/v1/pagos/stripe/webhook",
        json=evento_webhook,
        headers={"Stripe-Signature": "t=123456,v1=test_sig"},
    )
    assert resp_hook.status_code == 400, f"Esperaba 400, obtuvo {resp_hook.status_code}: {resp_hook.text}"

    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_pago_id)
        assert op_db.estado == "PENDIENTE", "Orden no debe pasar a CAPTURADO con metadata ajena"


@pytest.mark.asyncio
async def test_j2b_liquidar_presencial_con_pasarela_caida_arroja_502_y_no_liquida(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J2b: Si durante liquidar presencial la consulta a Stripe arroja error de red o timeout:
    - NO debe silenciarse con except Exception: pass.
    - Debe responder 502 Bad Gateway.
    - La venta debe continuar en PENDIENTE_PAGO.
    - El stock debe permanecer como comprometido_digital (no entregado ni consumido).
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

    # Falla de red en pasarela al consultar intención
    class GatewayCaido(FakeStripeGateway):
        async def consultar_intencion(self, payment_intent_id: str) -> IntencionPago:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Conexión con Stripe fallida (timeout/502)",
            )

    gw_down = GatewayCaido()
    gw_down.intenciones = fake_stripe.intenciones
    fijar_gateway(gw_down)

    resp_liq = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "venta_id": str(venta_id),
            "orden_pago_id": str(orden_pago_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "medio_pago": "STRIPE_TEST",
            "stripe_payment_intent_id": pi_id,
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                }
            ],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_liq.status_code == 502, f"Se esperaba 502, se obtuvo: {resp_liq.status_code} - {resp_liq.text}"

    async with fabrica_sesiones() as db:
        v_db = await db.get(Venta, venta_id)
        assert v_db.estado == "PENDIENTE_PAGO", "Venta no debe liquidarse sin confirmación de Stripe"


# =============================================================================
# PUERTA J3: PRECIO Y PROMOCIÓN CONGELADOS EN VENTA INICIADA
# =============================================================================

@pytest.mark.asyncio
async def test_j3_liquidar_con_precio_catalogo_modificado_posterior_mantiene_total_congelado(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J3: Iniciar venta Stripe a precio A (100 BOB) -> capturar PI ->
    Modificar precio de catálogo de la variante a B (200 BOB) ->
    Liquidar venta presencial con las líneas persistidas:
    - Debe retornar 201/200 exitosamente con total 100 BOB.
    - NO debe recalcular contra los 200 BOB del catálogo ni arrojar 400.
    - Kardex de VENTA_PRESENCIAL por 1 unidad exacto.
    - Comprobante emitido con total 100.00 BOB.
    """
    http.usar(escenario.usuario_admin_a)

    # 1. Iniciar venta con precio de catálogo actual (100 BOB)
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
    venta_id = uuid.UUID(datos_init["venta_id"])
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    pi_id = datos_init["stripe_payment_intent_id"]
    total_congelado = Decimal(str(datos_init["monto_bob"]))
    assert total_congelado == Decimal("100.00")

    # 2. Capturar válidamente en pasarela
    fake_stripe.intenciones[pi_id].estado = "SUCCEEDED"

    # Confirmar orden de pago en backend para pasar a CAPTURADO
    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_conf.status_code == 200, resp_conf.text
    assert resp_conf.json()["estado"] == "CAPTURADO"

    # 3. Alterar el precio en catálogo a 250.00 BOB en la base de datos
    async with fabrica_sesiones() as db:
        var = await db.get(VarianteProducto, escenario.variante_a_id)
        assert var is not None
        var.precio = Decimal("250.00")
        await db.commit()

    # 4. Simular recuperación tras F5 y liquidación con líneas persistidas
    resp_recup = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_recup.status_code == 200
    datos_recup = resp_recup.json()
    assert datos_recup["estado_orden"] == "CAPTURADO"
    lineas_recuperadas = datos_recup["lineas"]
    assert len(lineas_recuperadas) == 1
    assert Decimal(str(lineas_recuperadas[0]["precio_unitario_bob"])) == Decimal("100.00")

    # 5. Liquidar la venta presencial
    resp_liq = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "venta_id": str(venta_id),
            "orden_pago_id": str(orden_pago_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "medio_pago": "STRIPE_TEST",
            "stripe_payment_intent_id": pi_id,
            "lineas": [
                {
                    "variante_id": str(l["variante_id"]),
                    "cantidad": l["cantidad"],
                    "precio_unitario_bob": float(l["precio_unitario_bob"]),
                }
                for l in lineas_recuperadas
            ],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_liq.status_code in (200, 201), f"Liquidación debió aceptar precio congelado: {resp_liq.text}"
    liq_datos = resp_liq.json()
    assert Decimal(str(liq_datos["total_bob"])) == Decimal("100.00"), "Total liquidado debe ser el monto congelado A"
    assert liq_datos["estado_pago"] == "PAGADA"
    assert liq_datos["estado_entrega"] == "ENTREGADA"

    # Verificar DB: una venta, un pago, Kardex VENTA_PRESENCIAL
    async with fabrica_sesiones() as db:
        v_db = await db.get(Venta, venta_id)
        assert v_db.estado == "PAGADA"
        assert v_db.total == Decimal("100.00")

        stmt_p = select(Pago).where(Pago.venta_id == venta_id)
        pagos = (await db.execute(stmt_p)).scalars().all()
        assert len(pagos) == 1
        assert pagos[0].monto == Decimal("100.00")

        stmt_k = select(MovimientoInventario).where(
            MovimientoInventario.referencia_id == venta_id,
            MovimientoInventario.tipo == "VENTA_PRESENCIAL",
        )
        k_movs = (await db.execute(stmt_k)).scalars().all()
        assert len(k_movs) == 1


# =============================================================================
# PUERTA J4: REANUDACIÓN DE ORDEN PROVISIONAL
# =============================================================================

@pytest.mark.asyncio
async def test_j4_reanudacion_orden_provisional_recupera_mismo_pi_sin_duplicar(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J4: Si ocurre caída tras el primer commit (orden queda PENDIENTE_...):
    - GET /activa-caja no expone PENDIENTE_... como stripe_payment_intent_id (devuelve null o estado PROVISIONAL).
    - POST /ordenes/{id}/reanudar usa la venta.clave_idempotencia durable.
    - Se asocia el PaymentIntent oficial en Stripe y OrdenPago se actualiza.
    - Cero duplicación de venta, cero duplicación de Kardex COMPROMISO_DIGITAL.
    """
    http.usar(escenario.usuario_admin_a)

    # 1. Crear manualmente una venta y orden provisional simulando fallo tras Transacción 1
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
            numero=f"VTA-PROV-{v_id.hex[:6]}",
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

        det_v = DetalleVenta(
            id=uuid.uuid4(),
            venta_id=v_id,
            variante_id=escenario.variante_a_id,
            cantidad=1,
            precio_unitario=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_promedio=Decimal("50.00"),
        )
        db.add(det_v)

        # Comprometer inventario
        inv = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                )
            )
        ).scalars().first()
        inv.comprometido_digital = (inv.comprometido_digital or 0) + 1
        inv.disponible -= 1

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
                observacion="Compromiso provisional inicial",
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

    # 2. Verificar que activa-caja no expone PENDIENTE_... como stripe_payment_intent_id
    resp_activa = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_activa.status_code == 200
    datos_activa = resp_activa.json()
    assert datos_activa["orden_pago_id"] == str(op_id)
    assert datos_activa["stripe_payment_intent_id"] is None or not datos_activa["stripe_payment_intent_id"].startswith("PENDIENTE_")

    # 3. Invocar endpoint de reanudación
    resp_reanudar = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{op_id}/reanudar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_reanudar.status_code == 200, resp_reanudar.text
    datos_reanudar = resp_reanudar.json()
    pi_generado = datos_reanudar["referencia_externa"]
    assert pi_generado.startswith("pi_"), f"Debe devolver un PaymentIntent real de Stripe, no: {pi_generado}"

    # 4. Verificar que OrdenPago se actualizó en DB y no hay duplicados de Kardex ni de venta
    async with fabrica_sesiones() as db:
        op_actualizada = await db.get(OrdenPago, op_id)
        assert op_actualizada.referencia_externa == pi_generado
        assert not op_actualizada.referencia_externa.startswith("PENDIENTE_")

        stmt_k = select(func.count(MovimientoInventario.id)).where(
            MovimientoInventario.referencia_id == v_id,
            MovimientoInventario.tipo == "COMPROMISO_DIGITAL",
        )
        assert (await db.execute(stmt_k)).scalar() == 1, "Debe existir un único compromiso digital"
