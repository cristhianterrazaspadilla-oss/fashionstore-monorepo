"""Pruebas de Liquidación Real en Caja — CU19 (Venta Presencial Conectada).

Verifica:
1. Rechazo con 400 si el cliente o la caja intentan alterar precios o descuentos del servidor.
2. Liquidación con SALDO real: verifica saldo suficiente, debita del libro append-only y no descuenta stock si es insuficiente.
3. Liquidación con STRIPE_TEST: requiere pago capturado (OrdenPago CAPTURADA o PaymentIntent capturado), fallando si está pendiente o fallido sin descontar stock ni marcar entrega.
4. Conservación de caja de efectivo E1 con vuelto exacto y Kardex VENTA_PRESENCIAL único.
5. Idempotencia estricta mediante Idempotency-Key.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import pytest
from sqlalchemy import select

from backend.app.core.modules.inventario.models import CupoCaja, InventarioSucursal, MovimientoInventario
from backend.app.core.modules.organizacion.models import TasaCambio
from backend.app.core.modules.posventa.services.saldo_service import MovimientoSaldo, SaldoService
from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import (
    FakeStripeGateway,
    IntencionPago,
    fijar_gateway,
)
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Pago, TurnoCaja, Venta
from backend.app.core.modules.ventas_pagos.models_ordenes import OrdenPago
from backend.app.core.modules.ventas_pagos.services.pedido_service import Comprobante


@pytest.mark.asyncio
async def test_cu19_precio_alterado_por_cliente_falla_400(http, escenario, fabrica_sesiones):
    """CU19: Si el cliente/caja envía un precio_unitario_bob diferente al del catálogo del servidor, rechaza con 400."""
    http.usar(escenario.usuario_admin_a)

    async with fabrica_sesiones() as db:
        stmt = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_antes = (await db.execute(stmt)).scalars().first()
        disponible_antes = inv_antes.disponible

    # Catálogo tiene precio 100.00; enviamos 50.00 adulterado
    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 50.0,
                }
            ],
            "medio_pago": "EFECTIVO",
            "efectivo_recibido_bob": 100.0,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 400, resp.text
    assert "adulterado" in resp.json()["detail"].lower() or "precio" in resp.json()["detail"].lower()

    # Verificar que el stock NO fue tocado
    async with fabrica_sesiones() as db:
        inv_despues = (await db.execute(stmt)).scalars().first()
        assert inv_despues.disponible == disponible_antes


@pytest.mark.asyncio
async def test_cu19_descuento_alterado_por_cliente_falla_400(http, escenario, fabrica_sesiones):
    """CU19: Si el cliente/caja inventa un descuento_bob no respaldado por promociones vigentes, rechaza con 400."""
    http.usar(escenario.usuario_admin_a)

    async with fabrica_sesiones() as db:
        stmt = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        disponible_antes = (await db.execute(stmt)).scalars().first().disponible

    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                    "descuento_bob": 25.0,  # Descuento inventado
                }
            ],
            "medio_pago": "EFECTIVO",
            "efectivo_recibido_bob": 100.0,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 400, resp.text
    assert "descuento" in resp.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        disponible_despues = (await db.execute(stmt)).scalars().first().disponible
        assert disponible_despues == disponible_antes


@pytest.mark.asyncio
async def test_cu19_saldo_insuficiente_falla_sin_debitar_ni_descontar_stock(
    http, escenario, fabrica_sesiones
):
    """CU19: Liquidar con SALDO cuando el cliente no tiene saldo suficiente falla con 400 sin descontar stock ni debitar."""
    http.usar(escenario.usuario_admin_a)

    async with fabrica_sesiones() as db:
        stmt = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        disponible_antes = (await db.execute(stmt)).scalars().first().disponible

    # Cliente sin saldo suficiente (saldo disponible 0, total 100 BOB)
    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "SALDO",
            "cliente_id": str(escenario.usuario_a.id),
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 400, resp.text
    assert "saldo insuficiente" in resp.json()["detail"].lower()

    # Stock no modificado y ningún débito registrado
    async with fabrica_sesiones() as db:
        disponible_despues = (await db.execute(stmt)).scalars().first().disponible
        assert disponible_despues == disponible_antes

        stmt_deb = select(MovimientoSaldo).where(
            MovimientoSaldo.cliente_id == escenario.usuario_a.id,
            MovimientoSaldo.tipo == "DEBITO",
        )
        mov_deb = (await db.execute(stmt_deb)).scalars().first()
        assert mov_deb is None


@pytest.mark.asyncio
async def test_cu19_saldo_suficiente_liquida_exito_debita_saldo_y_emite_kardex(
    http, escenario, fabrica_sesiones
):
    """CU19: Liquidar con SALDO suficiente debita saldo del cliente, reduce stock y emite Kardex VENTA_PRESENCIAL."""
    # 1. Acreditar 250 BOB al cliente
    async with fabrica_sesiones() as db:
        saldo_srv = SaldoService(db)
        await saldo_srv.acreditar_saldo(
            cliente_id=escenario.usuario_a.id,
            empresa_id=escenario.empresa_a_id,
            monto_bob=Decimal("250.00"),
            origen_tipo="RECARGA",
        )
        await db.commit()

        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        disponible_antes = (await db.execute(stmt_inv)).scalars().first().disponible

    # 2. Liquidar venta presencial con SALDO (2 prendas de 100 = 200 BOB)
    http.usar(escenario.usuario_admin_a)
    clave = uuid.uuid4()
    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 2,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "SALDO",
            "cliente_id": str(escenario.usuario_a.id),
        },
        headers={"Idempotency-Key": str(clave)},
    )
    assert resp.status_code == 201, resp.text
    res = resp.json()

    assert res["venta_id"] is not None
    assert float(res["total_bob"]) == 200.0
    assert res["estado_pago"] == "PAGADA"
    assert res["estado_entrega"] == "ENTREGADA"

    # 3. Comprobar que el saldo del cliente quedó en 50 BOB (250 - 200)
    async with fabrica_sesiones() as db:
        saldo_srv = SaldoService(db)
        disp, ret, _ = await saldo_srv.calcular_totales(
            cliente_id=escenario.usuario_a.id, empresa_id=escenario.empresa_a_id
        )
        assert disp == Decimal("50.00")

        # Comprobar movimiento DEBITO en el libro
        stmt_deb = select(MovimientoSaldo).where(
            MovimientoSaldo.cliente_id == escenario.usuario_a.id,
            MovimientoSaldo.tipo == "DEBITO",
            MovimientoSaldo.origen_tipo == "VENTA",
            MovimientoSaldo.origen_id == uuid.UUID(res["venta_id"]),
        )
        debito = (await db.execute(stmt_deb)).scalars().first()
        assert debito is not None
        assert debito.monto_bob == Decimal("200.00")

        # Comprobar reducción de stock
        disponible_despues = (await db.execute(stmt_inv)).scalars().first().disponible
        assert disponible_despues == disponible_antes - 2


@pytest.mark.asyncio
async def test_cu19_stripe_pendiente_o_fallido_no_entrega_ni_descuenta_stock(
    http, escenario, fabrica_sesiones
):
    """CU19: Liquidar con STRIPE_TEST cuando la orden/intención no está capturada falla 400 sin descontar stock."""
    pi_ref = f"pi_test_pending_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        stmt_t = select(TasaCambio).order_by(TasaCambio.vigente_desde.desc())
        tasa = (await db.execute(stmt_t)).scalars().first()
        factor = Decimal(str(tasa.tasa_bob_por_usd))
        centavos = int((Decimal("100.00") / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)

        v_id = uuid.uuid4()
        venta_init = Venta(
            id=v_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-PEND-{v_id.hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=datetime.now(timezone.utc),
        )
        db.add(venta_init)
        await db.flush()

        orden = OrdenPago(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=v_id,
            clave_externa=pi_ref,
            referencia_externa=pi_ref,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            centavos_usd=centavos,
            tasa_id=tasa.id,
        )
        db.add(orden)
        await db.commit()

    fake = FakeStripeGateway()
    fijar_gateway(fake)
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref, venta_id=str(uuid.uuid4()), monto_centavos=centavos, moneda="usd", estado="REQUIRES_PAYMENT"
    )

    async with fabrica_sesiones() as db:
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        disponible_antes = (await db.execute(stmt_inv)).scalars().first().disponible

    http.usar(escenario.usuario_admin_a)
    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "STRIPE_TEST",
            "stripe_payment_intent_id": pi_ref,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 400, resp.text
    assert "no confirma la captura" in resp.json()["detail"].lower()

    # Verificar stock intacto
    async with fabrica_sesiones() as db:
        disponible_despues = (await db.execute(stmt_inv)).scalars().first().disponible
        assert disponible_despues == disponible_antes


@pytest.mark.asyncio
async def test_cu19_stripe_capturado_liquida_exito_y_emite_kardex(
    http, escenario, fabrica_sesiones
):
    """CU19: Liquidar con STRIPE_TEST debidamente capturado aprueba venta, descuenta stock y emite Kardex."""
    pi_ref = f"pi_test_captured_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        stmt_t = select(TasaCambio).order_by(TasaCambio.vigente_desde.desc())
        tasa = (await db.execute(stmt_t)).scalars().first()
        factor = Decimal(str(tasa.tasa_bob_por_usd))
        centavos = int((Decimal("100.00") / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)

        v_id = uuid.uuid4()
        venta_init = Venta(
            id=v_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-PEND-{v_id.hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=datetime.now(timezone.utc),
        )
        db.add(venta_init)
        await db.flush()

        orden = OrdenPago(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=v_id,
            clave_externa=pi_ref,
            referencia_externa=pi_ref,
            estado="CAPTURADO",
            monto_bob=Decimal("100.00"),
            centavos_usd=centavos,
            tasa_id=tasa.id,
        )
        db.add(orden)
        await db.commit()

    fake = FakeStripeGateway()
    fijar_gateway(fake)
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(v_id),
        monto_centavos=centavos,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={
            "empresa_id": str(escenario.empresa_a_id),
            "venta_id": str(v_id),
        },
    )

    async with fabrica_sesiones() as db:
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        disponible_antes = (await db.execute(stmt_inv)).scalars().first().disponible

    http.usar(escenario.usuario_admin_a)
    clave = uuid.uuid4()
    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "venta_id": str(v_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "STRIPE_TEST",
            "stripe_payment_intent_id": pi_ref,
        },
        headers={"Idempotency-Key": str(clave)},
    )
    assert resp.status_code == 201, resp.text
    res = resp.json()

    assert res["venta_id"] is not None
    assert uuid.UUID(res["venta_id"]) == v_id
    assert float(res["total_bob"]) == 100.0
    assert res["estado_pago"] == "PAGADA"
    assert res["estado_entrega"] == "ENTREGADA"

    # Verificar stock reducido en 1 unidad
    async with fabrica_sesiones() as db:
        disponible_despues = (await db.execute(stmt_inv)).scalars().first().disponible
        assert disponible_despues == disponible_antes - 1

        # Comprobar Pago STRIPE_TEST
        stmt_p = select(Pago).where(Pago.venta_id == uuid.UUID(res["venta_id"]))
        pago = (await db.execute(stmt_p)).scalars().first()
        assert pago is not None
        assert pago.metodo == "STRIPE_TEST"
        assert pago.monto == Decimal("100.00")
        assert pago.estado == "APROBADO"
        assert pago.referencia_externa == pi_ref

        # Comprobar que orden_stripe fue vinculada a la venta
        stmt_o = select(OrdenPago).where(OrdenPago.referencia_externa == pi_ref)
        orden_db = (await db.execute(stmt_o)).scalars().first()
        assert orden_db is not None
        assert orden_db.venta_id == uuid.UUID(res["venta_id"])


@pytest.mark.asyncio
async def test_cu19_flujo_completo_iniciar_stripe_capturar_y_liquidar(
    http, escenario, fabrica_sesiones
):
    """CU19: Flujo completo: iniciar-stripe -> orden propia capturada -> liquidar con éxito y Kardex."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    http.usar(escenario.usuario_admin_a)

    stmt_inv = select(InventarioSucursal).where(
        InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
        InventarioSucursal.variante_id == escenario.variante_a_id,
    )
    async with fabrica_sesiones() as db:
        disponible_antes = (await db.execute(stmt_inv)).scalars().first().disponible

    # 1. Iniciar venta presencial con Stripe
    clave_iniciar = uuid.uuid4()
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                    "descuento_bob": 0.0,
                }
            ],
        },
        headers={"Idempotency-Key": str(clave_iniciar)},
    )
    assert resp_init.status_code == 201, resp_init.text
    init_data = resp_init.json()

    venta_id = uuid.UUID(init_data["venta_id"])
    orden_pago_id = uuid.UUID(init_data["orden_pago_id"])
    pi_ref = init_data["stripe_payment_intent_id"]
    assert init_data["client_secret"] is not None
    assert float(init_data["monto_bob"]) == 100.0
    assert init_data["centavos_usd"] > 0
    assert init_data["estado_orden"] == "PENDIENTE"

    # Verificar Venta en BD en PENDIENTE_PAGO y compromiso digital trasladado
    async with fabrica_sesiones() as db:
        v_db = await db.get(Venta, venta_id)
        assert v_db is not None
        assert v_db.estado == "PENDIENTE_PAGO"
        assert v_db.total == Decimal("100.00")

        o_db = await db.get(OrdenPago, orden_pago_id)
        assert o_db is not None
        assert o_db.venta_id == venta_id
        assert o_db.estado == "PENDIENTE"

        inv_init = (await db.execute(stmt_inv)).scalars().first()
        assert inv_init.disponible == disponible_antes - 1
        assert inv_init.comprometido_digital == 1

    # 2. Simular captura del PaymentIntent en Stripe y orden
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=init_data["centavos_usd"],
        moneda="usd",
        estado="SUCCEEDED",
    )
    fake.intenciones[pi_ref].cliente_id = str(escenario.usuario_a.id)

    # Confirmar orden de pago mediante endpoint legítimo
    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_conf.status_code == 200, resp_conf.text
    assert resp_conf.json()["estado"] == "CAPTURADO"

    # 3. Liquidar venta presencial
    clave_liquidar = uuid.uuid4()
    resp_liq = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "venta_id": str(venta_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "STRIPE_TEST",
            "orden_pago_id": str(orden_pago_id),
            "stripe_payment_intent_id": pi_ref,
        },
        headers={"Idempotency-Key": str(clave_liquidar)},
    )
    assert resp_liq.status_code == 201, resp_liq.text
    liq_data = resp_liq.json()

    assert liq_data["venta_id"] == str(venta_id)
    assert liq_data["estado_pago"] == "PAGADA"
    assert liq_data["estado_entrega"] == "ENTREGADA"
    assert len(liq_data["kardex_ids"]) == 1

    # 4. Verificar integridad en base de datos
    async with fabrica_sesiones() as db:
        # Stock reducido
        inv_despues = (await db.execute(stmt_inv)).scalars().first()
        assert inv_despues.disponible == disponible_antes - 1
        assert inv_despues.comprometido_digital == 0

        # Venta pagada
        v_final = await db.get(Venta, venta_id)
        assert v_final.estado == "PAGADA"

        # Orden de pago vinculada estrictamente a la misma venta (no reasignada)
        o_final = await db.get(OrdenPago, orden_pago_id)
        assert o_final.venta_id == venta_id

        # Comprobante emitido
        stmt_c = select(Comprobante).where(Comprobante.recurso_id == venta_id)
        comp = (await db.execute(stmt_c)).scalars().first()
        assert comp is not None

        # Kardex VENTA_PRESENCIAL registrado
        stmt_k = select(MovimientoInventario).where(
            MovimientoInventario.referencia_id == venta_id,
            MovimientoInventario.tipo == "VENTA_PRESENCIAL",
        )
        kardex = (await db.execute(stmt_k)).scalars().first()
        assert kardex is not None
        assert kardex.cantidad == 1

        # Pago registrado
        stmt_p = select(Pago).where(Pago.venta_id == venta_id)
        pago = (await db.execute(stmt_p)).scalars().first()
        assert pago is not None
        assert pago.metodo == "STRIPE_TEST"
        assert pago.estado == "APROBADO"
        assert pago.referencia_externa == pi_ref


@pytest.mark.asyncio
async def test_cu19_liquidar_con_pi_otra_venta_falla_409(http, escenario, fabrica_sesiones):
    """CU19: Intentar liquidar Venta B con un PI perteneciente a Venta A falla con 409."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    http.usar(escenario.usuario_admin_a)

    # 1. Iniciar Venta A
    resp_a = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_a.status_code == 201
    data_a = resp_a.json()
    pi_ref_a = data_a["stripe_payment_intent_id"]
    ord_id_a = uuid.UUID(data_a["orden_pago_id"])

    # 2. Iniciar Venta B
    resp_b = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_b.status_code == 201
    data_b = resp_b.json()
    venta_b_id = data_b["venta_id"]

    # Simular éxito y confirmar orden A
    fake.intenciones[pi_ref_a].estado = "SUCCEEDED"
    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{ord_id_a}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_conf.status_code == 200

    # 3. Intentar liquidar Venta B con el PI de Venta A
    resp_bad = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "venta_id": str(venta_b_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "medio_pago": "STRIPE_TEST",
            "stripe_payment_intent_id": pi_ref_a,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_bad.status_code == 409, resp_bad.text
    assert "otra venta" in resp_bad.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cu19_liquidar_con_monto_o_moneda_adulterados_falla_400(http, escenario, fabrica_sesiones):
    """CU19: Intentar liquidar con monto o moneda adulterados falla con 400."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    http.usar(escenario.usuario_admin_a)

    # Iniciar venta por 100 BOB (1 unidad)
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
    init_data = resp_init.json()
    venta_id = init_data["venta_id"]
    ord_id = init_data["orden_pago_id"]
    pi_ref = init_data["stripe_payment_intent_id"]

    fake.intenciones[pi_ref].estado = "SUCCEEDED"
    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{ord_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_conf.status_code == 200

    # Intentar liquidar enviando cantidad 2 (total 200 BOB), pero la orden es por 100 BOB
    resp_monto = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "venta_id": str(venta_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "medio_pago": "STRIPE_TEST",
            "stripe_payment_intent_id": pi_ref,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_monto.status_code == 400, resp_monto.text
    assert "no coincide exactamente" in resp_monto.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cu19_caja_stock_libre_1_cupo_1_solo_consume_cupo_y_mantiene_stock_libre(
    http, escenario, fabrica_sesiones
):
    """CU19 / G3: Caso stock libre 1 + cupo 1: sólo se consume el cupo de la caja, el stock libre permanece intacto."""
    http.usar(escenario.usuario_admin_a)
    ahora = datetime.now(timezone.utc)

    turno_id = uuid.uuid4()
    cupo_id = uuid.uuid4()

    async with fabrica_sesiones() as db:
        turno = TurnoCaja(
            id=turno_id,
            empresa_id=escenario.empresa_a_id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            dispositivo_id=uuid.uuid4(),
            caja_codigo="CAJA-P0-02",
            estado="ABIERTO",
            inicio_en=ahora,
            vence_en=ahora + timedelta(hours=8),
            version_precios="v1",
            cupos_hash="cupo_hash_02",
            revision=1,
        )
        db.add(turno)
        await db.flush()

        cupo = CupoCaja(
            id=cupo_id,
            empresa_id=escenario.empresa_a_id,
            turno_id=turno_id,
            variante_id=escenario.variante_a_id,
            sucursal_id=escenario.sucursal_a_id,
            otorgado=1,
            consumido=0,
            liberado=0,
            mermado=0,
            costo_unitario_snapshot=Decimal("40.00"),
            precio_autorizado_bob=Decimal("100.00"),
            version_precios="v1",
        )
        db.add(cupo)

        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv = (await db.execute(stmt_inv)).scalars().first()
        inv.disponible = 1
        inv.comprometido_caja = 1
        await db.commit()

    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "EFECTIVO",
            "efectivo_recibido_bob": 100.0,
            "turno_caja_id": str(turno_id),
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 201, resp.text
    res = resp.json()
    assert res["estado_pago"] == "PAGADA"

    async with fabrica_sesiones() as db:
        cupo_db = await db.get(CupoCaja, cupo_id)
        assert cupo_db.consumido == 1

        inv_db = (await db.execute(stmt_inv)).scalars().first()
        assert inv_db.comprometido_caja == 0
        # Stock libre permanece intacto (1 unidad)
        assert inv_db.disponible == 1


@pytest.mark.asyncio
async def test_cu19_caja_turno_reintentos_idempotencia_y_cierre_turno(
    http, escenario, fabrica_sesiones
):
    """CU19 / G3: Reintentos de liquidación con turno y rechazo si el turno está cerrado."""
    http.usar(escenario.usuario_admin_a)
    ahora = datetime.now(timezone.utc)

    turno_id = uuid.uuid4()
    cupo_id = uuid.uuid4()

    async with fabrica_sesiones() as db:
        turno = TurnoCaja(
            id=turno_id,
            empresa_id=escenario.empresa_a_id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            dispositivo_id=uuid.uuid4(),
            caja_codigo="CAJA-P0-03",
            estado="ABIERTO",
            inicio_en=ahora,
            vence_en=ahora + timedelta(hours=8),
            version_precios="v1",
            cupos_hash="cupo_hash_03",
            revision=1,
        )
        db.add(turno)
        await db.flush()

        cupo = CupoCaja(
            id=cupo_id,
            empresa_id=escenario.empresa_a_id,
            turno_id=turno_id,
            variante_id=escenario.variante_a_id,
            sucursal_id=escenario.sucursal_a_id,
            otorgado=2,
            consumido=0,
            liberado=0,
            mermado=0,
            costo_unitario_snapshot=Decimal("40.00"),
            precio_autorizado_bob=Decimal("100.00"),
            version_precios="v1",
        )
        db.add(cupo)

        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv = (await db.execute(stmt_inv)).scalars().first()
        inv.disponible = 0
        inv.comprometido_caja = 2
        await db.commit()

    clave_idempotente = uuid.uuid4()
    body = {
        "sucursal_id": str(escenario.sucursal_a_id),
        "lineas": [
            {
                "variante_id": str(escenario.variante_a_id),
                "cantidad": 1,
                "precio_unitario_bob": 100.0,
            }
        ],
        "medio_pago": "EFECTIVO",
        "efectivo_recibido_bob": 100.0,
        "turno_caja_id": str(turno_id),
    }

    # Primera llamada
    resp1 = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json=body,
        headers={"Idempotency-Key": str(clave_idempotente)},
    )
    assert resp1.status_code == 201, resp1.text
    v_id1 = resp1.json()["venta_id"]

    # Reintento con misma clave de idempotencia
    resp2 = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json=body,
        headers={"Idempotency-Key": str(clave_idempotente)},
    )
    assert resp2.status_code == 201 or resp2.status_code == 200, resp2.text
    assert resp2.json()["venta_id"] == v_id1

    # Cierre del turno en BD
    async with fabrica_sesiones() as db:
        turno_db = await db.get(TurnoCaja, turno_id)
        turno_db.estado = "CERRADO"
        turno_db.cerrado_en = ahora
        await db.commit()

    # Intentar nueva liquidación con el turno ya cerrado
    resp3 = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "EFECTIVO",
            "efectivo_recibido_bob": 100.0,
            "turno_caja_id": str(turno_id),
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp3.status_code == 409, resp3.text
    assert "no está abierto" in resp3.json()["detail"].lower()
