"""Tests Contraejemplos Auditoría 42 — Subagente B (Venta Presencial / Inventario Backend).

Verifica:
- J3: Iniciar venta Stripe a precio A, capturar PI válidamente, cambiar precio de variante en catálogo a B
      o cambiar promociones actuales. Al llamar a liquidar con las líneas recuperadas, el código actual
      falla con 400 (precio adulterado o total recalculado no coincide con orden_stripe.monto_bob).
      La prueba exige éxito 200/201 con el total congelado original A.
- J2 en liquidación: Cuando gateway.consultar_intencion arroja excepción (red caída, timeout),
      el código previo hacía except Exception: pass y permitía liquidar sin verificación.
      La prueba exige que falle demostrando que DEBE arrojar 502 Bad Gateway y retener el stock/venta pendientes.
- J4: Reanudación de orden provisional vía reintento con la clave idempotente durable: verifica que
      una orden provisional no duplica reservas de inventario ni crea múltiples ventas.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import pytest
import pytest_asyncio
from fastapi import HTTPException, status
from sqlalchemy import func, select

from backend.app.core.modules.catalogo.models import VarianteProducto
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.organizacion.models import TasaCambio
from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import (
    FakeStripeGateway,
    IntencionPago,
    fijar_gateway,
)
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Pago, Venta
from backend.app.core.modules.ventas_pagos.models_ordenes import OrdenPago
from backend.app.core.modules.ventas_pagos.services.pedido_service import Comprobante
from backend.app.core.modules.ventas_pagos.services.venta_presencial_service import (
    LineaVentaPresencialDTO,
    VentaPresencialIniciarStripeDTO,
    VentaPresencialService,
)


@pytest.fixture
def fake_stripe():
    """Configura una instancia limpia de FakeStripeGateway."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    yield fake
    fijar_gateway(None)


@pytest_asyncio.fixture(autouse=True)
async def asegurar_tasa_vigente(fabrica_sesiones, escenario):
    """Garantiza una tasa de cambio vigente en plataforma.tasas_cambio."""
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
# CONTRAEJEMPLO J3: PRECIO Y PROMOCIÓN CONGELADOS EN LIQUIDACIÓN STRIPE
# =============================================================================

@pytest.mark.asyncio
async def test_subagente_b_j3_liquidar_con_precio_catalogo_modificado_mantiene_total_congelado(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J3: Iniciar venta Stripe a precio A (100 BOB) -> capturar PI válidamente ->
    modificar precio de catálogo a B (250 BOB).
    Al liquidar la venta presencial con las líneas de la venta iniciada:
    - Debe retornar 200/201 con el total congelado original (100.00 BOB).
    - NO debe recalcular con el nuevo precio de catálogo (250 BOB) ni arrojar 400 Bad Request.
    - El stock comprometido digitalmente se descuenta; NO se descuenta disponible libre dos veces.
    - Se emite Comprobante por el total congelado original (100.00 BOB).
    """
    http.usar(escenario.usuario_admin_a)

    # 1. Iniciar venta con precio de catálogo actual A = 100.00 BOB
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

    # 2. Capturar válidamente en pasarela y confirmar la orden de pago
    fake_stripe.intenciones[pi_id].estado = "SUCCEEDED"
    fake_stripe.intenciones[pi_id].metadata = {
        "empresa_id": str(escenario.empresa_a_id),
        "venta_id": str(venta_id),
    }

    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, orden_pago_id)
        assert op is not None
        op.estado = "CAPTURADO"
        await db.commit()

    # 3. Alterar el precio de la prenda en catálogo a B = 250.00 BOB
    async with fabrica_sesiones() as db:
        var = await db.get(VarianteProducto, escenario.variante_a_id)
        assert var is not None
        var.precio = Decimal("250.00")
        await db.commit()

        # Medir stock antes de liquidar
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_antes = (await db.execute(stmt_inv)).scalars().first()
        comp_antes = inv_antes.comprometido_digital
        disp_antes = inv_antes.disponible
        assert comp_antes >= 1

    # 4. Liquidar venta enviando las líneas de la orden iniciada (precio unitario 100 BOB)
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

    # El código no corregido falla aquí con HTTP 400 ("Precio unitario adulterado o desactualizado")
    assert resp_liq.status_code in (200, 201), f"Se esperaba éxito 200/201 con precio congelado, pero falló: {resp_liq.status_code} - {resp_liq.text}"
    liq_datos = resp_liq.json()
    assert Decimal(str(liq_datos["total_bob"])) == Decimal("100.00"), "El total liquidado debe ser el monto congelado de 100.00 BOB"
    assert liq_datos["estado_pago"] == "PAGADA"
    assert liq_datos["estado_entrega"] == "ENTREGADA"

    # 5. Comprobar que en la base de datos no se tocó el stock libre nuevamente y el Kardex es exacto
    async with fabrica_sesiones() as db:
        v_db = await db.get(Venta, venta_id)
        assert v_db.estado == "PAGADA"
        assert v_db.total == Decimal("100.00")

        inv_despues = (await db.execute(stmt_inv)).scalars().first()
        # El comprometido_digital se redujo en 1 unidad
        assert inv_despues.comprometido_digital == comp_antes - 1
        # El disponible libre NO se redujo dos veces
        assert inv_despues.disponible == disp_antes

        # Kardex VENTA_PRESENCIAL único emitido
        stmt_k = select(MovimientoInventario).where(
            MovimientoInventario.referencia_id == venta_id,
            MovimientoInventario.tipo == "VENTA_PRESENCIAL",
        )
        k_movs = (await db.execute(stmt_k)).scalars().all()
        assert len(k_movs) == 1
        assert k_movs[0].cantidad == 1

        # Comprobante emitido con el total congelado
        stmt_comp = select(Comprobante).where(
            Comprobante.recurso_id == venta_id,
            Comprobante.tipo == "VENTA_PRESENCIAL",
        )
        comp_db = (await db.execute(stmt_comp)).scalars().first()
        assert comp_db is not None
        assert Decimal(str(comp_db.documento["total_bob"])) == Decimal("100.00")


# =============================================================================
# CONTRAEJEMPLO J2: PASARELA CAÍDA EN LIQUIDACIÓN DEBE ARROJAR 502 Y NO SILENCIAR
# =============================================================================

@pytest.mark.asyncio
async def test_subagente_b_j2_liquidar_con_pasarela_caida_arroja_502_y_retiene_stock(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J2 en liquidación: Cuando gateway.consultar_intencion arroja excepción (red caída/timeout),
    el código anterior hacía `except Exception: pass` y permitía liquidar sin verificar con pasarela.
    La prueba exige que arroje HTTP 502 Bad Gateway y retenga la venta en PENDIENTE_PAGO y el stock pendiente.
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
    venta_id = uuid.UUID(datos_init["venta_id"])
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    pi_id = datos_init["stripe_payment_intent_id"]

    # Simular que la orden localmente aparece como CAPTURADO
    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, orden_pago_id)
        assert op is not None
        op.estado = "CAPTURADO"
        await db.commit()

        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_antes = (await db.execute(stmt_inv)).scalars().first()
        comp_antes = inv_antes.comprometido_digital

    # Simular fallo de red / timeout en Stripe Gateway
    class GatewayConFalloRed(FakeStripeGateway):
        async def consultar_intencion(self, payment_intent_id: str) -> IntencionPago:
            raise ConnectionError("Red caída / Timeout de conexión con api.stripe.com")

    gw_down = GatewayConFalloRed()
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

    # El código anterior silenciaba la excepción con pass y respondía 201.
    # Debe responder 502 Bad Gateway.
    assert resp_liq.status_code == 502, f"Se esperaba 502 Bad Gateway, pero respondió {resp_liq.status_code}: {resp_liq.text}"
    assert "no se pudo verificar el estado del pago en stripe" in resp_liq.json()["detail"].lower()

    # Verificar que la venta permanece PENDIENTE_PAGO y el stock sigue comprometido
    async with fabrica_sesiones() as db:
        v_db = await db.get(Venta, venta_id)
        assert v_db.estado == "PENDIENTE_PAGO", "La venta debe seguir PENDIENTE_PAGO"

        inv_despues = (await db.execute(stmt_inv)).scalars().first()
        assert inv_despues.comprometido_digital == comp_antes, "El inventario debe permanecer comprometido"

        # CERO movimientos de liquidación VENTA_PRESENCIAL
        stmt_k = select(func.count(MovimientoInventario.id)).where(
            MovimientoInventario.referencia_id == venta_id,
            MovimientoInventario.tipo == "VENTA_PRESENCIAL",
        )
        assert (await db.execute(stmt_k)).scalar() == 0


# =============================================================================
# CONTRAEJEMPLO J4: REANUDACIÓN DE ORDEN PROVISIONAL SIN DUPLICAR STOCK NI VENTA
# =============================================================================

@pytest.mark.asyncio
async def test_subagente_b_j4_reintento_orden_provisional_con_clave_durable_no_duplica_reservas(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """J4: Si ocurre un corte tras la Transacción 1 (orden provisional PENDIENTE_{clave}):
    El reintento con la misma clave durable idempotente:
    - Recupera la misma venta existente (no crea una segunda venta).
    - Asocia el PaymentIntent oficial de Stripe a la orden provisional.
    - CERO duplicación de reserva en inventario (comprometido_digital y Kardex COMPROMISO_DIGITAL).
    """
    http.usar(escenario.usuario_admin_a)
    clave_durable = uuid.uuid4()

    async with fabrica_sesiones() as db:
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_inicial = (await db.execute(stmt_inv)).scalars().first()
        comp_inicial = inv_inicial.comprometido_digital or 0
        disp_inicial = inv_inicial.disponible

    # Simular que durante el primer llamado a iniciar_stripe, la pasarela falla en el 2do commit o se desconecta
    class GatewayFallaPrimerIntento(FakeStripeGateway):
        def __init__(self):
            super().__init__()
            self.llamadas = 0

        async def crear_o_reutilizar_intencion(self, **kwargs) -> IntencionPago:
            self.llamadas += 1
            if self.llamadas == 1:
                # Simular excepción inesperada tras el commit 1
                raise RuntimeError("Caída de red simulada en pasarela tras registrar orden provisional")
            return await super().crear_o_reutilizar_intencion(**kwargs)

    gw_inestable = GatewayFallaPrimerIntento()
    fijar_gateway(gw_inestable)

    payload = {
        "sucursal_id": str(escenario.sucursal_a_id),
        "cliente_id": str(escenario.usuario_a.id),
        "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
    }

    # Primer intento: falla por la red tras haber comprometido inventario en Transacción 1
    with pytest.raises(Exception):
        await http.cliente.post(
            "/api/v1/ventas/presenciales/iniciar-stripe",
            json=payload,
            headers={"Idempotency-Key": str(clave_durable)},
        )

    # Verificar estado intermedio provisional en BD
    async with fabrica_sesiones() as db:
        stmt_v = select(Venta).where(Venta.clave_idempotencia == clave_durable)
        venta_prov = (await db.execute(stmt_v)).scalars().first()
        assert venta_prov is not None, "La venta provisional debió quedar registrada en Transacción 1"
        assert venta_prov.estado == "PENDIENTE_PAGO"

        stmt_op = select(OrdenPago).where(OrdenPago.venta_id == venta_prov.id)
        op_prov = (await db.execute(stmt_op)).scalars().first()
        assert op_prov is not None
        assert op_prov.clave_externa.startswith("PENDIENTE_")

        # El stock fue comprometido una sola vez
        inv_intermedio = (await db.execute(stmt_inv)).scalars().first()
        assert inv_intermedio.comprometido_digital == comp_inicial + 1
        assert inv_intermedio.disponible == disp_inicial - 1

    # Reintento con la misma clave durable
    resp_reintento = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json=payload,
        headers={"Idempotency-Key": str(clave_durable)},
    )
    assert resp_reintento.status_code == 201, resp_reintento.text
    datos_reintento = resp_reintento.json()
    assert datos_reintento["venta_id"] == str(venta_prov.id), "Debe reutilizar la misma venta provisional"
    assert datos_reintento["stripe_payment_intent_id"].startswith("pi_"), "Debe asociar un PI oficial"

    # Verificar que NO se duplicaron ventas, ni órdenes, ni movimientos Kardex COMPROMISO_DIGITAL
    async with fabrica_sesiones() as db:
        stmt_total_ventas = select(func.count(Venta.id)).where(Venta.clave_idempotencia == clave_durable)
        assert (await db.execute(stmt_total_ventas)).scalar() == 1, "Debe existir exactamente 1 venta"

        stmt_total_ordenes = select(func.count(OrdenPago.id)).where(OrdenPago.venta_id == venta_prov.id)
        assert (await db.execute(stmt_total_ordenes)).scalar() == 1, "Debe existir exactamente 1 orden de pago"

        stmt_k = select(func.count(MovimientoInventario.id)).where(
            MovimientoInventario.referencia_id == venta_prov.id,
            MovimientoInventario.tipo == "COMPROMISO_DIGITAL",
        )
        assert (await db.execute(stmt_k)).scalar() == 1, "Debe existir un único compromiso digital en Kardex"

        inv_final = (await db.execute(stmt_inv)).scalars().first()
        assert inv_final.comprometido_digital == comp_inicial + 1, "El stock no debe comprometerse doblemente"
        assert inv_final.disponible == disp_inicial - 1, "El disponible libre no debe descontarse dos veces"
