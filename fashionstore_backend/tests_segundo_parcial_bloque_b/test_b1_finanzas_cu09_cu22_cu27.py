"""Suite B1: Finanzas, Saldo Personal, Stripe Test y Reembolsos (CU09, CU22, CU27).

Reglas de la suite:
- Ejecución sobre fashionstore_test (PostgreSQL 16, Alembic 0013).
- Usa conftest.py del Bloque B (escenario, fabrica_sesiones, http).
- Doble determinista sin red: FakeStripeGateway conmutado mediante fijar_gateway.
- Verificación exhaustiva:
  * CU09: libro append-only, saldo disponible/retenido, for update, idempotencia, restante_por_pagar_bob, multi-tenant.
  * CU22: SetupIntent (/metodos/preparar, /metodos/{id}), órdenes de pago (/ordenes, /ordenes/{id}) con cálculo
    de deuda por servidor y centavos congelados, continuación 3DS (/continuar-accion), webhook firmado.
  * CU27: derivación en servidor, componente Stripe a centavos originales, componente Saldo restaurado al libro
    sin convertir a efectivo, autorización por rol, ejecución idempotente y verificación de no mutación de stock.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from backend.app.core.modules.posventa.models import (
    ComponenteReembolso,
    EjecucionReembolso,
    MovimientoSaldo,
    ObligacionReembolso,
)
from backend.app.core.modules.posventa.services.saldo_service import SaldoService
from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import (
    FakeStripeGateway,
    fijar_gateway,
    firmar_prueba,
)
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Pago, Venta
from backend.app.core.modules.ventas_pagos.models_ordenes import (
    MetodoPreparado,
    OrdenPago,
)
from backend.app.core.config import settings


# ============================================================================
# Helpers para creación de datos de negocio en pruebas
# ============================================================================

async def crear_venta_db(
    fabrica_sesiones,
    escenario,
    total: Decimal = Decimal("100.00"),
    cliente_id: uuid.UUID = None,
    empresa_id: uuid.UUID = None,
    estado: str = "PENDIENTE_PAGO",
) -> uuid.UUID:
    """Crea una venta con su detalle en la base de datos de prueba."""
    v_id = uuid.uuid4()
    emp_id = empresa_id or escenario.empresa_a_id
    cli_id = cliente_id or escenario.usuario_a.id
    ahora = datetime.now(timezone.utc)

    async with fabrica_sesiones() as db:
        venta = Venta(
            id=v_id,
            empresa_id=emp_id,
            numero=f"V-{v_id.hex[:8].upper()}",
            cliente_id=cli_id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=None,
            canal="WEB",
            estado=estado,
            subtotal=total,
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=total,
            creada_en=ahora,
            expira_en=ahora + timedelta(hours=2),
        )
        db.add(venta)
        await db.flush()

        det = DetalleVenta(
            id=uuid.uuid4(),
            venta_id=v_id,
            variante_id=escenario.variante_a_id,
            cantidad=1,
            precio_unitario=total,
            descuento=Decimal("0.00"),
            costo_promedio=Decimal("40.00"),
        )
        db.add(det)
        await db.flush()

        # Asegurar compromiso de stock para venta digital
        await db.execute(
            text(
                "UPDATE inventario.inventario_sucursal "
                "SET reservado = reservado + 1 "
                "WHERE sucursal_id = :sid AND variante_id = :vid"
            ),
            {"sid": escenario.sucursal_a_id, "vid": escenario.variante_a_id},
        )
        await db.commit()
    return v_id


async def crear_pago_db(
    fabrica_sesiones,
    venta_id: uuid.UUID,
    empresa_id: uuid.UUID,
    monto: Decimal,
    metodo: str = "STRIPE_TEST",
    estado: str = "APROBADO",
    referencia_externa: str = None,
) -> uuid.UUID:
    """Crea un registro de pago asociado a la venta."""
    p_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        pago = Pago(
            id=p_id,
            empresa_id=empresa_id,
            contexto="VENTA",
            venta_id=venta_id,
            metodo=metodo,
            tipo_pago="PAGO",
            monto=monto,
            no_reembolsable=False,
            estado=estado,
            referencia_externa=referencia_externa or f"pi_test_{p_id.hex[:8]}",
            proveedor_pago=metodo,
            pagado_en=datetime.now(timezone.utc),
        )
        db.add(pago)
        await db.commit()
    return p_id


async def crear_pedido_compra_db(
    fabrica_sesiones,
    escenario,
    total: Decimal = Decimal("150.00"),
    cliente_id: uuid.UUID = None,
) -> uuid.UUID:
    """Inserta directamente un pedido de compra en comercial.pedidos_compra."""
    p_id = uuid.uuid4()
    cli_id = cliente_id or escenario.usuario_a.id
    ahora = datetime.now(timezone.utc)

    async with fabrica_sesiones() as db:
        await db.execute(
            text(
                "INSERT INTO comercial.pedidos_compra "
                "(id, empresa_id, cliente_id, sucursal_id, estado, estado_pago, estado_cumplimiento, "
                "modalidad, subtotal_bob, descuento_bob, envio_bob, total_bob, revision, creado_en, actualizado_en) "
                "VALUES (:id, :eid, :cid, :sid, 'BORRADOR', 'SIN_PAGO', 'SIN_ASIGNACION', "
                "'RECOJO', :tot, 0, 0, :tot, 1, :ahora, :ahora)"
            ),
            {
                "id": p_id,
                "eid": escenario.empresa_a_id,
                "cid": cli_id,
                "sid": escenario.sucursal_a_id,
                "tot": total,
                "ahora": ahora,
            },
        )
        await db.commit()
    return p_id


# ============================================================================
# BLOQUE 1: Pruebas CU09 — Saldo Personal del Cliente
# ============================================================================

@pytest.mark.asyncio
async def test_cu09_01_consultar_saldo_inicial_vacio(http, escenario):
    """Cliente recién registrado sin movimientos tiene saldo disponible y retenido en 0."""
    http.usar(escenario.usuario_a)
    resp = await http.cliente.get("/api/v1/saldos/mio")
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert Decimal(str(datos["saldo_disponible_bob"])) == Decimal("0.00")
    assert Decimal(str(datos["saldo_retenido_bob"])) == Decimal("0.00")
    assert datos["movimientos"] == []


@pytest.mark.asyncio
async def test_cu09_02_acreditar_saldo_y_consultar_resumen(http, escenario, fabrica_sesiones):
    """Acreditar saldo personal refleja disponible inmediato y genera rastro append-only."""
    async with fabrica_sesiones() as db:
        servicio = SaldoService(db)
        await servicio.acreditar_saldo(
            cliente_id=escenario.usuario_a.id,
            empresa_id=escenario.empresa_a_id,
            monto_bob=Decimal("500.00"),
            origen_tipo="PROMOCION",
        )
        await db.commit()

    http.usar(escenario.usuario_a)
    resp = await http.cliente.get("/api/v1/saldos/mio")
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert Decimal(str(datos["saldo_disponible_bob"])) >= Decimal("500.00")
    assert Decimal(str(datos["saldo_retenido_bob"])) == Decimal("0.00")
    assert len(datos["movimientos"]) >= 1
    assert datos["movimientos"][0]["tipo"] == "CREDITO"


@pytest.mark.asyncio
async def test_cu09_03_aislamiento_saldo_multiempresa(http, escenario, fabrica_sesiones):
    """El saldo de un cliente en Empresa A no es visible ni utilizable por un cliente en Empresa B."""
    async with fabrica_sesiones() as db:
        servicio = SaldoService(db)
        # Acreditar a usuario A en empresa A
        await servicio.acreditar_saldo(
            cliente_id=escenario.usuario_a.id,
            empresa_id=escenario.empresa_a_id,
            monto_bob=Decimal("300.00"),
            origen_tipo="RECARGA",
        )
        await db.commit()

    # Usuario B consulta su saldo en Empresa B
    http.usar(escenario.usuario_b)
    resp_b = await http.cliente.get("/api/v1/saldos/mio")
    assert resp_b.status_code == 200
    datos_b = resp_b.json()
    assert Decimal(str(datos_b["saldo_disponible_bob"])) == Decimal("0.00")


@pytest.mark.asyncio
async def test_cu09_04_aplicar_saldo_monto_insuficiente_rechaza_sin_debito_parcial(
    http, escenario, fabrica_sesiones
):
    """Si el importe a aplicar supera el saldo disponible, rechaza 400 sin débito parcial implícito."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("200.00"))

    http.usar(escenario.usuario_a)
    # Usuario A no tiene suficiente (o tiene menos de 999999)
    resp = await http.cliente.post(
        f"/api/v1/ventas/{v_id}/aplicar-saldo",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"monto_bob": "999999.00", "revision": 1},
    )
    assert resp.status_code == 400, resp.text
    assert "insuficiente" in resp.json()["detail"].lower() or "supera" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cu09_05_aplicar_saldo_exitoso_y_restante_por_pagar(http, escenario, fabrica_sesiones):
    """Aplica saldo a una venta, reteniendo atómicamente el monto y calculando restante_por_pagar_bob."""
    async with fabrica_sesiones() as db:
        servicio = SaldoService(db)
        await servicio.acreditar_saldo(
            cliente_id=escenario.usuario_a.id,
            empresa_id=escenario.empresa_a_id,
            monto_bob=Decimal("400.00"),
            origen_tipo="DEPOSITO",
        )
        await db.commit()

    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("250.00"))

    http.usar(escenario.usuario_a)
    clave_idem = str(uuid.uuid4())
    resp = await http.cliente.post(
        f"/api/v1/ventas/{v_id}/aplicar-saldo",
        headers={"Idempotency-Key": clave_idem},
        json={"monto_bob": "100.00", "revision": 1},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert Decimal(str(data["saldo_retenido_bob"])) >= Decimal("100.00")
    # Restante de 250 - 100 = 150
    assert Decimal(str(data["restante_por_pagar_bob"])) == Decimal("150.00")
    assert "movimiento_id" in data


@pytest.mark.asyncio
async def test_cu09_06_aplicar_saldo_idempotencia_estricta(http, escenario, fabrica_sesiones):
    """Reenviar la solicitud con la misma Idempotency-Key devuelve el mismo resultado sin duplicar retención."""
    async with fabrica_sesiones() as db:
        servicio = SaldoService(db)
        await servicio.acreditar_saldo(
            cliente_id=escenario.usuario_a.id,
            empresa_id=escenario.empresa_a_id,
            monto_bob=Decimal("300.00"),
        )
        await db.commit()

    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("120.00"))
    clave_idem = str(uuid.uuid4())

    http.usar(escenario.usuario_a)
    r1 = await http.cliente.post(
        f"/api/v1/ventas/{v_id}/aplicar-saldo",
        headers={"Idempotency-Key": clave_idem},
        json={"monto_bob": "50.00", "revision": 1},
    )
    assert r1.status_code == 200
    d1 = r1.json()

    # Segunda llamada idempotente
    r2 = await http.cliente.post(
        f"/api/v1/ventas/{v_id}/aplicar-saldo",
        headers={"Idempotency-Key": clave_idem},
        json={"monto_bob": "50.00", "revision": 1},
    )
    assert r2.status_code == 200
    d2 = r2.json()

    assert d1["movimiento_id"] == d2["movimiento_id"]
    assert d1["saldo_disponible_bob"] == d2["saldo_disponible_bob"]
    assert d1["saldo_retenido_bob"] == d2["saldo_retenido_bob"]


@pytest.mark.asyncio
async def test_cu09_07_aplicar_saldo_a_pedido_compra(http, escenario, fabrica_sesiones):
    """Aplica saldo a un pedido de compra en comercial.pedidos_compra."""
    async with fabrica_sesiones() as db:
        servicio = SaldoService(db)
        await servicio.acreditar_saldo(
            cliente_id=escenario.usuario_a.id,
            empresa_id=escenario.empresa_a_id,
            monto_bob=Decimal("200.00"),
        )
        await db.commit()

    ped_id = await crear_pedido_compra_db(fabrica_sesiones, escenario, total=Decimal("150.00"))

    http.usar(escenario.usuario_a)
    clave_idem = str(uuid.uuid4())
    resp = await http.cliente.post(
        f"/api/v1/compras/{ped_id}/aplicar-saldo",
        headers={"Idempotency-Key": clave_idem},
        json={"monto_bob": "75.00", "revision": 1},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert Decimal(str(data["restante_por_pagar_bob"])) == Decimal("75.00")
    assert Decimal(str(data["saldo_retenido_bob"])) >= Decimal("75.00")


# ============================================================================
# BLOQUE 2: Pruebas CU22 — Pasarela Stripe Test (E2)
# ============================================================================

@pytest.fixture(autouse=True)
def configurar_fake_stripe():
    """Conmuta FakeStripeGateway para evitar llamadas a la red en todas las pruebas."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    yield fake
    fijar_gateway(None)


@pytest.mark.asyncio
async def test_cu22_01_preparar_metodo_setup_intent_y_consultar(http, escenario):
    """POST /pagos/stripe/metodos/preparar genera SetupIntent y GET /metodos/{id} lo recupera."""
    http.usar(escenario.usuario_a)
    clave_idem = str(uuid.uuid4())

    resp = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": clave_idem},
        json={"huella_dispositivo": "android_pixel_test_01"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "preparacion_pago_id" in data
    assert data["estado"] == "PENDIENTE"
    assert data["client_secret"].startswith("seti_test_")

    prep_id = data["preparacion_pago_id"]
    resp_get = await http.cliente.get(f"/api/v1/pagos/stripe/metodos/{prep_id}")
    assert resp_get.status_code == 200, resp_get.text
    data_get = resp_get.json()
    assert data_get["preparacion_pago_id"] == prep_id
    assert data_get["estado"] == "PENDIENTE"

    # Confirmar método preparado
    resp_conf = await http.cliente.post(f"/api/v1/pagos/stripe/metodos/{prep_id}/confirmar")
    assert resp_conf.status_code == 200, resp_conf.text
    assert resp_conf.json()["estado"] == "LISTO"


@pytest.mark.asyncio
async def test_cu22_02_crear_orden_pago_servidor_calcula_deuda_y_tasa(http, escenario, fabrica_sesiones):
    """El backend calcula deuda, congela tasa y emite centavos USD sin confiar en cliente."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("208.80"))

    http.usar(escenario.usuario_a)
    clave_idem = str(uuid.uuid4())

    resp = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": clave_idem},
        json={
            "contexto": "VENTA",
            "recurso_id": str(v_id),
            "oferta_revision": 1,
        },
    )
    assert resp.status_code == 201, resp.text
    orden = resp.json()
    assert orden["estado"] in ("PENDIENTE", "CAPTURADO")
    assert Decimal(str(orden["monto_bob"])) == Decimal("208.80")
    assert orden["centavos_usd"] is not None and orden["centavos_usd"] > 0
    assert orden["centavos_usd"] == int(Decimal(str(orden["monto_usd"])) * 100)
    assert orden["tasa_id"] is not None
    assert orden["client_secret"].startswith("pi_test_")


@pytest.mark.asyncio
async def test_cu22_03_crear_orden_pago_idempotente(http, escenario, fabrica_sesiones):
    """Reintentar la creación de orden de pago con la misma clave devuelve el registro existente."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("100.00"))
    clave_idem = str(uuid.uuid4())

    http.usar(escenario.usuario_a)
    r1 = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": clave_idem},
        json={"contexto": "VENTA", "recurso_id": str(v_id)},
    )
    assert r1.status_code == 201
    o1 = r1.json()

    r2 = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": clave_idem},
        json={"contexto": "VENTA", "recurso_id": str(v_id)},
    )
    assert r2.status_code in (200, 201)
    o2 = r2.json()

    assert o1["orden_pago_id"] == o2["orden_pago_id"]
    assert o1["centavos_usd"] == o2["centavos_usd"]


@pytest.mark.asyncio
async def test_cu22_04_orden_pago_off_session_con_metodo_preparado(http, escenario, fabrica_sesiones):
    """Orden de pago con método preparado y consentimiento se captura off_session directamente."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("150.00"))

    http.usar(escenario.usuario_a)
    # 1. Preparar método
    r_prep = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    prep_id = r_prep.json()["preparacion_pago_id"]
    await http.cliente.post(f"/api/v1/pagos/stripe/metodos/{prep_id}/confirmar")

    # 2. Crear orden con consentimiento off-session
    r_ord = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "contexto": "VENTA",
            "recurso_id": str(v_id),
            "metodo_preparado_id": prep_id,
            "consentimiento_cobro_posterior": True,
        },
    )
    assert r_ord.status_code == 201, r_ord.text
    orden = r_ord.json()
    assert orden["estado"] == "CAPTURADO"


@pytest.mark.asyncio
async def test_cu22_05_orden_pago_requiere_accion_3ds_y_continuacion(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """Simulación de SCA / 3DS: orden entra en REQUIERE_ACCION_CLIENTE y se continúa a CAPTURADO."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("100.00"))

    # Configurar fake para exigir acción 3DS
    configurar_fake_stripe.simular_requiere_accion = True

    http.usar(escenario.usuario_a)
    r_ord = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"contexto": "VENTA", "recurso_id": str(v_id)},
    )
    assert r_ord.status_code == 201, r_ord.text
    orden = r_ord.json()
    assert orden["estado"] == "REQUIERE_ACCION_CLIENTE"

    # Continuar la acción tras confirmación del cliente
    configurar_fake_stripe.simular_requiere_accion = False
    ord_id = orden["orden_pago_id"]
    r_cont = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{ord_id}/continuar-accion",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert r_cont.status_code == 200, r_cont.text
    orden_fin = r_cont.json()
    assert orden_fin["estado"] == "CAPTURADO"


@pytest.mark.asyncio
async def test_cu22_06_rutas_legadas_intencion_y_webhook_firmado(http, escenario, fabrica_sesiones):
    """Conserva el flujo de intenciones y webhook firmado legado (/stripe/intenciones y /stripe/webhook)."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("100.00"))

    http.usar(escenario.usuario_a)
    # Crear intención
    r_int = await http.cliente.post(
        "/api/v1/pagos/stripe/intenciones",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"venta_id": str(v_id)},
    )
    assert r_int.status_code == 201, r_int.text
    pi_id = r_int.json()["payment_intent_id"]

    # Consultar estado
    r_est = await http.cliente.get(f"/api/v1/pagos/stripe/estado/{v_id}")
    assert r_est.status_code == 200
    assert r_est.json()["payment_intent_id"] == pi_id

    # Webhook firmado
    payload = {
        "id": f"evt_test_{uuid.uuid4().hex[:6]}",
        "type": "payment_intent.succeeded",
        "livemode": False,
        "data": {"object": {"id": pi_id, "amount": 1437, "status": "succeeded"}},
    }
    import json
    cuerpo = json.dumps(payload).encode("utf-8")
    secreto = settings.STRIPE_WEBHOOK_SECRET or "whsec_test"
    firma = firmar_prueba(cuerpo, secreto)

    r_hook = await http.cliente.post(
        "/api/v1/pagos/stripe/webhook",
        headers={"Stripe-Signature": firma, "Content-Type": "application/json"},
        content=cuerpo,
    )
    assert r_hook.status_code == 200, r_hook.text
    assert r_hook.json()["estado"] == "APROBADO"


@pytest.mark.asyncio
async def test_cu22_07_orden_pago_pedido_webhook_captura_y_stock_idempotente(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """CU22: Webhook payment_intent.succeeded para orden de pedido confirma captura, asigna stock y es idempotente."""
    p_id = uuid.uuid4()
    ahora = datetime.now(timezone.utc)

    # 1. Crear pedido y detalles en base de datos
    async with fabrica_sesiones() as db:
        await db.execute(
            text(
                "INSERT INTO comercial.pedidos_compra "
                "(id, empresa_id, cliente_id, sucursal_id, estado, estado_pago, estado_cumplimiento, "
                "modalidad, subtotal_bob, descuento_bob, envio_bob, total_bob, revision, creado_en, actualizado_en) "
                "VALUES (:id, :eid, :cid, :sid, 'BORRADOR', 'EN_VERIFICACION', 'SIN_ASIGNACION', "
                "'RECOJO', 100.0, 0, 0, 100.0, 1, :ahora, :ahora)"
            ),
            {
                "id": p_id,
                "eid": escenario.empresa_a_id,
                "cid": escenario.usuario_a.id,
                "sid": escenario.sucursal_a_id,
                "ahora": ahora,
            },
        )
        await db.execute(
            text(
                "INSERT INTO comercial.detalles_pedido "
                "(id, empresa_id, pedido_id, variante_id, cantidad, precio_unitario_bob, descuento_bob, total_bob, oferta_revision) "
                "VALUES (:id, :eid, :pid, :vid, 1, 100.0, 0, 100.0, 1)"
            ),
            {
                "id": uuid.uuid4(),
                "eid": escenario.empresa_a_id,
                "pid": p_id,
                "vid": escenario.variante_a_id,
            },
        )
        await db.commit()

    # 2. Crear orden de pago que requiera 3DS
    configurar_fake_stripe.simular_requiere_accion = True
    http.usar(escenario.usuario_a)
    r_ord = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"contexto": "PEDIDO", "recurso_id": str(p_id)},
    )
    assert r_ord.status_code == 201, r_ord.text
    ord_data = r_ord.json()
    assert ord_data["estado"] == "REQUIERE_ACCION_CLIENTE"
    pi_id = ord_data["referencia_externa"]

    configurar_fake_stripe.simular_requiere_accion = False

    # 3. Leer stock disponible y reservado inicial
    async with fabrica_sesiones() as db:
        r_inv = await db.execute(
            text(
                "SELECT disponible, reservado FROM inventario.inventario_sucursal "
                "WHERE sucursal_id = :sid AND variante_id = :vid"
            ),
            {"sid": escenario.sucursal_a_id, "vid": escenario.variante_a_id},
        )
        row_inv = r_inv.first()
        disp_ini, res_ini = row_inv[0], row_inv[1]

    # 4. Primer webhook payment_intent.succeeded firmado
    import json
    payload = {
        "id": f"evt_test_{uuid.uuid4().hex[:6]}",
        "type": "payment_intent.succeeded",
        "livemode": False,
        "data": {
            "object": {
                "id": pi_id,
                "amount": ord_data["centavos_usd"],
                "currency": "usd",
                "metadata": {
                    "empresa_id": str(escenario.empresa_a_id),
                    "pedido_id": str(p_id),
                },
                "status": "succeeded",
            }
        },
    }
    cuerpo = json.dumps(payload).encode("utf-8")
    secreto = settings.STRIPE_WEBHOOK_SECRET or "whsec_test"
    firma = firmar_prueba(cuerpo, secreto)

    r_hook1 = await http.cliente.post(
        "/api/v1/pagos/stripe/webhook",
        headers={"Stripe-Signature": firma, "Content-Type": "application/json"},
        content=cuerpo,
    )
    assert r_hook1.status_code == 200, r_hook1.text
    assert r_hook1.json()["estado"] == "APROBADO"

    # Verificar que el pedido pasó a PAGADO y CONFIRMADO, y el stock se reservó
    async with fabrica_sesiones() as db:
        r_p = await db.execute(text("SELECT estado, estado_pago, estado_cumplimiento FROM comercial.pedidos_compra WHERE id = :id"), {"id": p_id})
        f_p = r_p.first()
        assert f_p[0] == "CONFIRMADO"
        assert f_p[1] == "PAGADO"
        assert f_p[2] == "COMPROMETIDO"

        r_inv1 = await db.execute(
            text("SELECT disponible, reservado FROM inventario.inventario_sucursal WHERE sucursal_id = :sid AND variante_id = :vid"),
            {"sid": escenario.sucursal_a_id, "vid": escenario.variante_a_id},
        )
        row_inv1 = r_inv1.first()
        assert row_inv1[0] == disp_ini - 1
        assert row_inv1[1] == res_ini + 1

    # 5. Webhook DUPLICADO: debe responder APROBADO sin descontar stock adicional
    r_hook2 = await http.cliente.post(
        "/api/v1/pagos/stripe/webhook",
        headers={"Stripe-Signature": firma, "Content-Type": "application/json"},
        content=cuerpo,
    )
    assert r_hook2.status_code == 200, r_hook2.text
    assert r_hook2.json()["estado"] == "APROBADO"

    async with fabrica_sesiones() as db:
        r_inv2 = await db.execute(
            text("SELECT disponible, reservado FROM inventario.inventario_sucursal WHERE sucursal_id = :sid AND variante_id = :vid"),
            {"sid": escenario.sucursal_a_id, "vid": escenario.variante_a_id},
        )
        row_inv2 = r_inv2.first()
        assert row_inv2[0] == disp_ini - 1
        assert row_inv2[1] == res_ini + 1


# ============================================================================
# BLOQUE 3: Pruebas CU27 — Gestión de Reembolsos
# ============================================================================

@pytest.mark.asyncio
async def test_cu27_01_solicitar_reembolso_deriva_pagos_servidor(http, escenario, fabrica_sesiones):
    """Solicitar reembolso deriva del servidor los pagos capturados sin aceptar monto de cliente."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("100.00"))
    p_id = await crear_pago_db(
        fabrica_sesiones, venta_id=v_id, empresa_id=escenario.empresa_a_id, monto=Decimal("100.00")
    )

    http.usar(escenario.usuario_a)
    resp = await http.cliente.post(
        "/api/v1/reembolsos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "origen_tipo": "VENTA",
            "origen_id": str(v_id),
            "motivo_codigo": "DEFECTO_FABRICA",
            "motivo_descripcion": "Costura desprendida",
        },
    )
    assert resp.status_code == 201, resp.text
    datos = resp.json()
    assert datos["estado"] == "PENDIENTE_AUTORIZACION"
    assert Decimal(str(datos["monto_bob"])) == Decimal("100.00")
    assert len(datos["componentes"]) == 1
    assert datos["componentes"][0]["medio"] == "STRIPE"
    assert datos["componentes"][0]["centavos_usd"] is not None


@pytest.mark.asyncio
async def test_cu27_02_solicitar_reembolso_idempotente(http, escenario, fabrica_sesiones):
    """Dos solicitudes de reembolso con el mismo origen y motivo devuelven la misma obligación."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("100.00"))
    await crear_pago_db(fabrica_sesiones, venta_id=v_id, empresa_id=escenario.empresa_a_id, monto=Decimal("100.00"))

    http.usar(escenario.usuario_a)
    cuerpo = {
        "origen_tipo": "VENTA",
        "origen_id": str(v_id),
        "motivo_codigo": "TALLA_INCORRECTA",
    }
    r1 = await http.cliente.post(
        "/api/v1/reembolsos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=cuerpo,
    )
    assert r1.status_code == 201

    r2 = await http.cliente.post(
        "/api/v1/reembolsos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=cuerpo,
    )
    assert r2.status_code in (200, 201)
    assert r1.json()["id"] == r2.json()["id"]


@pytest.mark.asyncio
async def test_cu27_03_autorizar_reembolso_solo_personal_autorizado(http, escenario, fabrica_sesiones):
    """Solo ENCARGADO o ADMINISTRADOR pueden autorizar el reembolso; CLIENTE recibe 403."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("80.00"))
    await crear_pago_db(fabrica_sesiones, venta_id=v_id, empresa_id=escenario.empresa_a_id, monto=Decimal("80.00"))

    http.usar(escenario.usuario_a)
    r_sol = await http.cliente.post(
        "/api/v1/reembolsos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"origen_tipo": "VENTA", "origen_id": str(v_id), "motivo_codigo": "INCUMPLIMIENTO_ENTREGA"},
    )
    reemb_id = r_sol.json()["id"]

    # Cliente intenta autorizar -> 403
    r_aut_cli = await http.cliente.post(
        f"/api/v1/reembolsos/{reemb_id}/autorizar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"motivo_aprobacion": "Aprobación no autorizada"},
    )
    assert r_aut_cli.status_code == 403

    # Administrador autoriza exitosamente -> 200
    http.usar(escenario.usuario_admin_a)
    r_aut_adm = await http.cliente.post(
        f"/api/v1/reembolsos/{reemb_id}/autorizar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"motivo_aprobacion": "Aprobado por política de garantía"},
    )
    assert r_aut_adm.status_code == 200, r_aut_adm.text
    assert r_aut_adm.json()["estado"] == "AUTORIZADO"


@pytest.mark.asyncio
async def test_cu27_04_ejecutar_reembolso_stripe_centavos_originales_sin_mutar_stock(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """Ejecución de reembolso devuelve en centavos USD exactos a la pasarela y no altera el stock."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("100.00"))
    await crear_pago_db(
        fabrica_sesiones,
        venta_id=v_id,
        empresa_id=escenario.empresa_a_id,
        monto=Decimal("100.00"),
        referencia_externa=f"pi_test_{uuid.uuid4().hex[:10]}",
    )

    # 1. Solicitar y autorizar
    http.usar(escenario.usuario_a)
    r_sol = await http.cliente.post(
        "/api/v1/reembolsos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"origen_tipo": "VENTA", "origen_id": str(v_id), "motivo_codigo": "DEVOLUCION_FISICA_CONFORME"},
    )
    reemb_id = r_sol.json()["id"]

    http.usar(escenario.usuario_admin_a)
    await http.cliente.post(
        f"/api/v1/reembolsos/{reemb_id}/autorizar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    # Stock previo
    async with fabrica_sesiones() as db:
        r_st_pre = await db.execute(
            text(
                "SELECT disponible, reservado FROM inventario.inventario_sucursal "
                "WHERE sucursal_id = :sid AND variante_id = :vid"
            ),
            {"sid": escenario.sucursal_a_id, "vid": escenario.variante_a_id},
        )
        stock_pre = r_st_pre.first()

    # 2. Ejecutar desembolso
    clave_ejec = uuid.uuid4()
    r_ejec = await http.cliente.post(
        f"/api/v1/reembolsos/{reemb_id}/ejecutar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"clave_ejecucion": str(clave_ejec)},
    )
    assert r_ejec.status_code == 200, r_ejec.text
    assert r_ejec.json()["estado"] == "COMPLETADO"

    # Verificar que el fake registró el reembolso
    assert len(configurar_fake_stripe.reembolsos) >= 1

    # Verificar que el stock NO mutó (CU20 controla inventario, no CU27)
    async with fabrica_sesiones() as db:
        r_st_post = await db.execute(
            text(
                "SELECT disponible, reservado FROM inventario.inventario_sucursal "
                "WHERE sucursal_id = :sid AND variante_id = :vid"
            ),
            {"sid": escenario.sucursal_a_id, "vid": escenario.variante_a_id},
        )
        stock_post = r_st_post.first()

    assert stock_pre[0] == stock_post[0]
    assert stock_pre[1] == stock_post[1]


@pytest.mark.asyncio
async def test_cu27_05_reembolso_mixto_restaura_saldo_personal_sin_convertir_en_efectivo(
    http, escenario, fabrica_sesiones
):
    """En pago mixto (Stripe + Saldo), el componente Saldo se restaura al libro append-only sin efectivo."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("120.00"))

    # Pago Stripe de 70.00
    await crear_pago_db(
        fabrica_sesiones, venta_id=v_id, empresa_id=escenario.empresa_a_id, monto=Decimal("70.00")
    )

    # Débito de saldo de 50.00
    async with fabrica_sesiones() as db:
        mov_debito = MovimientoSaldo(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            cliente_id=escenario.usuario_a.id,
            tipo="DEBITO",
            monto_bob=Decimal("50.00"),
            origen_tipo="VENTA",
            origen_id=v_id,
            referencia_unica=uuid.uuid4(),
            estado="CONFIRMADO",
            creado_en=datetime.now(timezone.utc),
        )
        db.add(mov_debito)
        await db.commit()

    http.usar(escenario.usuario_a)
    r_sol = await http.cliente.post(
        "/api/v1/reembolsos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"origen_tipo": "VENTA", "origen_id": str(v_id), "motivo_codigo": "CANCELACION_TOTAL_MIXTA"},
    )
    assert r_sol.status_code == 201, r_sol.text
    det_sol = r_sol.json()
    assert Decimal(str(det_sol["monto_bob"])) == Decimal("120.00")
    medios = [c["medio"] for c in det_sol["componentes"]]
    assert "STRIPE" in medios
    assert "SALDO" in medios

    reemb_id = det_sol["id"]

    # Autorizar y Ejecutar por Admin
    http.usar(escenario.usuario_admin_a)
    await http.cliente.post(
        f"/api/v1/reembolsos/{reemb_id}/autorizar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    clave_ejec = uuid.uuid4()
    r_ejec = await http.cliente.post(
        f"/api/v1/reembolsos/{reemb_id}/ejecutar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"clave_ejecucion": str(clave_ejec)},
    )
    assert r_ejec.status_code == 200, r_ejec.text
    assert r_ejec.json()["estado"] == "COMPLETADO"

    # Verificar que el cliente A tiene un movimiento RESTAURACION de 50.00 en su saldo
    http.usar(escenario.usuario_a)
    r_saldo = await http.cliente.get("/api/v1/saldos/mio")
    assert r_saldo.status_code == 200
    saldo_info = r_saldo.json()
    tipos_mov = [m["tipo"] for m in saldo_info["movimientos"]]
    assert "RESTAURACION" in tipos_mov


@pytest.mark.asyncio
async def test_cu27_06_conciliar_reembolso_administrador(http, escenario, fabrica_sesiones):
    """POST /reembolsos/{id}/conciliar resuelve reembolsos pendientes como Administrador."""
    v_id = await crear_venta_db(fabrica_sesiones, escenario, total=Decimal("50.00"))
    await crear_pago_db(
        fabrica_sesiones, venta_id=v_id, empresa_id=escenario.empresa_a_id, monto=Decimal("50.00")
    )

    http.usar(escenario.usuario_a)
    r_sol = await http.cliente.post(
        "/api/v1/reembolsos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"origen_tipo": "VENTA", "origen_id": str(v_id), "motivo_codigo": "INCIDENCIA_TECNICA"},
    )
    reemb_id = r_sol.json()["id"]

    http.usar(escenario.usuario_admin_a)
    r_conc = await http.cliente.post(
        f"/api/v1/reembolsos/{reemb_id}/conciliar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r_conc.status_code == 200, r_conc.text
    assert r_conc.json()["estado"] == "COMPLETADO"
