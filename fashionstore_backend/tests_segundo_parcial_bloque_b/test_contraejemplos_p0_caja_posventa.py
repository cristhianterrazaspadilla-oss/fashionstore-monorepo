"""Pruebas de Contraejemplos P0: Caja y Posventa (C1 y C4).

Cubre:
1. CU19 Caja — Reúso de stripe_payment_intent_id falla con 409 Conflict.
2. CU19 Caja — Intento de usar cargo de otro cliente u otra empresa es rechazado.
3. CU19 Caja — Intento de liquidar con monto o moneda incongruente falla con 400 Bad Request.
4. CU19 Caja — Descuento de stock rechazado si la liquidación falla (garantía de integridad física).
5. CU20 Posventa — Devolución fuera de plazo (15 días): rechazo de voluntaria vs admisión en PENDIENTE_EVALUACION con defecto.
6. CU08 Posventa — Cambio con resolución simultánea saldo + reembolso es rechazado con 400 Bad Request.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import pytest
from sqlalchemy import select

from backend.app.core.modules.identidad_empresas.models import Cliente, Usuario
from backend.app.core.modules.inventario.models import CupoCaja, InventarioSucursal, MovimientoInventario
from backend.app.core.modules.organizacion.models import TasaCambio
from backend.app.core.modules.posventa.services.cambio_service import Cambio, DetalleCambio, MovimientoSaldo
from backend.app.core.modules.posventa.services.devolucion_service import Devolucion, DetalleDevolucion
from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import (
    FakeStripeGateway,
    IntencionPago,
    fijar_gateway,
)
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Pago, TurnoCaja, Venta
from backend.app.core.modules.ventas_pagos.models_ordenes import OrdenPago
from backend.app.core.modules.ventas_pagos.services.pedido_service import ObligacionReembolso


async def _crear_venta_para_posventa(
    escenario, fabrica_sesiones, cantidad: int = 1, entregada: bool = True, dias_antiguedad: int = 0
) -> tuple[uuid.UUID, uuid.UUID]:
    """Helper para crear venta pagada en base de datos con fecha de entrega controlada."""
    async with fabrica_sesiones() as db:
        venta_id = uuid.uuid4()
        det_id = uuid.uuid4()
        ahora = datetime.now(timezone.utc)
        fecha_creacion = ahora - timedelta(days=dias_antiguedad)
        fecha_entrega = (ahora - timedelta(days=dias_antiguedad)) if entregada else None

        venta = Venta(
            id=venta_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PAGADA",
            subtotal=Decimal("100.00") * cantidad,
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00") * cantidad,
            creada_en=fecha_creacion,
            confirmada_en=fecha_creacion,
            entregada_en=fecha_entrega,
        )
        db.add(venta)

        det = DetalleVenta(
            id=det_id,
            venta_id=venta_id,
            variante_id=escenario.variante_a_id,
            cantidad=cantidad,
            precio_unitario=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_promedio=Decimal("40.00"),
        )
        db.add(det)
        await db.commit()
        return venta_id, det_id


async def _crear_orden_stripe_db(
    fabrica_sesiones,
    empresa_id: uuid.UUID,
    cliente_id: uuid.UUID,
    sucursal_id: uuid.UUID,
    pi_ref: str,
    total_bob: Decimal = Decimal("100.00"),
    centavos_usd: int | None = None,
    estado: str = "CAPTURADO",
    tasa_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID, int]:
    """Helper para crear Venta previa en PENDIENTE_PAGO y OrdenPago válida para liquidación presencial."""
    async with fabrica_sesiones() as db:
        if tasa_id is None:
            stmt_t = select(TasaCambio).order_by(TasaCambio.vigente_desde.desc())
            tasa = (await db.execute(stmt_t)).scalars().first()
            tasa_id = tasa.id
            factor = Decimal(str(tasa.tasa_bob_por_usd))
        else:
            tasa = await db.get(TasaCambio, tasa_id)
            factor = Decimal(str(tasa.tasa_bob_por_usd))

        if centavos_usd is None:
            centavos_usd = int((total_bob / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)

        v_id = uuid.uuid4()
        venta_init = Venta(
            id=v_id,
            empresa_id=empresa_id,
            numero=f"VTA-PEND-{v_id.hex[:6]}",
            cliente_id=cliente_id,
            sucursal_id=sucursal_id,
            cajero_id=None,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=total_bob,
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=total_bob,
            creada_en=datetime.now(timezone.utc),
        )
        db.add(venta_init)
        await db.flush()

        orden = OrdenPago(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            contexto="VENTA",
            venta_id=v_id,
            clave_externa=pi_ref,
            referencia_externa=pi_ref,
            estado=estado,
            monto_bob=total_bob,
            centavos_usd=centavos_usd,
            tasa_id=tasa_id,
        )
        db.add(orden)
        await db.commit()
        return v_id, orden.id, centavos_usd


# ============================================================================
# C1: CU19 CAJA Y VENTA PRESENCIAL CONECTADA
# ============================================================================

@pytest.mark.asyncio
async def test_contraejemplo_c1_reuso_stripe_payment_intent_falla_409(http, escenario, fabrica_sesiones):
    """Contraejemplo C1.1: Reutilizar el mismo stripe_payment_intent_id para liquidar una segunda venta falla 409."""
    pi_ref = f"pi_test_reused_{uuid.uuid4().hex[:8]}"
    venta_id, _, centavos = await _crear_orden_stripe_db(
        fabrica_sesiones,
        empresa_id=escenario.empresa_a_id,
        cliente_id=escenario.usuario_a.id,
        sucursal_id=escenario.sucursal_a_id,
        pi_ref=pi_ref,
    )

    fake = FakeStripeGateway()
    fijar_gateway(fake)
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=centavos,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(venta_id)},
    )

    http.usar(escenario.usuario_admin_a)

    # 1. Primera liquidación exitosa
    resp1 = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
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
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp1.status_code == 201, resp1.text

    # 2. Intento de liquidar segunda venta distinta con el MISMO cargo Stripe
    resp2 = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
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
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp2.status_code == 409, resp2.text
    assert (
        "consumido" in resp2.json()["detail"].lower()
        or "utilizado" in resp2.json()["detail"].lower()
        or "aplicado" in resp2.json()["detail"].lower()
        or "liquidada" in resp2.json()["detail"].lower()
    )


@pytest.mark.asyncio
async def test_contraejemplo_c1_stripe_cargo_otro_cliente_o_empresa_rechazado(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo C1.2: Rechazar cargos Stripe pertenecientes a otro cliente o a otra empresa."""
    # Crear un segundo cliente dentro de la misma empresa A para probar pertenencia a otro cliente
    async with fabrica_sesiones() as db:
        otro_cliente = Usuario(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            rol_id=escenario.usuario_a.rol_id,
            nombres="Otro",
            apellidos=f"Cliente A {uuid.uuid4().hex[:6]}",
            correo_electronico=f"otro_a_{uuid.uuid4().hex[:6]}@test.local",
            contrasenia_hash="no-usar",
            estado="ACTIVO",
        )
        db.add(otro_cliente)
        await db.flush()
        db.add(Cliente(usuario_id=otro_cliente.id, direccion_referencia="Zona Otro"))
        await db.commit()

    pi_cliente_b = f"pi_test_cliente_b_{uuid.uuid4().hex[:8]}"
    venta_b_id, _, centavos_b = await _crear_orden_stripe_db(
        fabrica_sesiones,
        empresa_id=escenario.empresa_a_id,
        cliente_id=otro_cliente.id,
        sucursal_id=escenario.sucursal_a_id,
        pi_ref=pi_cliente_b,
    )

    fake = FakeStripeGateway()
    fijar_gateway(fake)
    intencion_b = IntencionPago(
        id=pi_cliente_b,
        venta_id=str(venta_b_id),
        monto_centavos=centavos_b,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(venta_b_id)},
    )
    intencion_b.cliente_id = str(otro_cliente.id)
    fake.intenciones[pi_cliente_b] = intencion_b

    http.usar(escenario.usuario_admin_a)
    resp_cli = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
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
            "stripe_payment_intent_id": pi_cliente_b,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_cli.status_code == 400, resp_cli.text
    assert "otro cliente" in resp_cli.json()["detail"].lower()

    # Caso A2: Intento de usar cargo de cliente B omitiendo cliente_id en la solicitud
    resp_cli_anon = await http.cliente.post(
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
            "stripe_payment_intent_id": pi_cliente_b,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_cli_anon.status_code == 400, resp_cli_anon.text
    assert "otro cliente" in resp_cli_anon.json()["detail"].lower()

    # Caso B: OrdenPago en BD perteneciente a empresa B, liquidando en sucursal/empresa A
    pi_empresa_b = f"pi_test_empresa_b_{uuid.uuid4().hex[:8]}"
    _, _, centavos_emp_b = await _crear_orden_stripe_db(
        fabrica_sesiones,
        empresa_id=escenario.empresa_b_id,
        cliente_id=escenario.usuario_b.id,
        sucursal_id=escenario.sucursal_b_id,
        pi_ref=pi_empresa_b,
    )
    fake.intenciones[pi_empresa_b] = IntencionPago(
        id=pi_empresa_b, venta_id=str(uuid.uuid4()), monto_centavos=centavos_emp_b, moneda="usd", estado="SUCCEEDED"
    )

    resp_emp = await http.cliente.post(
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
            "stripe_payment_intent_id": pi_empresa_b,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_emp.status_code == 403, resp_emp.text
    assert "otra empresa" in resp_emp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_contraejemplo_c1_stripe_monto_o_moneda_incongruente_falla_400(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo C1.3: Liquidación con moneda no soportada o monto en centavos insuficiente falla 400."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    http.usar(escenario.usuario_admin_a)

    # 1. Moneda no soportada (EUR)
    pi_eur = f"pi_test_eur_{uuid.uuid4().hex[:8]}"
    venta_id, _, centavos = await _crear_orden_stripe_db(
        fabrica_sesiones,
        empresa_id=escenario.empresa_a_id,
        cliente_id=escenario.usuario_a.id,
        sucursal_id=escenario.sucursal_a_id,
        pi_ref=pi_eur,
    )
    fake.intenciones[pi_eur] = IntencionPago(
        id=pi_eur, venta_id=str(uuid.uuid4()), monto_centavos=centavos, moneda="eur", estado="SUCCEEDED"
    )

    resp_eur = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
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
            "stripe_payment_intent_id": pi_eur,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_eur.status_code == 400, resp_eur.text
    assert "moneda" in resp_eur.json()["detail"].lower()

    # 2. Monto USD insuficiente (10 centavos en la orden cuando se requieren ~1408 centavos para 100 BOB)
    pi_low = f"pi_test_low_{uuid.uuid4().hex[:8]}"
    await _crear_orden_stripe_db(
        fabrica_sesiones,
        empresa_id=escenario.empresa_a_id,
        cliente_id=escenario.usuario_a.id,
        sucursal_id=escenario.sucursal_a_id,
        pi_ref=pi_low,
        centavos_usd=10,
    )
    fake.intenciones[pi_low] = IntencionPago(
        id=pi_low, venta_id=str(uuid.uuid4()), monto_centavos=10, moneda="usd", estado="SUCCEEDED"
    )

    resp_low = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
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
            "stripe_payment_intent_id": pi_low,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_low.status_code == 400, resp_low.text
    assert "centavos" in resp_low.json()["detail"].lower() or "coinciden" in resp_low.json()["detail"].lower()


@pytest.mark.asyncio
async def test_contraejemplo_c1_descuento_stock_rechazado_si_liquidacion_falla(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo C1.4: Si la liquidación falla por cualquier motivo, el stock permanece intacto sin Kardex."""
    pi_pending = f"pi_test_pending_{uuid.uuid4().hex[:8]}"
    venta_id, _, centavos = await _crear_orden_stripe_db(
        fabrica_sesiones,
        empresa_id=escenario.empresa_a_id,
        cliente_id=escenario.usuario_a.id,
        sucursal_id=escenario.sucursal_a_id,
        pi_ref=pi_pending,
        total_bob=Decimal("200.00"),
        estado="PENDIENTE",
    )
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    fake.intenciones[pi_pending] = IntencionPago(
        id=pi_pending, venta_id=str(uuid.uuid4()), monto_centavos=centavos, moneda="usd", estado="REQUIRES_PAYMENT"
    )

    async with fabrica_sesiones() as db:
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        disponible_antes = (await db.execute(stmt_inv)).scalars().first().disponible

        stmt_kardex_antes = select(MovimientoInventario).where(
            MovimientoInventario.tipo == "VENTA_PRESENCIAL"
        )
        total_kardex_antes = len((await db.execute(stmt_kardex_antes)).scalars().all())

    http.usar(escenario.usuario_admin_a)

    # 1. Intento fallido con Stripe no capturado
    resp_stripe_fail = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 2,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "STRIPE_TEST",
            "stripe_payment_intent_id": pi_pending,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_stripe_fail.status_code == 400

    # 2. Intento fallido con EFECTIVO insuficiente
    resp_cash_fail = await http.cliente.post(
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
            "medio_pago": "EFECTIVO",
            "efectivo_recibido_bob": 50.0,  # Requiere 200.0
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_cash_fail.status_code == 400

    # 3. Verificar que el inventario disponible no se modificó en absoluto y no hay nuevo Kardex
    async with fabrica_sesiones() as db:
        disponible_despues = (await db.execute(stmt_inv)).scalars().first().disponible
        assert disponible_despues == disponible_antes

        total_kardex_despues = len((await db.execute(stmt_kardex_antes)).scalars().all())
        assert total_kardex_despues == total_kardex_antes


@pytest.mark.asyncio
async def test_contraejemplo_c1_payment_intent_sin_orden_interna_falla_400(
    http, escenario
):
    """Contraejemplo C1.5: PaymentIntent sin OrdenPago interna creada por FashionStore falla 400."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    pi_huerfano = f"pi_test_sin_orden_{uuid.uuid4().hex[:8]}"
    fake.intenciones[pi_huerfano] = IntencionPago(
        id=pi_huerfano, venta_id=str(uuid.uuid4()), monto_centavos=1437, moneda="usd", estado="SUCCEEDED"
    )

    http.usar(escenario.usuario_admin_a)
    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
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
            "stripe_payment_intent_id": pi_huerfano,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 400, resp.text
    assert "orden de pago" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_contraejemplo_c1_concurrencia_caja_mismo_cargo_stripe_solo_una_pasa(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo C1.6: Demuestra que ante dos liquidaciones concurrentes con VARIANTES DISTINTAS que intentan
    usar el MISMO cargo Stripe:
    - Exactamente UNA venta se liquida (201) y solo el stock de su variante se descuenta.
    - La otra falla con 409 Conflict y el stock de su variante queda intacto.
    - Se garantiza integridad física sin sobreventa ni cobro duplicado."""
    pi_ref = f"pi_test_concurrente_{uuid.uuid4().hex[:8]}"
    venta_id, _, centavos = await _crear_orden_stripe_db(
        fabrica_sesiones,
        empresa_id=escenario.empresa_a_id,
        cliente_id=escenario.usuario_a.id,
        sucursal_id=escenario.sucursal_a_id,
        pi_ref=pi_ref,
        total_bob=Decimal("100.00"),
    )

    fake = FakeStripeGateway()
    fijar_gateway(fake)
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=centavos,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(venta_id)},
    )

    # 1. Consultar stock inicial de las DOS variantes distintas
    async with fabrica_sesiones() as db:
        inv_a = (await db.execute(
            select(InventarioSucursal).where(
                InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                InventarioSucursal.variante_id == escenario.variante_a_id,
            )
        )).scalars().first()
        stock_a_inicial = inv_a.disponible

        inv_ultima = (await db.execute(
            select(InventarioSucursal).where(
                InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                InventarioSucursal.variante_id == escenario.variante_ultima_id,
            )
        )).scalars().first()
        stock_ultima_inicial = inv_ultima.disponible

    import asyncio

    # 2. Dos peticiones concurrentes con VARIANTES DISTINTAS pero el MISMO cargo Stripe
    async def liquidar_variante_a():
        return await http.cliente.post(
            "/api/v1/ventas/presenciales/liquidar",
            json={
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
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )

    async def liquidar_variante_ultima():
        return await http.cliente.post(
            "/api/v1/ventas/presenciales/liquidar",
            json={
                "sucursal_id": str(escenario.sucursal_a_id),
                "cliente_id": str(escenario.usuario_a.id),
                "lineas": [
                    {
                        "variante_id": str(escenario.variante_ultima_id),
                        "cantidad": 1,
                        "precio_unitario_bob": 100.0,
                    }
                ],
                "medio_pago": "STRIPE_TEST",
                "stripe_payment_intent_id": pi_ref,
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )

    http.usar(escenario.usuario_admin_a)
    r1, r2 = await asyncio.gather(liquidar_variante_a(), liquidar_variante_ultima())

    status_codes = sorted([r1.status_code, r2.status_code])
    assert status_codes == [201, 409], f"Se esperaba [201, 409], pero se obtuvo {status_codes}. R1: {r1.text}, R2: {r2.text}"

    resp_201 = r1 if r1.status_code == 201 else r2
    resp_409 = r1 if r1.status_code == 409 else r2
    assert (
        "aplicado" in resp_409.json()["detail"].lower()
        or "otra venta" in resp_409.json()["detail"].lower()
        or "liquidada" in resp_409.json()["detail"].lower()
    )

    # 3. Verificar que solo la variante ganadora descontó stock y la perdedora quedó INTACTA
    datos_201 = resp_201.json()
    async with fabrica_sesiones() as db:
        inv_a_fin = (await db.execute(
            select(InventarioSucursal).where(
                InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                InventarioSucursal.variante_id == escenario.variante_a_id,
            )
        )).scalars().first()

        inv_ultima_fin = (await db.execute(
            select(InventarioSucursal).where(
                InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                InventarioSucursal.variante_id == escenario.variante_ultima_id,
            )
        )).scalars().first()

        detalles = (await db.execute(
            select(DetalleVenta).where(DetalleVenta.venta_id == uuid.UUID(datos_201["venta_id"]))
        )).scalars().all()
        assert len(detalles) == 1
        variante_ganadora_id = detalles[0].variante_id

        if variante_ganadora_id == escenario.variante_a_id:
            # Ganó A: variante A se descontó en 1; variante última quedó intacta
            assert inv_a_fin.disponible == stock_a_inicial - 1
            assert inv_ultima_fin.disponible == stock_ultima_inicial
        else:
            # Ganó última: variante última se descontó en 1; variante A quedó intacta
            assert inv_ultima_fin.disponible == stock_ultima_inicial - 1
            assert inv_a_fin.disponible == stock_a_inicial

        # Comprobar que en la plataforma existe exactamente 1 pago registrado para pi_ref
        pagos = (
            await db.execute(
                select(Pago).where(Pago.referencia_externa == pi_ref)
            )
        ).scalars().all()
        assert len(pagos) == 1


@pytest.mark.asyncio
async def test_contraejemplo_c1_intento_usar_cargo_venta_a_para_liquidar_venta_b_falla_409(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo C1.7: Intentar usar el PaymentIntent de una Venta A para liquidar una Venta B
    debe ser RECHAZADO con 409 Conflict, demostrando que la orden no se reasigna."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    http.usar(escenario.usuario_admin_a)

    # 1. Iniciar Venta A con Stripe
    resp_a = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
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
    assert resp_a.status_code == 201, resp_a.text
    data_a = resp_a.json()
    venta_a_id = uuid.UUID(data_a["venta_id"])
    pi_ref_a = data_a["stripe_payment_intent_id"]
    orden_a_id = uuid.UUID(data_a["orden_pago_id"])

    # Capturar orden A en pasarela y DB
    fake.intenciones[pi_ref_a] = IntencionPago(
        id=pi_ref_a,
        venta_id=str(venta_a_id),
        monto_centavos=data_a["centavos_usd"],
        moneda="usd",
        estado="SUCCEEDED",
    )
    fake.intenciones[pi_ref_a].cliente_id = str(escenario.usuario_a.id)

    async with fabrica_sesiones() as db:
        ord_db = await db.get(OrdenPago, orden_a_id)
        ord_db.estado = "CAPTURADO"
        await db.commit()

    # 2. Iniciar Venta B con Stripe
    resp_b = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
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
    assert resp_b.status_code == 201, resp_b.text
    data_b = resp_b.json()
    venta_b_id = uuid.UUID(data_b["venta_id"])

    # 3. Intentar liquidar Venta B enviando el cargo de Venta A
    resp_ataque = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "venta_id": str(venta_b_id),
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
            "stripe_payment_intent_id": pi_ref_a,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_ataque.status_code == 409, resp_ataque.text
    assert "otra venta" in resp_ataque.json()["detail"].lower()

    # 4. Verificar en base de datos que la orden A NUNCA fue reasignada a Venta B
    async with fabrica_sesiones() as db:
        ord_chk = await db.get(OrdenPago, orden_a_id)
        assert ord_chk.venta_id == venta_a_id
        assert ord_chk.venta_id != venta_b_id

        # Venta B debe permanecer en PENDIENTE_PAGO
        v_b_chk = await db.get(Venta, venta_b_id)
        assert v_b_chk.estado == "PENDIENTE_PAGO"


@pytest.mark.asyncio
async def test_contraejemplo_c1_reintento_iniciar_stripe_recupera_client_secret_real_y_tasa_congelada(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo C1.8: En reintento de /iniciar-stripe, se debe recuperar el client_secret real consultando la pasarela y la tasa congelada real."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    http.usar(escenario.usuario_admin_a)

    clave_idempotencia = uuid.uuid4()
    body = {
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
    }

    resp1 = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json=body,
        headers={"Idempotency-Key": str(clave_idempotencia)},
    )
    assert resp1.status_code == 201, resp1.text
    data1 = resp1.json()
    pi_ref = data1["stripe_payment_intent_id"]

    # Simulamos que la pasarela tiene un client_secret real y específico
    secret_real = f"{pi_ref}_secret_real_gateway_abc"
    fake.intenciones[pi_ref].client_secret = secret_real

    # Reintento con la misma clave de idempotencia
    resp2 = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json=body,
        headers={"Idempotency-Key": str(clave_idempotencia)},
    )
    assert resp2.status_code == 200 or resp2.status_code == 201, resp2.text
    data2 = resp2.json()

    assert data2["client_secret"] == secret_real
    assert data2["tasa_bob_por_usd"] == data1["tasa_bob_por_usd"]


@pytest.mark.asyncio
async def test_contraejemplo_c1_caja_turno_cupo_1_stock_libre_0_no_falla_y_consume_cupo(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo C1.9: Caja con turno_caja_id y cupo=1 pero stock libre=0 no debe fallar 409 y debe consumir el cupo."""
    http.usar(escenario.usuario_admin_a)
    ahora = datetime.now(timezone.utc)

    # 1. Crear turno de caja abierto y cupo de 1 unidad para la variante
    turno_id = uuid.uuid4()
    cupo_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        turno = TurnoCaja(
            id=turno_id,
            empresa_id=escenario.empresa_a_id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            dispositivo_id=uuid.uuid4(),
            caja_codigo="CAJA-P0-01",
            estado="ABIERTO",
            inicio_en=ahora,
            vence_en=ahora + timedelta(hours=8),
            version_precios="v1",
            cupos_hash="cupo_hash_p0",
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

        # Simular que el stock libre es 0 porque fue comprometido a la caja al abrir el turno
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv = (await db.execute(stmt_inv)).scalars().first()
        inv.disponible = 0
        inv.comprometido_caja = 1
        await db.commit()

    # 2. Liquidar venta presencial con efectivo pasando turno_caja_id
    clave_liq = uuid.uuid4()
    resp_liq = await http.cliente.post(
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
        headers={"Idempotency-Key": str(clave_liq)},
    )
    assert resp_liq.status_code == 201, resp_liq.text
    liq_data = resp_liq.json()
    assert liq_data["estado_pago"] == "PAGADA"

    # 3. Verificar que consumió el cupo, redujo comprometido_caja y disponible permanece en 0 (sin negativos)
    async with fabrica_sesiones() as db:
        cupo_db = await db.get(CupoCaja, cupo_id)
        assert cupo_db.consumido == 1

        inv_db = (await db.execute(stmt_inv)).scalars().first()
        assert inv_db.disponible == 0
        assert inv_db.comprometido_caja == 0



# ============================================================================
# C4: CU20 Y CU08 POSVENTA (DEVOLUCIONES Y CAMBIOS)
# ============================================================================

@pytest.mark.asyncio
async def test_contraejemplo_c4_devolucion_fuera_de_plazo_voluntaria_vs_defecto(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo C4.1: Devolución voluntaria fuera de 15 días falla 400; reclamo por defecto entra a PENDIENTE_EVALUACION."""
    # Venta entregada hace 25 días calendario
    venta_id, det_id = await _crear_venta_para_posventa(
        escenario, fabrica_sesiones, cantidad=2, entregada=True, dias_antiguedad=25
    )

    http.usar(escenario.usuario_a)

    # 1. Devolución voluntaria (TALLA) fuera de plazo debe ser rechazada con 400
    resp_vol = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "motivo_codigo": "TALLA",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_vol.status_code == 400, resp_vol.text
    assert "ha vencido" in resp_vol.json()["detail"].lower()

    # 2. Devolución por defecto de fábrica no se rechaza automáticamente; pasa a PENDIENTE_EVALUACION
    resp_def = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "motivo_codigo": "DEFECTO_FABRICACION",
            "motivo_descripcion": "Costura desprendida en prenda de fábrica",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_def.status_code == 201, resp_def.text
    dev = resp_def.json()
    assert dev["estado"] == "PENDIENTE_EVALUACION"


@pytest.mark.asyncio
async def test_contraejemplo_c4_cambio_resolucion_simultanea_saldo_y_reembolso_falla_400(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo C4.2: Intentar resolver diferencia con saldo y reembolso simultáneos o ambiguos falla con 400."""
    venta_id, det_id = await _crear_venta_para_posventa(escenario, fabrica_sesiones, cantidad=1)

    http.usar(escenario.usuario_a)
    resp_sol = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "TALLA",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_sol.status_code == 201, resp_sol.text
    cambio_id = resp_sol.json()["cambio_id"]

    # 1. Enviar destino ambiguo o combinado "SALDO_Y_REEMBOLSO"
    resp_comb = await http.cliente.post(
        f"/api/v1/cambios/{cambio_id}/resolver-diferencia",
        json={"destino_diferencia": "SALDO_Y_REEMBOLSO"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_comb.status_code == 400, resp_comb.text
    assert "prohibida" in resp_comb.json()["detail"].lower() or "exclusivamente" in resp_comb.json()["detail"].lower()

    # 2. Enviar montos simultáneos a saldo y reembolso
    resp_split = await http.cliente.post(
        f"/api/v1/cambios/{cambio_id}/resolver-diferencia",
        json={"destino_diferencia": "SALDO", "saldo_bob": 50.0, "reembolso_bob": 50.0},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_split.status_code == 400, resp_split.text
    assert "simultánea" in resp_split.json()["detail"].lower() or "prohibida" in resp_split.json()["detail"].lower()

    # 3. Verificar que el cambio NO quedó en estado RESUELTO y no hay saldo ni reembolso creados
    async with fabrica_sesiones() as db:
        cambio = await db.get(Cambio, uuid.UUID(cambio_id))
        assert cambio.estado == "SOLICITADO"

        stmt_s = select(MovimientoSaldo).where(
            MovimientoSaldo.origen_tipo == "CAMBIO",
            MovimientoSaldo.origen_id == uuid.UUID(cambio_id),
        )
        assert (await db.execute(stmt_s)).scalars().first() is None

        stmt_r = select(ObligacionReembolso).where(
            ObligacionReembolso.origen_tipo == "CAMBIO",
            ObligacionReembolso.origen_id == uuid.UUID(cambio_id),
        )
        assert (await db.execute(stmt_r)).scalars().first() is None


# ============================================================================
# CONTRAEJEMPLOS AUDITORÍA 33 — SUBAGENTE A: INVENTARIO, CAJA Y LIQUIDACIÓN
# ============================================================================

@pytest.mark.asyncio
async def test_contraejemplo_c1_iniciar_stripe_libre_cero_cupo_uno_falla_409(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo 1 (Auditoría 33): iniciar_stripe con libre 0 y cupo 1 debe fallar 409 antes de crear PaymentIntent.

    Demuestra el defecto donde el backend anterior tomaba cupo de caja y creaba PaymentIntent.
    Debe fallar con HTTP 409 Conflict ("Stock libre insuficiente para venta conectada Stripe").
    """
    fake = FakeStripeGateway()
    fijar_gateway(fake)
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
            caja_codigo="CAJA-P0-AUD33-01",
            estado="ABIERTO",
            inicio_en=ahora,
            vence_en=ahora + timedelta(hours=8),
            version_precios="v1",
            cupos_hash="cupo_hash_aud33_01",
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
        # Libre 0, cupo 1
        inv.disponible = 0
        inv.comprometido_caja = 1
        await db.commit()

    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "turno_caja_id": str(turno_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                    "descuento_bob": 0.0,
                }
            ],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    # Debe ser rechazado con HTTP 409 Conflict
    assert resp.status_code == 409, f"Esperado 409 pero respondió {resp.status_code}: {resp.text}"
    assert "stock libre insuficiente para venta conectada stripe" in resp.json()["detail"].lower()

    # Comprobar que NO se creó ningún PaymentIntent ni Venta ni OrdenPago
    assert len(fake.intenciones) == 0
    async with fabrica_sesiones() as db:
        stmt_v = select(Venta).where(
            Venta.sucursal_id == escenario.sucursal_a_id,
            Venta.turno_caja_id == turno_id,
        )
        assert (await db.execute(stmt_v)).scalars().first() is None


@pytest.mark.asyncio
async def test_contraejemplo_c1_dos_ventas_stripe_concurrentes_compitiendo_por_una_unidad_libre(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo 2 (Auditoría 33): Dos ventas Stripe concurrentes compitiendo por 1 sola unidad libre.

    La comprobación o bloqueo atómico evita emitir dos PaymentIntent sobre la misma unidad:
    una sola debe poder iniciar (201); la segunda debe ser rechazada con HTTP 409.
    """
    import asyncio
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    http.usar(escenario.usuario_admin_a)

    async with fabrica_sesiones() as db:
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv = (await db.execute(stmt_inv)).scalars().first()
        inv.disponible = 1
        inv.comprometido_caja = 0
        await db.commit()

    async def _iniciar(clave_id):
        return await http.cliente.post(
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
            headers={"Idempotency-Key": str(clave_id)},
        )

    # Dos intentos concurrentes por la misma unidad libre
    res1, res2 = await asyncio.gather(_iniciar(uuid.uuid4()), _iniciar(uuid.uuid4()))
    codigos = [res1.status_code, res2.status_code]

    assert 201 in codigos, f"Una venta debe poder iniciar; respuestas: {codigos}"
    assert 409 in codigos, f"La venta competidora debe ser rechazada con 409; respuestas: {codigos}"


@pytest.mark.asyncio
async def test_contraejemplo_c1_libre_uno_cupo_uno_stripe_consume_libre_y_mantiene_cupo(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo 3 (Auditoría 33): Libre 1 y cupo 1: venta Stripe conectada consume de libre (dejando libre 0) y deja cupo intacto.

    Demuestra el defecto donde liquidar hacía `comprometido_caja = max(0, comprometido_caja - cant)`.
    """
    fake = FakeStripeGateway()
    fijar_gateway(fake)
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
            caja_codigo="CAJA-P0-AUD33-03",
            estado="ABIERTO",
            inicio_en=ahora,
            vence_en=ahora + timedelta(hours=8),
            version_precios="v1",
            cupos_hash="cupo_hash_aud33_03",
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
        # Libre 1, cupo 1
        inv.disponible = 1
        inv.comprometido_caja = 1
        await db.commit()

    # Iniciar Stripe con turno_caja_id
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "turno_caja_id": str(turno_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                    "descuento_bob": 0.0,
                }
            ],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201, resp_init.text
    init_data = resp_init.json()
    venta_id = uuid.UUID(init_data["venta_id"])
    orden_pago_id = uuid.UUID(init_data["orden_pago_id"])
    pi_ref = init_data["stripe_payment_intent_id"]

    # Simular captura y confirmar
    fake.intenciones[pi_ref].estado = "SUCCEEDED"
    fake.intenciones[pi_ref].cliente_id = str(escenario.usuario_a.id)

    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_conf.status_code == 200, resp_conf.text
    assert resp_conf.json()["estado"] == "CAPTURADO"

    # Liquidar Stripe
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
            "turno_caja_id": str(turno_id),
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_liq.status_code == 201, resp_liq.text

    # Verificación en BD:
    # 1. disponible debe haber bajado de 1 a 0 (Stripe consumió stock libre)
    # 2. comprometido_caja debe SEGUIR EN 1 (cupo de caja offline NO fue tocado)
    # 3. cupo.consumido debe SEGUIR EN 0
    async with fabrica_sesiones() as db:
        inv_db = (await db.execute(stmt_inv)).scalars().first()
        cupo_db = await db.get(CupoCaja, cupo_id)

        assert inv_db.disponible == 0, f"Stock libre disponible debió ser 0 pero quedó en {inv_db.disponible}"
        assert inv_db.comprometido_caja == 1, f"comprometido_caja debió permanecer en 1 pero quedó en {inv_db.comprometido_caja}"
        assert cupo_db.consumido == 0, f"cupo.consumido debió permanecer en 0 pero quedó en {cupo_db.consumido}"


@pytest.mark.asyncio
async def test_contraejemplo_c1_captura_seguida_de_fallo_liquidacion_conserva_venta_y_permite_reintento(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo 6 (Auditoría 33): Captura seguida de fallo de liquidación.

    La venta permanece en PENDIENTE_PAGO con su orden CAPTURADO, sin borrarse ni perderse,
    permitiendo reintento de liquidación exitoso.
    """
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    http.usar(escenario.usuario_admin_a)

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
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201
    init_data = resp_init.json()
    venta_id = uuid.UUID(init_data["venta_id"])
    orden_pago_id = uuid.UUID(init_data["orden_pago_id"])
    pi_ref = init_data["stripe_payment_intent_id"]

    # Simular captura y confirmar
    fake.intenciones[pi_ref].estado = "SUCCEEDED"
    fake.intenciones[pi_ref].cliente_id = str(escenario.usuario_a.id)

    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_pago_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_conf.status_code == 200
    assert resp_conf.json()["estado"] == "CAPTURADO"

    # 1. Intento de liquidación fallido (ej. precio adulterado a 50 BOB)
    resp_fallo = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "venta_id": str(venta_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 50.0,
                }
            ],
            "medio_pago": "STRIPE_TEST",
            "orden_pago_id": str(orden_pago_id),
            "stripe_payment_intent_id": pi_ref,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_fallo.status_code == 400

    # 2. Verificar que la Venta NO se borró y sigue en PENDIENTE_PAGO con Orden CAPTURADO
    async with fabrica_sesiones() as db:
        v_db = await db.get(Venta, venta_id)
        assert v_db is not None
        assert v_db.estado == "PENDIENTE_PAGO"

        o_db = await db.get(OrdenPago, orden_pago_id)
        assert o_db is not None
        assert o_db.estado == "CAPTURADO"

    # 3. Reintento de liquidación con datos correctos tiene éxito
    resp_ok = await http.cliente.post(
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
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_ok.status_code == 201, resp_ok.text
    assert resp_ok.json()["estado_pago"] == "PAGADA"

    async with fabrica_sesiones() as db:
        v_final = await db.get(Venta, venta_id)
        assert v_final.estado == "PAGADA"


@pytest.mark.asyncio
async def test_intercalacion_stripe_efectivo_compromiso_stock(
    http, escenario, fabrica_sesiones
):
    """Contraejemplo P0 (1): Intercalación Stripe y Efectivo con 1 unidad libre.

    Demuestra la vulnerabilidad P0:
    - Con 1 unidad libre en inventario:
      - Venta A inicia Stripe (/iniciar-stripe) -> debe comprometer durablemente la unidad libre
        (disponible 1 -> 0, comprometido_digital 0 -> 1, Kardex COMPROMISO_DIGITAL).
      - Venta B intenta liquidar en efectivo la misma variante -> debe ser rechazada con HTTP 409
        porque no hay disponible libre. En el código defectuoso se aceptaba y consumía disponible a 0.
      - Venta A confirma captura en pasarela y liquida con STRIPE_TEST -> debe tener éxito (HTTP 201)
        consumiendo el compromiso digital (comprometido_digital 1 -> 0), sin fallar por falta de stock.
    """
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    http.usar(escenario.usuario_admin_a)

    # 1. Asegurar inventario exacto: 1 unidad libre, 0 en caja, 0 digital
    stmt_inv = select(InventarioSucursal).where(
        InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
        InventarioSucursal.variante_id == escenario.variante_a_id,
    )
    async with fabrica_sesiones() as db:
        inv = (await db.execute(stmt_inv)).scalars().first()
        inv.disponible = 1
        inv.comprometido_caja = 0
        inv.comprometido_digital = 0
        await db.commit()

    # 2. Iniciar Stripe Venta A por 1 unidad
    clave_a = uuid.uuid4()
    resp_init_a = await http.cliente.post(
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
        headers={"Idempotency-Key": str(clave_a)},
    )
    assert resp_init_a.status_code == 201, resp_init_a.text
    data_a = resp_init_a.json()
    venta_a_id = uuid.UUID(data_a["venta_id"])
    orden_a_id = uuid.UUID(data_a["orden_pago_id"])
    pi_ref_a = data_a["stripe_payment_intent_id"]

    # Verificar compromiso durable inmediato en base de datos:
    # disponible debió pasar de 1 a 0, y comprometido_digital debió pasar de 0 a 1
    async with fabrica_sesiones() as db:
        inv_post_init = (await db.execute(stmt_inv)).scalars().first()
        assert inv_post_init.disponible == 0, (
            f"El stock disponible debió bajar a 0 tras iniciar Stripe, pero sigue en {inv_post_init.disponible}"
        )
        assert inv_post_init.comprometido_digital == 1, (
            f"El comprometido_digital debió subir a 1 tras iniciar Stripe, pero está en {inv_post_init.comprometido_digital}"
        )

        # Verificar movimiento Kardex COMPROMISO_DIGITAL
        stmt_k = select(MovimientoInventario).where(
            MovimientoInventario.referencia_id == venta_a_id,
            MovimientoInventario.tipo == "COMPROMISO_DIGITAL",
        )
        mov_comp = (await db.execute(stmt_k)).scalars().first()
        assert mov_comp is not None, "Debe existir movimiento Kardex COMPROMISO_DIGITAL para la venta iniciada"
        assert mov_comp.cantidad == 1

        # Verificar expira_en asignado
        v_db = await db.get(Venta, venta_a_id)
        assert v_db.expira_en is not None, "Venta debe tener expira_en asignado"

    # 3. Venta B intenta liquidar en efectivo la misma variante
    resp_b = await http.cliente.post(
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
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    # Debe ser RECHAZADO con 409 Conflict porque la única unidad está comprometida con Stripe A
    assert resp_b.status_code == 409, (
        f"Venta B debió fallar con 409 por stock insuficiente, pero respondió {resp_b.status_code}: {resp_b.text}"
    )

    # 4. Simular captura en pasarela de Venta A y confirmar
    fake.intenciones[pi_ref_a].estado = "SUCCEEDED"
    fake.intenciones[pi_ref_a].cliente_id = str(escenario.usuario_a.id)

    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_a_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_conf.status_code == 200, resp_conf.text
    assert resp_conf.json()["estado"] == "CAPTURADO"

    # 5. Liquidar Venta A con STRIPE_TEST
    resp_liq_a = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "venta_id": str(venta_a_id),
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
            "orden_pago_id": str(orden_a_id),
            "stripe_payment_intent_id": pi_ref_a,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    # Debe liquidar con éxito 201 consumiendo el compromiso
    assert resp_liq_a.status_code == 201, (
        f"Venta A debió liquidar exitosamente pero respondió {resp_liq_a.status_code}: {resp_liq_a.text}"
    )

    # 6. Verificación final de integridad en BD
    async with fabrica_sesiones() as db:
        inv_final = (await db.execute(stmt_inv)).scalars().first()
        assert inv_final.disponible == 0
        assert inv_final.comprometido_digital == 0, (
            f"comprometido_digital debió quedar en 0 tras liquidar, pero quedó en {inv_final.comprometido_digital}"
        )
        assert inv_final.comprometido_caja == 0

        # Kardex VENTA_PRESENCIAL registrado
        stmt_kv = select(MovimientoInventario).where(
            MovimientoInventario.referencia_id == venta_a_id,
            MovimientoInventario.tipo == "VENTA_PRESENCIAL",
        )
        assert (await db.execute(stmt_kv)).scalars().first() is not None
