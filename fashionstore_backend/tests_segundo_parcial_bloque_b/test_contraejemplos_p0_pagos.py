"""Suite de Pruebas de Contraejemplos P0: Pagos y Compra Backend (Auditoría 20 y Plan 21 C1/C2).

Verifica de forma estricta contraejemplos que antes fallaban o vulneraban los contratos:
1. SetupIntent:
   - Inicia estrictamente en 'PENDIENTE' (requires_payment_method).
   - Intento de cobro off-session con método no listo rechaza con 409 METODO_NO_LISTO.
   - Confirmación explícita (POST /stripe/metodos/{id}/confirmar) consulta la pasarela,
     extrae customer y payment_method reales, y pasa a 'LISTO'.
2. Continuación 3DS / SCA (POST /stripe/ordenes/{id}/continuar):
   - Rechaza con 409 si payment_intent_id no coincide con la referencia externa de la orden.
   - No marca CAPTURADO si la pasarela responde 'requires_action'.
   - Marca CAPTURADO solo tras 'SUCCEEDED' validando moneda USD y centavos.
3. Webhook Stripe e Idempotencia:
   - Registra eventos en comercial.eventos_proveedor.
   - Repetición de webhook responde APROBADO sin duplicar stock ni órdenes.
   - Webhook setup_intent.succeeded actualiza MetodoPreparado a LISTO.
4. CU05 Sincronización y Autorización v3:
   - 15 campos contractuales obligatorios validados estrictamente.
   - Faltantes o método no LISTO -> PENDIENTE_INTERVENCION (AUTORIZACION_REQUERIDA).
   - Precio o tasa cambiados, o huella alterada -> REQUIERE_NUEVA_ACEPTACION (PRECIO_CAMBIADO).
   - Continuación durable: reintento con misma operacion_id y nueva autorización transiciona
     sin violar idempotencia ni duplicar pedidos.
   - consultarOperacion refleja dinámicamente el estado real del PedidoCompra.
5. ReembolsoService (CU27):
   - Derivación estricta a partir de dinero real capturado; prohíbe reembolsos ficticios.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from backend.app.core.config import settings
from backend.app.core.modules.inventario.models import InventarioSucursal
from backend.app.core.modules.reservas_traslados.models import OperacionSincronizacion
from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import (
    FakeStripeGateway,
    fijar_gateway,
)
from backend.app.core.modules.ventas_pagos.services.pedido_service import (
    ObligacionReembolso,
    PedidoCompra,
)
from backend.app.core.modules.ventas_pagos.models_ordenes import (
    EventoProveedor,
    MetodoPreparado,
    OrdenPago,
)
from backend.app.core.modules.ventas_pagos.models import Venta
from backend.app.core.modules.ventas_pagos.services.reembolso_service import ReembolsoService


@pytest.fixture
def configurar_fake_stripe():
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    yield fake
    fijar_gateway(None)


def firmar_webhook_stripe(cuerpo: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = timestamp or int(time.time())
    payload = f"{ts}.".encode("utf-8") + cuerpo
    firma = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={firma}"


# =============================================================================
# 1. SETUPINTENT Y METODO PREPARADO (CU22)
# =============================================================================

@pytest.mark.asyncio
async def test_contraejemplo_metodo_preparado_inicia_pendiente_y_bloquea_off_session(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0-CU22: SetupIntent inicia en PENDIENTE. Intentar cobrar off-session rechaza con 409."""
    http.usar(escenario.usuario_a)

    # 1. Preparar método
    resp_prep = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"huella_dispositivo": "disp_test"},
    )
    assert resp_prep.status_code == 201, resp_prep.text
    datos_prep = resp_prep.json()
    metodo_id = uuid.UUID(datos_prep["preparacion_pago_id"])
    assert datos_prep["estado"] == "PENDIENTE"
    assert datos_prep["client_secret"] is not None

    # Verificar en base de datos que está en PENDIENTE
    async with fabrica_sesiones() as db:
        mp = await db.get(MetodoPreparado, metodo_id)
        assert mp is not None
        assert mp.estado == "PENDIENTE"

    # 2. Crear un pedido borrador para intentar cobrarlo off-session
    p_id = uuid.uuid4()
    ahora = datetime.now(timezone.utc)
    async with fabrica_sesiones() as db:
        await db.execute(
            text(
                "INSERT INTO comercial.pedidos_compra "
                "(id, empresa_id, cliente_id, sucursal_id, estado, estado_pago, estado_cumplimiento, "
                "modalidad, subtotal_bob, descuento_bob, envio_bob, total_bob, revision, creado_en, actualizado_en) "
                "VALUES (:id, :eid, :cid, :sid, 'BORRADOR', 'SIN_PAGO', 'SIN_ASIGNACION', "
                "'RECOJO', 100.0, 0, 0, 100.0, 1, :ahora, :ahora)"
            ),
            {"id": p_id, "eid": escenario.empresa_a_id, "cid": escenario.usuario_a.id, "sid": escenario.sucursal_a_id, "ahora": ahora},
        )
        await db.execute(
            text(
                "INSERT INTO comercial.detalles_pedido "
                "(id, empresa_id, pedido_id, variante_id, cantidad, precio_unitario_bob, descuento_bob, total_bob, oferta_revision) "
                "VALUES (:id, :eid, :pid, :vid, 1, 100.0, 0, 100.0, 1)"
            ),
            {"id": uuid.uuid4(), "eid": escenario.empresa_a_id, "pid": p_id, "vid": escenario.variante_a_id},
        )
        await db.commit()

    # 3. Intentar cobrar con método NO listo -> Debe fallar con 409 METODO_NO_LISTO
    resp_cobro = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "contexto": "PEDIDO",
            "recurso_id": str(p_id),
            "metodo_preparado_id": str(metodo_id),
        },
    )
    assert resp_cobro.status_code == 409, resp_cobro.text
    assert "METODO_NO_LISTO" in resp_cobro.text


@pytest.mark.asyncio


async def test_contraejemplo_confirmacion_metodo_preparado_habilita_off_session(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0-CU22: Confirmar SetupIntent transiciona a LISTO con método real y permite cobro off-session."""
    http.usar(escenario.usuario_a)

    # 1. Preparar método
    resp_prep = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"huella_dispositivo": "disp_test"},
    )
    assert resp_prep.status_code == 201
    metodo_id = resp_prep.json()["preparacion_pago_id"]

    # 2. Confirmar método vía nuevo endpoint POST /stripe/metodos/{id}/confirmar
    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/metodos/{metodo_id}/confirmar",
        json={"payment_method_id": "pm_card_visa_test"},
    )
    assert resp_conf.status_code == 200, resp_conf.text
    datos_conf = resp_conf.json()
    assert datos_conf["estado"] == "LISTO"

    # Verificar en base de datos que guardó cliente y método cifrados y estado LISTO
    async with fabrica_sesiones() as db:
        mp = await db.get(MetodoPreparado, uuid.UUID(metodo_id))
        assert mp.estado == "LISTO"
        assert mp.cliente_proveedor_cifrado is not None
        assert mp.metodo_proveedor_cifrado is not None

    # 3. Ahora el cobro off-session debe ejecutarse exitosamente
    p_id = uuid.uuid4()
    ahora = datetime.now(timezone.utc)
    async with fabrica_sesiones() as db:
        await db.execute(
            text(
                "INSERT INTO comercial.pedidos_compra "
                "(id, empresa_id, cliente_id, sucursal_id, estado, estado_pago, estado_cumplimiento, "
                "modalidad, subtotal_bob, descuento_bob, envio_bob, total_bob, revision, creado_en, actualizado_en) "
                "VALUES (:id, :eid, :cid, :sid, 'BORRADOR', 'SIN_PAGO', 'SIN_ASIGNACION', "
                "'RECOJO', 100.0, 0, 0, 100.0, 1, :ahora, :ahora)"
            ),
            {"id": p_id, "eid": escenario.empresa_a_id, "cid": escenario.usuario_a.id, "sid": escenario.sucursal_a_id, "ahora": ahora},
        )
        await db.execute(
            text(
                "INSERT INTO comercial.detalles_pedido "
                "(id, empresa_id, pedido_id, variante_id, cantidad, precio_unitario_bob, descuento_bob, total_bob, oferta_revision) "
                "VALUES (:id, :eid, :pid, :vid, 1, 100.0, 0, 100.0, 1)"
            ),
            {"id": uuid.uuid4(), "eid": escenario.empresa_a_id, "pid": p_id, "vid": escenario.variante_a_id},
        )
        await db.commit()

    resp_cobro = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "contexto": "PEDIDO",
            "recurso_id": str(p_id),
            "metodo_preparado_id": str(metodo_id),
        },
    )
    assert resp_cobro.status_code == 201, resp_cobro.text
    orden_data = resp_cobro.json()
    assert orden_data["estado"] == "CAPTURADO"


@pytest.mark.asyncio


async def test_contraejemplo_setup_intent_succeeded_sin_customer_es_rechazado_y_no_se_marca_listo(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0-CU22: SetupIntent succeeded sin customer (o cus inválido) es rechazado con 400 y conserva estado PENDIENTE."""
    http.usar(escenario.usuario_a)

    resp_prep = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"huella_dispositivo": "disp_test"},
    )
    assert resp_prep.status_code == 201
    metodo_id = resp_prep.json()["preparacion_pago_id"]

    # Simular que pasarela devuelve succeeded pero sin customer
    configurar_fake_stripe.simular_sin_customer = True

    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/metodos/{metodo_id}/confirmar",
        json={"payment_method_id": "pm_card_test"},
    )
    assert resp_conf.status_code == 400, resp_conf.text
    assert "customer" in resp_conf.json()["detail"].lower()

    # Revalidar que en consulta y en BD sigue en PENDIENTE y nunca pasó a LISTO
    resp_get = await http.cliente.get(f"/api/v1/pagos/stripe/metodos/{metodo_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["estado"] == "PENDIENTE"

    async with fabrica_sesiones() as db:
        mp = await db.get(MetodoPreparado, uuid.UUID(metodo_id))
        assert mp.estado == "PENDIENTE"


@pytest.mark.asyncio


async def test_contraejemplo_setup_intent_succeeded_sin_payment_method_es_rechazado_y_no_se_marca_listo(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0-CU22: SetupIntent succeeded sin payment_method (o pm inválido) es rechazado con 400 y conserva PENDIENTE."""
    http.usar(escenario.usuario_a)

    resp_prep = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert resp_prep.status_code == 201
    metodo_id = resp_prep.json()["preparacion_pago_id"]

    # Simular que pasarela devuelve succeeded pero sin payment_method
    configurar_fake_stripe.simular_sin_payment_method = True

    resp_conf = await http.cliente.post(
        f"/api/v1/pagos/stripe/metodos/{metodo_id}/confirmar",
        json={},
    )
    assert resp_conf.status_code == 400, resp_conf.text
    assert "paymentmethod" in resp_conf.json()["detail"].lower()

    # Verificar que persiste en PENDIENTE
    async with fabrica_sesiones() as db:
        mp = await db.get(MetodoPreparado, uuid.UUID(metodo_id))
        assert mp.estado == "PENDIENTE"


@pytest.mark.asyncio


async def test_contraejemplo_setup_intent_customer_ajeno_y_metodo_no_adjunto_rechazados(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0-CU22: SetupIntent con customer ajeno o payment method no adjunto es rechazado con 400."""
    http.usar(escenario.usuario_a)

    # 1. Customer ajeno que parece válido (no solo 'cus_ajeno')
    resp_prep1 = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    m_id1 = resp_prep1.json()["preparacion_pago_id"]
    configurar_fake_stripe.simular_customer_ajeno = True
    configurar_fake_stripe.customer_ajeno_personalizado = f"cus_otro_valido_{uuid.uuid4().hex[:8]}"

    r_conf1 = await http.cliente.post(f"/api/v1/pagos/stripe/metodos/{m_id1}/confirmar")
    assert r_conf1.status_code == 400
    assert "otro usuario" in r_conf1.json()["detail"].lower() or "no coincide" in r_conf1.json()["detail"].lower()
    configurar_fake_stripe.simular_customer_ajeno = False
    configurar_fake_stripe.customer_ajeno_personalizado = None

    # 2. Payment method no adjunto
    resp_prep2 = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    m_id2 = resp_prep2.json()["preparacion_pago_id"]
    configurar_fake_stripe.simular_metodo_no_adjunto = True

    r_conf2 = await http.cliente.post(f"/api/v1/pagos/stripe/metodos/{m_id2}/confirmar")
    assert r_conf2.status_code == 400
    assert "adjunto" in r_conf2.json()["detail"].lower() or "válido" in r_conf2.json()["detail"].lower()
    configurar_fake_stripe.simular_metodo_no_adjunto = False

    # 3. Payment method asociado a otro customer en Stripe
    resp_prep3 = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    m_id3 = resp_prep3.json()["preparacion_pago_id"]
    configurar_fake_stripe.simular_metodo_otro_customer = True
    configurar_fake_stripe.metodo_otro_customer_id = f"cus_otro_propietario_{uuid.uuid4().hex[:6]}"

    r_conf3 = await http.cliente.post(f"/api/v1/pagos/stripe/metodos/{m_id3}/confirmar")
    assert r_conf3.status_code == 400
    assert "no pertenece" in r_conf3.json()["detail"].lower() or "adjunto" in r_conf3.json()["detail"].lower()
    configurar_fake_stripe.simular_metodo_otro_customer = False


@pytest.mark.asyncio


async def test_contraejemplo_setup_intent_fallo_temporal_y_reintento(
    http, escenario, configurar_fake_stripe
):
    """P0-CU22: Fallo temporal en pasarela retorna 503 y permite reintento exitoso."""
    http.usar(escenario.usuario_a)

    resp_prep = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert resp_prep.status_code == 201
    m_id = resp_prep.json()["preparacion_pago_id"]

    # Simular 1 fallo temporal
    configurar_fake_stripe.fallos_temporales_restantes = 1
    r_fallo = await http.cliente.post(f"/api/v1/pagos/stripe/metodos/{m_id}/confirmar")
    assert r_fallo.status_code == 503

    # Reintento exitoso
    r_ok = await http.cliente.post(f"/api/v1/pagos/stripe/metodos/{m_id}/confirmar")
    assert r_ok.status_code == 200
    assert r_ok.json()["estado"] == "LISTO"

    # Confirmación posterior es idempotente
    r_idem = await http.cliente.post(f"/api/v1/pagos/stripe/metodos/{m_id}/confirmar")
    assert r_idem.status_code == 200
    assert r_idem.json()["estado"] == "LISTO"


@pytest.mark.asyncio


async def test_contraejemplo_multitenant_metodos_y_ordenes_aisladas(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0-CU22: Usuario de Empresa B no puede consultar ni confirmar métodos ni órdenes de Empresa A (403 Forbidden)."""
    # 1. Usuario A crea método preparado en Empresa A
    http.usar(escenario.usuario_a)
    resp_prep = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    m_id = resp_prep.json()["preparacion_pago_id"]

    # Usuario B de Empresa B intenta consultar y confirmar método de A -> 403
    http.usar(escenario.usuario_b)
    r_get_b = await http.cliente.get(f"/api/v1/pagos/stripe/metodos/{m_id}")
    assert r_get_b.status_code == 403, r_get_b.text

    r_conf_b = await http.cliente.post(f"/api/v1/pagos/stripe/metodos/{m_id}/confirmar")
    assert r_conf_b.status_code == 403, r_conf_b.text

    # 2. Usuario A crea orden de pago en Empresa A
    http.usar(escenario.usuario_a)
    await http.cliente.post(f"/api/v1/pagos/stripe/metodos/{m_id}/confirmar")

    p_id = uuid.uuid4()
    ahora = datetime.now(timezone.utc)
    async with fabrica_sesiones() as db:
        await db.execute(
            text(
                "INSERT INTO comercial.pedidos_compra "
                "(id, empresa_id, cliente_id, sucursal_id, estado, estado_pago, estado_cumplimiento, "
                "modalidad, subtotal_bob, descuento_bob, envio_bob, total_bob, revision, creado_en, actualizado_en) "
                "VALUES (:id, :eid, :cid, :sid, 'BORRADOR', 'SIN_PAGO', 'SIN_ASIGNACION', "
                "'RECOJO', 100.0, 0, 0, 100.0, 1, :ahora, :ahora)"
            ),
            {"id": p_id, "eid": escenario.empresa_a_id, "cid": escenario.usuario_a.id, "sid": escenario.sucursal_a_id, "ahora": ahora},
        )
        await db.execute(
            text(
                "INSERT INTO comercial.detalles_pedido "
                "(id, empresa_id, pedido_id, variante_id, cantidad, precio_unitario_bob, descuento_bob, total_bob, oferta_revision) "
                "VALUES (:id, :eid, :pid, :vid, 1, 100.0, 0, 100.0, 1)"
            ),
            {"id": uuid.uuid4(), "eid": escenario.empresa_a_id, "pid": p_id, "vid": escenario.variante_a_id},
        )
        await db.commit()

    configurar_fake_stripe.simular_requiere_accion = True
    r_ord = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"contexto": "PEDIDO", "recurso_id": str(p_id)},
    )
    assert r_ord.status_code == 201
    ord_id = r_ord.json()["orden_pago_id"]

    # Usuario B intenta consultar y continuar la orden de Usuario A -> 403
    http.usar(escenario.usuario_b)
    r_ord_b = await http.cliente.get(f"/api/v1/pagos/stripe/ordenes/{ord_id}")
    assert r_ord_b.status_code == 403, r_ord_b.text

    r_cont_b = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{ord_id}/continuar-accion",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert r_cont_b.status_code == 403, r_cont_b.text
    configurar_fake_stripe.simular_requiere_accion = False


# =============================================================================
# 2. CONTINUACIÓN 3DS Y VALIDACIÓN DE REFERENCIA EXTERNA (CU22)
# =============================================================================

@pytest.mark.asyncio


async def test_contraejemplo_continuar_accion_rechaza_payment_intent_mismatched(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0-CU22: continuar_accion rechaza con 409 si el cliente intenta confirmar un PI ajeno a la orden."""
    http.usar(escenario.usuario_a)
    p_id = uuid.uuid4()
    ahora = datetime.now(timezone.utc)

    async with fabrica_sesiones() as db:
        await db.execute(
            text(
                "INSERT INTO comercial.pedidos_compra "
                "(id, empresa_id, cliente_id, sucursal_id, estado, estado_pago, estado_cumplimiento, "
                "modalidad, subtotal_bob, descuento_bob, envio_bob, total_bob, revision, creado_en, actualizado_en) "
                "VALUES (:id, :eid, :cid, :sid, 'BORRADOR', 'EN_VERIFICACION', 'SIN_ASIGNACION', "
                "'RECOJO', 100.0, 0, 0, 100.0, 1, :ahora, :ahora)"
            ),
            {"id": p_id, "eid": escenario.empresa_a_id, "cid": escenario.usuario_a.id, "sid": escenario.sucursal_a_id, "ahora": ahora},
        )
        await db.execute(
            text(
                "INSERT INTO comercial.detalles_pedido "
                "(id, empresa_id, pedido_id, variante_id, cantidad, precio_unitario_bob, descuento_bob, total_bob, oferta_revision) "
                "VALUES (:id, :eid, :pid, :vid, 1, 100.0, 0, 100.0, 1)"
            ),
            {"id": uuid.uuid4(), "eid": escenario.empresa_a_id, "pid": p_id, "vid": escenario.variante_a_id},
        )
        await db.commit()

    configurar_fake_stripe.simular_requiere_accion = True
    r_ord = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"contexto": "PEDIDO", "recurso_id": str(p_id)},
    )
    assert r_ord.status_code == 201
    ord_id = r_ord.json()["orden_pago_id"]

    # Intentar continuar con un payment_intent_id falso/dispar
    r_cont = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{ord_id}/continuar-accion",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"payment_intent_id": "pi_ajeno_hacker_123"},
    )
    assert r_cont.status_code == 409, r_cont.text


@pytest.mark.asyncio


async def test_contraejemplo_continuar_accion_no_captura_si_pasarela_exige_accion(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0-CU22: continuar_accion no pasa a CAPTURADO si la pasarela aún devuelve requires_action."""
    http.usar(escenario.usuario_a)
    p_id = uuid.uuid4()
    ahora = datetime.now(timezone.utc)

    async with fabrica_sesiones() as db:
        await db.execute(
            text(
                "INSERT INTO comercial.pedidos_compra "
                "(id, empresa_id, cliente_id, sucursal_id, estado, estado_pago, estado_cumplimiento, "
                "modalidad, subtotal_bob, descuento_bob, envio_bob, total_bob, revision, creado_en, actualizado_en) "
                "VALUES (:id, :eid, :cid, :sid, 'BORRADOR', 'EN_VERIFICACION', 'SIN_ASIGNACION', "
                "'RECOJO', 100.0, 0, 0, 100.0, 1, :ahora, :ahora)"
            ),
            {"id": p_id, "eid": escenario.empresa_a_id, "cid": escenario.usuario_a.id, "sid": escenario.sucursal_a_id, "ahora": ahora},
        )
        await db.execute(
            text(
                "INSERT INTO comercial.detalles_pedido "
                "(id, empresa_id, pedido_id, variante_id, cantidad, precio_unitario_bob, descuento_bob, total_bob, oferta_revision) "
                "VALUES (:id, :eid, :pid, :vid, 1, 100.0, 0, 100.0, 1)"
            ),
            {"id": uuid.uuid4(), "eid": escenario.empresa_a_id, "pid": p_id, "vid": escenario.variante_a_id},
        )
        await db.commit()

    configurar_fake_stripe.simular_requiere_accion = True
    r_ord = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"contexto": "PEDIDO", "recurso_id": str(p_id)},
    )
    assert r_ord.status_code == 201
    ord_id = r_ord.json()["orden_pago_id"]

    # Simular que el cliente intenta continuar pero la pasarela sigue requiriendo acción
    r_cont = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{ord_id}/continuar-accion",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert r_cont.status_code == 200, r_cont.text
    assert r_cont.json()["estado"] == "REQUIERE_ACCION_CLIENTE"

    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, uuid.UUID(ord_id))
        assert op.estado != "CAPTURADO"
        assert op.estado == "REQUIERE_ACCION_CLIENTE"


@pytest.mark.asyncio


async def test_contraejemplo_off_session_con_requiere_accion_conserva_orden_y_evita_falsa_captura(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0-CU22: Cobro off-session que exige 3DS pasa a REQUIERE_ACCION_CLIENTE sin declarar captura falsa,
    y tras continuar_accion transiciona a CAPTURADO."""
    http.usar(escenario.usuario_a)

    # 1. Preparar y confirmar método
    resp_prep = await http.cliente.post(
        "/api/v1/pagos/stripe/metodos/preparar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    m_id = resp_prep.json()["preparacion_pago_id"]
    await http.cliente.post(
        f"/api/v1/pagos/stripe/metodos/{m_id}/confirmar",
        json={"payment_method_id": "pm_card_test_3ds"},
    )

    # 2. Crear pedido de compra
    p_id = uuid.uuid4()
    ahora = datetime.now(timezone.utc)
    async with fabrica_sesiones() as db:
        await db.execute(
            text(
                "INSERT INTO comercial.pedidos_compra "
                "(id, empresa_id, cliente_id, sucursal_id, estado, estado_pago, estado_cumplimiento, "
                "modalidad, subtotal_bob, descuento_bob, envio_bob, total_bob, revision, creado_en, actualizado_en) "
                "VALUES (:id, :eid, :cid, :sid, 'BORRADOR', 'SIN_PAGO', 'SIN_ASIGNACION', "
                "'RECOJO', 100.0, 0, 0, 100.0, 1, :ahora, :ahora)"
            ),
            {"id": p_id, "eid": escenario.empresa_a_id, "cid": escenario.usuario_a.id, "sid": escenario.sucursal_a_id, "ahora": ahora},
        )
        await db.execute(
            text(
                "INSERT INTO comercial.detalles_pedido "
                "(id, empresa_id, pedido_id, variante_id, cantidad, precio_unitario_bob, descuento_bob, total_bob, oferta_revision) "
                "VALUES (:id, :eid, :pid, :vid, 1, 100.0, 0, 100.0, 1)"
            ),
            {"id": uuid.uuid4(), "eid": escenario.empresa_a_id, "pid": p_id, "vid": escenario.variante_a_id},
        )
        await db.commit()

    # 3. Intentar cobro off-session pero simulando desafío 3DS
    configurar_fake_stripe.simular_requiere_accion = True

    r_ord = await http.cliente.post(
        "/api/v1/pagos/stripe/ordenes",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "contexto": "PEDIDO",
            "recurso_id": str(p_id),
            "metodo_preparado_id": str(m_id),
        },
    )
    assert r_ord.status_code == 201
    ord_data = r_ord.json()
    assert ord_data["estado"] == "REQUIERE_ACCION_CLIENTE"
    ord_id = ord_data["orden_pago_id"]
    pi_ref = ord_data["referencia_externa"]

    # Verificar que NO se declaró captura falsa en el pedido
    async with fabrica_sesiones() as db:
        p_bd = await db.get(PedidoCompra, p_id)
        assert p_bd.estado_pago != "PAGADO"

    # 4. Completar autenticación 3DS en pasarela y continuar acción
    configurar_fake_stripe.simular_requiere_accion = False

    r_cont = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{ord_id}/continuar-accion",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"payment_intent_id": pi_ref},
    )
    assert r_cont.status_code == 200
    assert r_cont.json()["estado"] == "CAPTURADO"

    # Ahora sí el pedido debe estar capturado/confirmado
    async with fabrica_sesiones() as db:
        p_bd = await db.get(PedidoCompra, p_id)
        assert p_bd.estado_pago == "PAGADO"



# =============================================================================
# 3. CU05 SINCRONIZACIÓN Y AUTORIZACIÓN V3
# =============================================================================

@pytest.mark.asyncio


async def test_contraejemplo_cu05_autorizacion_incompleta_da_pendiente_intervencion(
    http, escenario
):
    """P0-CU05: Autorización de cobro a la que le faltan campos contractuales retorna PENDIENTE_INTERVENCION."""
    http.usar(escenario.usuario_a)

    disp_id = uuid.uuid4()
    resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
    ref_id = resp_ref.json()["referencia_horaria_id"]
    ahora_local = datetime.now(timezone.utc)

    # Payload v3 con datos pero autorizacion_cobro con campos faltantes (sin tasa, huella, etc.)
    op_payload = {
        "version_esquema": 3,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 1,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "autorizacion_cobro": {
                "consentimiento_id": str(uuid.uuid4()),
                "total_bob": "100.00",
                # Faltan 13 campos obligatorios de la v3
            },
        },
    }

    # 1. Objeto autorizacion_cobro presente pero incompleto -> 422 Unprocessable Entity
    resp_incompleto = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
    assert resp_incompleto.status_code == 422, resp_incompleto.text

    # 2. Objeto autorizacion_cobro omitido -> 200 PENDIENTE_INTERVENCION sin cobro
    op_payload_omitido = {
        "version_esquema": 3,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 2,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    resp_omitido = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload_omitido)
    assert resp_omitido.status_code == 200, resp_omitido.text
    res = resp_omitido.json()
    assert res["estado"] == "PENDIENTE_INTERVENCION"
    assert res["codigo"] == "AUTORIZACION_REQUERIDA"


@pytest.mark.asyncio


async def test_contraejemplo_cu05_huella_compra_alterada_da_requiere_nueva_aceptacion(
    http, escenario, fabrica_sesiones
):
    """P0-CU05: Si la huella_compra no coincide con el cálculo canónico retorna REQUIERE_NUEVA_ACEPTACION."""
    http.usar(escenario.usuario_a)

    disp_id = uuid.uuid4()
    resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
    ref_id = resp_ref.json()["referencia_horaria_id"]
    ahora_local = datetime.now(timezone.utc)
    metodo_prep_id = uuid.uuid4()

    async with fabrica_sesiones() as db:
        mp = MetodoPreparado(
            id=metodo_prep_id,
            empresa_id=escenario.empresa_a_id,
            cliente_id=escenario.usuario_a.id,
            proveedor="STRIPE",
            cliente_proveedor_cifrado=b"cus_test",
            metodo_proveedor_cifrado=b"pm_test",
            preparacion_proveedor_cifrado=b"seti_test",
            estado="LISTO",
        )
        db.add(mp)
        r_t = await db.execute(select(text("id, tasa_bob_por_usd FROM plataforma.tasas_cambio ORDER BY vigente_desde DESC LIMIT 1")))
        f_t = r_t.first()
        tasa_id = f_t[0] if f_t else uuid.uuid4()
        tasa_val = Decimal(str(f_t[1])) if f_t else Decimal("6.96")
        await db.commit()

    cid = uuid.uuid4()
    usd_cobro = (Decimal("100.00") / tasa_val).quantize(Decimal("0.01"))
    huella_alterada = "0" * 64  # Huella corrupta/falsificada

    op_payload = {
        "version_esquema": 3,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 2,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "autorizacion_cobro": {
                "consentimiento_id": str(cid),
                "aceptado_local_en": ahora_local.isoformat(),
                "huella_compra": huella_alterada,
                "base_bob": "100.00",
                "descuento_bob": "0.00",
                "envio_bob": "0.00",
                "total_bob": "100.00",
                "moneda_cobro": "USD",
                "importe_cobro": str(usd_cobro),
                "tasa_id": str(tasa_id),
                "tasa_bob_por_usd": str(tasa_val),
                "condiciones_version": "v3",
                "vigente_hasta": (ahora_local + timedelta(hours=24)).isoformat(),
                "preparacion_pago_id": str(metodo_prep_id),
                "permite_cobro_al_reconectar": True,
            },
        },
    }

    resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["estado"] == "REQUIERE_NUEVA_ACEPTACION"
    assert res["codigo"] == "PRECIO_CAMBIADO"


@pytest.mark.asyncio


async def test_contraejemplo_cu05_continuacion_durable_tras_pendiente_intervencion(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0-CU05: Reintento con misma operacion_id y autorización válida resuelve la orden durablemente."""
    http.usar(escenario.usuario_a)

    disp_id = uuid.uuid4()
    resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
    ref_id = resp_ref.json()["referencia_horaria_id"]
    ahora_local = datetime.now(timezone.utc)
    operacion_id = uuid.uuid4()

    # 1. Enviar primera vez sin consentimiento -> PENDIENTE_INTERVENCION
    op_payload_incompleta = {
        "version_esquema": 3,
        "operacion_id": str(operacion_id),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 10,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    r1 = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload_incompleta)
    assert r1.status_code == 200
    assert r1.json()["estado"] == "PENDIENTE_INTERVENCION"

    # 2. El cliente reacciona en la app móvil: prepara método y firma consentimiento válido
    metodo_prep_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        mp = MetodoPreparado(
            id=metodo_prep_id,
            empresa_id=escenario.empresa_a_id,
            cliente_id=escenario.usuario_a.id,
            proveedor="STRIPE",
            cliente_proveedor_cifrado=b"cus_test",
            metodo_proveedor_cifrado=b"pm_test",
            preparacion_proveedor_cifrado=b"seti_test",
            estado="LISTO",
        )
        db.add(mp)
        r_t = await db.execute(select(text("id, tasa_bob_por_usd FROM plataforma.tasas_cambio ORDER BY vigente_desde DESC LIMIT 1")))
        f_t = r_t.first()
        tasa_id = f_t[0] if f_t else uuid.uuid4()
        tasa_val = Decimal(str(f_t[1])) if f_t else Decimal("6.96")
        await db.commit()

    cid = uuid.uuid4()
    usd_cobro = (Decimal("100.00") / tasa_val).quantize(Decimal("0.01"))
    huella_valida = hashlib.sha256(f"{cid}:100.00:USD:{metodo_prep_id}".encode("utf-8")).hexdigest()

    # Reenviar la MISMA operacion_id con autorización completa
    op_payload_completa = {
        "version_esquema": 3,
        "operacion_id": str(operacion_id),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 11,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "autorizacion_cobro": {
                "consentimiento_id": str(cid),
                "aceptado_local_en": ahora_local.isoformat(),
                "huella_compra": huella_valida,
                "base_bob": "100.00",
                "descuento_bob": "0.00",
                "envio_bob": "0.00",
                "total_bob": "100.00",
                "moneda_cobro": "USD",
                "importe_cobro": str(usd_cobro),
                "tasa_id": str(tasa_id),
                "tasa_bob_por_usd": str(tasa_val),
                "condiciones_version": "v3",
                "vigente_hasta": (ahora_local + timedelta(hours=24)).isoformat(),
                "preparacion_pago_id": str(metodo_prep_id),
                "permite_cobro_al_reconectar": True,
            },
        },
    }
    r2 = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload_completa)
    assert r2.status_code == 200, r2.text
    res2 = r2.json()
    assert res2["estado"] == "ACEPTADA"
    assert res2["codigo"] == "OK"
    assert res2["recurso_id"] is not None

    # Verificar que solo existe exactamente 1 PedidoCompra para esta operación
    async with fabrica_sesiones() as db:
        pedidos = (
            await db.execute(
                select(PedidoCompra).where(
                    PedidoCompra.operacion_id == operacion_id
                )
            )
        ).scalars().all()
        assert len(pedidos) == 1
        assert pedidos[0].estado == "CONFIRMADO"
        assert pedidos[0].estado_pago == "PAGADO"
        assert pedidos[0].estado_cumplimiento == "COMPROMETIDO"


# =============================================================================
# 4. WEBHOOK STRIPE IDEMPOTENCIA Y SETUP_INTENT.SUCCEEDED
# =============================================================================

@pytest.mark.asyncio


async def test_contraejemplo_webhook_setup_intent_succeeded_actualiza_metodo_a_listo(
    http, escenario, fabrica_sesiones
):
    """P0-CU22: Webhook setup_intent.succeeded actualiza MetodoPreparado a LISTO e inserta evento."""
    metodo_prep_id = uuid.uuid4()
    seti_id = f"seti_test_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        mp = MetodoPreparado(
            id=metodo_prep_id,
            empresa_id=escenario.empresa_a_id,
            cliente_id=escenario.usuario_a.id,
            proveedor="STRIPE",
            cliente_proveedor_cifrado=b"",
            metodo_proveedor_cifrado=b"",
            preparacion_proveedor_cifrado=seti_id.encode("utf-8"),
            estado="PENDIENTE",
        )
        db.add(mp)
        await db.commit()

    evt_id = f"evt_{uuid.uuid4().hex[:12]}"
    payload = {
        "id": evt_id,
        "type": "setup_intent.succeeded",
        "livemode": False,
        "data": {
            "object": {
                "id": seti_id,
                "customer": "cus_webhook_test_123",
                "payment_method": "pm_webhook_test_456",
                "status": "succeeded",
            }
        },
    }
    cuerpo = json.dumps(payload).encode("utf-8")
    secreto = settings.STRIPE_WEBHOOK_SECRET or "whsec_test"
    firma = firmar_webhook_stripe(cuerpo, secreto)

    resp = await http.cliente.post(
        "/api/v1/pagos/stripe/webhook",
        headers={"Stripe-Signature": firma, "Content-Type": "application/json"},
        content=cuerpo,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado"] == "LISTO"

    # Verificar que el método pasó a LISTO y se registró el evento de forma persistente
    async with fabrica_sesiones() as db:
        mp_actual = await db.get(MetodoPreparado, metodo_prep_id)
        assert mp_actual.estado == "LISTO"
        assert mp_actual.cliente_proveedor_cifrado == b"cus_webhook_test_123"
        assert mp_actual.metodo_proveedor_cifrado == b"pm_webhook_test_456"

        stmt_evt = select(EventoProveedor).where(EventoProveedor.evento_externo_id == evt_id)
        reg_evt = (await db.execute(stmt_evt)).scalars().first()
        assert reg_evt is not None
        assert reg_evt.estado == "PROCESADO"


# =============================================================================
# 5. REEMBOLSOS ESTRICTOS DERIVADOS DE CAPTURA REAL (CU27)
# =============================================================================

@pytest.mark.asyncio


async def test_contraejemplo_cu27_reembolso_solo_sobre_dinero_capturado(
    http, escenario, fabrica_sesiones
):
    """P0-CU27: ReembolsoService rechaza crear reembolso si el recurso no tiene pago capturado real."""
    from backend.app.core.modules.posventa.schemas import ReembolsoSolicitudDTO
    from fastapi import HTTPException

    async with fabrica_sesiones() as db:
        service = ReembolsoService(db)

        # 1. Intentar reembolso sobre un pedido con SIN_PAGO -> Rechaza con 409 SIN_FONDOS_CAPTURADOS
        p_sin_pago_id = uuid.uuid4()
        ahora = datetime.now(timezone.utc)
        await db.execute(
            text(
                "INSERT INTO comercial.pedidos_compra "
                "(id, empresa_id, cliente_id, sucursal_id, estado, estado_pago, estado_cumplimiento, "
                "modalidad, subtotal_bob, descuento_bob, envio_bob, total_bob, revision, creado_en, actualizado_en) "
                "VALUES (:id, :eid, :cid, :sid, 'BORRADOR', 'SIN_PAGO', 'SIN_ASIGNACION', "
                "'RECOJO', 100.0, 0, 0, 100.0, 1, :ahora, :ahora)"
            ),
            {"id": p_sin_pago_id, "eid": escenario.empresa_a_id, "cid": escenario.usuario_a.id, "sid": escenario.sucursal_a_id, "ahora": ahora},
        )
        await db.commit()

        with pytest.raises(HTTPException) as excinfo:
            await service.solicitar_reembolso(
                usuario=escenario.usuario_a,
                datos=ReembolsoSolicitudDTO(
                    origen_tipo="PEDIDO",
                    origen_id=p_sin_pago_id,
                    motivo_codigo="SIN_STOCK",
                    motivo_detalle="Prueba de fallo",
                ),
                clave_idempotencia=uuid.uuid4(),
            )
        assert excinfo.value.status_code == 409
        assert "SIN_FONDOS_CAPTURADOS" in str(excinfo.value.detail)


# =============================================================================
# CONTRAEJEMPLOS AUDITORÍA 33 — SUBAGENTE A: PAGOS STRIPE Y CONFIRMACIÓN / CANCELACIÓN
# =============================================================================

@pytest.mark.asyncio


async def test_contraejemplo_confirmar_orden_datos_incongruentes_rechaza_400(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """Contraejemplo 4 (Auditoría 33): En /pagos/stripe/ordenes/{id}/confirmar, datos incongruentes rechazan con 400.

    Verifica rechazo estricto si:
    1. El PaymentIntent tiene un ID ajeno.
    2. La moneda devuelta no es USD.
    3. Los centavos no coinciden exactamente con op.centavos_usd.
    4. La metadata de empresa_id no coincide con la orden.
    5. La metadata de venta_id / pedido_id no coincide con la orden.
    En todos los casos la orden NO debe transicionar a CAPTURADO.
    """
    fake = configurar_fake_stripe
    http.usar(escenario.usuario_admin_a)

    # 1. Crear Venta y OrdenPago en PENDIENTE por 100 BOB (1429 centavos USD aprox)
    venta_id = uuid.uuid4()
    orden_id = uuid.uuid4()
    pi_ref = f"pi_test_incongruente_{uuid.uuid4().hex[:8]}"
    ahora = datetime.now(timezone.utc)

    async with fabrica_sesiones() as db:
        v = Venta(
            id=venta_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-ORD-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=ahora,
        )
        db.add(v)
        await db.flush()

        op = OrdenPago(
            id=orden_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=venta_id,
            clave_externa=pi_ref,
            referencia_externa=pi_ref,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            monto_usd=Decimal("14.29"),
            centavos_usd=1429,
            creada_en=ahora,
            actualizada_en=ahora,
        )
        db.add(op)
        await db.commit()

    # Caso A: Moneda distinta de USD (ej. "eur")
    fake.intenciones[pi_ref] = fake.crear_o_reutilizar_intencion  # limpiar
    from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import IntencionPago
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=1429,
        moneda="eur",  # Adulterado
        estado="SUCCEEDED",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(venta_id)},
    )
    resp_moneda = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_moneda.status_code == 400, f"Esperado 400 por moneda pero dio {resp_moneda.status_code}: {resp_moneda.text}"
    assert "moneda" in resp_moneda.json()["detail"].lower() or "no coinciden" in resp_moneda.json()["detail"].lower()

    # Verificar que NO transicionó a CAPTURADO
    async with fabrica_sesiones() as db:
        op_check = await db.get(OrdenPago, orden_id)
        assert op_check.estado == "PENDIENTE"

    # Caso B: Centavos adulterados (ej. 100 centavos en vez de 1429)
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=100,  # Adulterado
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(venta_id)},
    )
    resp_centavos = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_centavos.status_code == 400, f"Esperado 400 por centavos pero dio {resp_centavos.status_code}: {resp_centavos.text}"
    assert "monto" in resp_centavos.json()["detail"].lower() or "centavos" in resp_centavos.json()["detail"].lower() or "no coinciden" in resp_centavos.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        op_check = await db.get(OrdenPago, orden_id)
        assert op_check.estado == "PENDIENTE"

    # Caso C: Metadata empresa_id errónea o de otra empresa
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=1429,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"empresa_id": str(uuid.uuid4()), "venta_id": str(venta_id)},  # Empresa ajena
    )
    resp_empresa = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_empresa.status_code == 400, f"Esperado 400 por empresa pero dio {resp_empresa.status_code}: {resp_empresa.text}"
    assert "empresa" in resp_empresa.json()["detail"].lower() or "no coinciden" in resp_empresa.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        op_check = await db.get(OrdenPago, orden_id)
        assert op_check.estado == "PENDIENTE"

    # Caso D: Metadata venta_id errónea
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=1429,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(uuid.uuid4())},  # Venta ajena
    )
    resp_venta = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_venta.status_code == 400, f"Esperado 400 por venta_id pero dio {resp_venta.status_code}: {resp_venta.text}"
    assert "venta" in resp_venta.json()["detail"].lower() or "no coinciden" in resp_venta.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        op_check = await db.get(OrdenPago, orden_id)
        assert op_check.estado == "PENDIENTE"

    # Sub-caso B: Falta metadata venta_id en contexto VENTA
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=1429,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"empresa_id": str(escenario.empresa_a_id)},  # NO tiene venta_id
    )

    resp_no_venta = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_no_venta.status_code == 400, f"Esperado 400 por falta de venta_id pero devolvió {resp_no_venta.status_code}: {resp_no_venta.text}"

    async with fabrica_sesiones() as db:
        op_check = await db.get(OrdenPago, orden_id)
        assert op_check.estado == "PENDIENTE"


async def test_h3_cancelar_orden_libera_stock_digital_y_kardex(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """H3: Cancelación exitosa en pasarela libera stock comprometido_digital y genera Kardex LIBERACION_DIGITAL."""
    fake = configurar_fake_stripe
    http.usar(escenario.usuario_admin_a)
    ahora = datetime.now(timezone.utc)

    from backend.app.core.modules.inventario.models import MovimientoInventario
    from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import IntencionPago
    from backend.app.core.modules.ventas_pagos.models import DetalleVenta

    venta_id = uuid.uuid4()
    orden_id = uuid.uuid4()
    det_id = uuid.uuid4()
    pi_ref = f"pi_test_lib_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv = (await db.execute(stmt_inv)).scalars().first()
        inv.disponible = 10
        inv.comprometido_digital = 2
        await db.flush()

        v = Venta(
            id=venta_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-LIB-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=ahora,
        )
        db.add(v)
        await db.flush()

        det = DetalleVenta(
            id=det_id,
            venta_id=venta_id,
            variante_id=escenario.variante_a_id,
            cantidad=2,
            precio_unitario=Decimal("50.00"),
            descuento=Decimal("0.00"),
            costo_promedio=Decimal("20.00"),
        )
        db.add(det)
        await db.flush()

        op = OrdenPago(
            id=orden_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=venta_id,
            clave_externa=pi_ref,
            referencia_externa=pi_ref,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            monto_usd=Decimal("14.29"),
            centavos_usd=1429,
            creada_en=ahora,
            actualizada_en=ahora,
        )
        db.add(op)
        await db.commit()

    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=1429,
        moneda="usd",
        estado="REQUIRES_PAYMENT",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(venta_id)},
    )

    resp = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_id}/cancelar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200, f"Error: {resp.text}"
    assert resp.json()["estado"] == "CANCELADO"

    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_id)
        assert op_db.estado == "CANCELADO"
        v_db = await db.get(Venta, venta_id)
        assert v_db.estado == "CANCELADA"

        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_db = (await db.execute(stmt_inv)).scalars().first()
        assert inv_db.comprometido_digital == 0, f"Comprometido digital debió ser 0 pero es {inv_db.comprometido_digital}"
        assert inv_db.disponible == 12, f"Disponible debió volver a 12 pero es {inv_db.disponible}"

        stmt_mov = select(MovimientoInventario).where(
            MovimientoInventario.referencia_tipo == "VENTA",
            MovimientoInventario.referencia_id == venta_id,
            MovimientoInventario.tipo == "LIBERACION_DIGITAL",
        )
        mov = (await db.execute(stmt_mov)).scalars().first()
        assert mov is not None, "Debió registrarse Kardex LIBERACION_DIGITAL"
        assert mov.cantidad == 2


@pytest.mark.asyncio


async def test_h4_recuperar_orden_activa_caja(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """H4: Endpoint GET /api/v1/pagos/stripe/ordenes/activa-caja recupera la orden activa del cajero
    y refresca el client_secret de la pasarela para la PWA.
    """
    fake = configurar_fake_stripe
    http.usar(escenario.usuario_admin_a)
    ahora = datetime.now(timezone.utc)

    from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import IntencionPago

    # 1. Cuando no hay orden activa, devuelve 200 con null
    resp_vacia = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_vacia.status_code == 200
    assert resp_vacia.json() is None

    # 2. Con orden activa PENDIENTE
    venta_id = uuid.uuid4()
    orden_id = uuid.uuid4()
    pi_ref = f"pi_test_activa_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        v = Venta(
            id=venta_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-ACT-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=ahora,
        )
        db.add(v)
        await db.flush()

        op = OrdenPago(
            id=orden_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=venta_id,
            clave_externa=pi_ref,
            referencia_externa=pi_ref,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            monto_usd=Decimal("14.29"),
            centavos_usd=1429,
            creada_en=ahora,
            actualizada_en=ahora,
        )
        db.add(op)
        await db.commit()

    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=1429,
        moneda="usd",
        estado="REQUIRES_PAYMENT",
        client_secret="pi_secret_fresco_recuperado_123",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(venta_id)},
    )

    resp_act = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_act.status_code == 200, f"Error: {resp_act.text}"
    datos_act = resp_act.json()
    assert datos_act["orden_pago_id"] == str(orden_id)
    assert datos_act["estado"] == "PENDIENTE"
    assert datos_act["client_secret"] == "pi_secret_fresco_recuperado_123"

    # 3. Con orden en CAPTURADO
    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_id)
        op_db.estado = "CAPTURADO"
        await db.commit()

    resp_cap = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_cap.status_code == 200
    assert resp_cap.json()["estado"] == "CAPTURADO"


@pytest.mark.asyncio


async def test_h4_expiracion_segura_ventas_stripe(
    escenario, fabrica_sesiones, configurar_fake_stripe
):
    """H4: Tarea de expiración segura consulta Stripe:
    - Si está SUCCEEDED: sincroniza a CAPTURADO y NO libera stock.
    - Si está REQUIRES_PAYMENT / CANCELED: cancela en pasarela, cancela venta y libera comprometido_digital.
    """
    fake = configurar_fake_stripe
    from backend.app.core.tareas import expirar_ventas_stripe_segura
    from backend.app.core.modules.inventario.models import MovimientoInventario
    from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import IntencionPago
    from backend.app.core.modules.ventas_pagos.models import DetalleVenta

    ahora = datetime.now(timezone.utc)
    vencido = ahora - timedelta(minutes=15)

    # --- Caso A: Venta vencida pero Stripe SUCCEEDED (no liberar stock) ---
    v_succ_id = uuid.uuid4()
    op_succ_id = uuid.uuid4()
    det_succ_id = uuid.uuid4()
    pi_succ_ref = f"pi_test_expsucc_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv = (await db.execute(stmt_inv)).scalars().first()
        inv.disponible = 10
        inv.comprometido_digital = 2
        await db.flush()

        v_succ = Venta(
            id=v_succ_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-EXPSUCC-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=vencido - timedelta(minutes=5),
            expira_en=vencido,
        )
        db.add(v_succ)
        await db.flush()

        det_succ = DetalleVenta(
            id=det_succ_id,
            venta_id=v_succ_id,
            variante_id=escenario.variante_a_id,
            cantidad=2,
            precio_unitario=Decimal("50.00"),
            descuento=Decimal("0.00"),
            costo_promedio=Decimal("20.00"),
        )
        db.add(det_succ)
        await db.flush()

        op_succ = OrdenPago(
            id=op_succ_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=v_succ_id,
            clave_externa=pi_succ_ref,
            referencia_externa=pi_succ_ref,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            monto_usd=Decimal("14.29"),
            centavos_usd=1429,
            creada_en=vencido,
            actualizada_en=vencido,
        )
        db.add(op_succ)
        await db.commit()

    fake.intenciones[pi_succ_ref] = IntencionPago(
        id=pi_succ_ref,
        venta_id=str(v_succ_id),
        monto_centavos=1429,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(v_succ_id)},
    )

    async with fabrica_sesiones() as db:
        res = await expirar_ventas_stripe_segura(db=db, ahora=ahora, empresa_id=escenario.empresa_a_id)

    async with fabrica_sesiones() as db:
        v_succ_check = await db.get(Venta, v_succ_id)
        assert v_succ_check.estado != "CANCELADA", "La venta con fondos en Stripe no debe ser cancelada"
        op_succ_check = await db.get(OrdenPago, op_succ_id)
        assert op_succ_check.estado == "CAPTURADO", f"La orden debió sincronizarse a CAPTURADO pero quedó en {op_succ_check.estado}"

        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_check = (await db.execute(stmt_inv)).scalars().first()
        assert inv_check.comprometido_digital == 2, "El stock de cobro exitoso no debe liberarse"
        assert inv_check.disponible == 10

    # --- Caso B: Venta vencida con Stripe pendiente (cancelar y liberar stock) ---
    v_canc_id = uuid.uuid4()
    op_canc_id = uuid.uuid4()
    det_canc_id = uuid.uuid4()
    pi_canc_ref = f"pi_test_expcanc_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        v_canc = Venta(
            id=v_canc_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-EXPCANC-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=vencido - timedelta(minutes=5),
            expira_en=vencido,
        )
        db.add(v_canc)
        await db.flush()

        det_canc = DetalleVenta(
            id=det_canc_id,
            venta_id=v_canc_id,
            variante_id=escenario.variante_a_id,
            cantidad=2,
            precio_unitario=Decimal("50.00"),
            descuento=Decimal("0.00"),
            costo_promedio=Decimal("20.00"),
        )
        db.add(det_canc)
        await db.flush()

        op_canc = OrdenPago(
            id=op_canc_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=v_canc_id,
            clave_externa=pi_canc_ref,
            referencia_externa=pi_canc_ref,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            monto_usd=Decimal("14.29"),
            centavos_usd=1429,
            creada_en=vencido,
            actualizada_en=vencido,
        )
        db.add(op_canc)
        await db.commit()

    fake.intenciones[pi_canc_ref] = IntencionPago(
        id=pi_canc_ref,
        venta_id=str(v_canc_id),
        monto_centavos=1429,
        moneda="usd",
        estado="REQUIRES_PAYMENT",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(v_canc_id)},
    )

    async with fabrica_sesiones() as db:
        res2 = await expirar_ventas_stripe_segura(db=db, ahora=ahora, empresa_id=escenario.empresa_a_id)

    async with fabrica_sesiones() as db:
        v_canc_check = await db.get(Venta, v_canc_id)
        assert v_canc_check.estado == "CANCELADA", "La venta impaga vencida debe ser CANCELADA"
        op_canc_check = await db.get(OrdenPago, op_canc_id)
        assert op_canc_check.estado == "CANCELADO", "La orden impaga vencida debe ser CANCELADO"

        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_canc_check = (await db.execute(stmt_inv)).scalars().first()
        assert inv_canc_check.comprometido_digital == 0, "El stock comprometido debe liberarse"
        assert inv_canc_check.disponible == 12, "El stock disponible debe restaurarse"


async def test_contraejemplo_cancelar_orden_pago_pendiente_y_bloqueo_si_capturado(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """Contraejemplo 5 (Auditoría 33): Cancelación segura en POST /pagos/stripe/ordenes/{id}/cancelar.

    1. Orden PENDIENTE pasa a CANCELADO y su Venta asociada pasa a CANCELADA.
    2. Orden CAPTURADO rechaza la cancelación con HTTP 409 Conflict para no ocultar cobros reales.
    """
    fake = configurar_fake_stripe
    http.usar(escenario.usuario_admin_a)
    ahora = datetime.now(timezone.utc)

    # 1. Crear Orden en PENDIENTE con Venta en PENDIENTE_PAGO
    venta_id = uuid.uuid4()
    orden_id = uuid.uuid4()
    pi_ref = f"pi_test_cancel_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        v = Venta(
            id=venta_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-CAN-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=ahora,
        )
        db.add(v)
        await db.flush()

        op = OrdenPago(
            id=orden_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=venta_id,
            clave_externa=pi_ref,
            referencia_externa=pi_ref,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            monto_usd=Decimal("14.29"),
            centavos_usd=1429,
            creada_en=ahora,
            actualizada_en=ahora,
        )
        db.add(op)
        await db.commit()

    from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import IntencionPago
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=1429,
        moneda="usd",
        estado="REQUIRES_PAYMENT",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(venta_id)},
    )

    # Cancelar orden en PENDIENTE
    resp_canc = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_id}/cancelar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_canc.status_code == 200, f"Esperado 200 pero respondió {resp_canc.status_code}: {resp_canc.text}"
    assert resp_canc.json()["estado"] == "CANCELADO"

    # Verificar en BD que la orden es CANCELADO y la venta es CANCELADA
    async with fabrica_sesiones() as db:
        op_db = await db.get(OrdenPago, orden_id)
        assert op_db.estado == "CANCELADO"
        v_db = await db.get(Venta, venta_id)
        assert v_db.estado == "CANCELADA"

    # 2. Ahora probar sobre una orden en CAPTURADO
    orden_cap_id = uuid.uuid4()
    venta_cap_id = uuid.uuid4()
    pi_cap_ref = f"pi_test_cap_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        v_cap = Venta(
            id=venta_cap_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-CAP-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=ahora,
        )
        db.add(v_cap)
        await db.flush()

        op_cap = OrdenPago(
            id=orden_cap_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=venta_cap_id,
            clave_externa=pi_cap_ref,
            referencia_externa=pi_cap_ref,
            estado="CAPTURADO",
            monto_bob=Decimal("100.00"),
            monto_usd=Decimal("14.29"),
            centavos_usd=1429,
            creada_en=ahora,
            actualizada_en=ahora,
        )
        db.add(op_cap)
        await db.commit()

    resp_block = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_cap_id}/cancelar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    # Debe ser 409 Conflict
    assert resp_block.status_code == 409, f"Esperado 409 pero respondió {resp_block.status_code}: {resp_block.text}"
    assert "fondos capturados" in resp_block.json()["detail"].lower() or "no se puede cancelar" in resp_block.json()["detail"].lower()

    # Comprobar que sigue en CAPTURADO
    async with fabrica_sesiones() as db:
        op_check = await db.get(OrdenPago, orden_cap_id)
        assert op_check.estado == "CAPTURADO"


# =============================================================================
# 6. CONTRAEJEMPLOS P0/P1 — CANCELACIÓN HONESTA Y VALIDACIÓN DE METADATA (H3, H4)
# =============================================================================

@pytest.mark.asyncio


async def test_contraejemplo_p0_cancelar_orden_gateway_excepcion_o_succeeded(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P0 (H3): Al llamar a cancelar_orden_pago:
    1. Si el gateway lanza excepción (timeout / error de red), NO debe fabricar éxito (200)
       ni marcar CANCELADO/CANCELADA localmente, sino preservar PENDIENTE y responder 502 BAD_GATEWAY.
    2. Si el PaymentIntent ya está SUCCEEDED en pasarela, NO debe cancelarlo ni liberar stock,
       sino sincronizar a CAPTURADO y rechazar con 409 CONFLICT.
    """
    fake = configurar_fake_stripe
    http.usar(escenario.usuario_admin_a)
    ahora = datetime.now(timezone.utc)

    from backend.app.core.modules.inventario.models import MovimientoInventario
    from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import IntencionPago
    from backend.app.core.modules.ventas_pagos.models import DetalleVenta

    # --- CASO 1: Fallo de red / timeout en pasarela al cancelar ---
    venta_err_id = uuid.uuid4()
    orden_err_id = uuid.uuid4()
    det_err_id = uuid.uuid4()
    pi_err_ref = f"pi_test_err_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        # Asegurar stock inicial y compromiso digital
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv = (await db.execute(stmt_inv)).scalars().first()
        inv.disponible = 10
        inv.comprometido_digital = 2
        await db.flush()

        v_err = Venta(
            id=venta_err_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-ERR-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=ahora,
        )
        db.add(v_err)
        await db.flush()

        det = DetalleVenta(
            id=det_err_id,
            venta_id=venta_err_id,
            variante_id=escenario.variante_a_id,
            cantidad=2,
            precio_unitario=Decimal("50.00"),
            descuento=Decimal("0.00"),
            costo_promedio=Decimal("20.00"),
        )
        db.add(det)
        await db.flush()

        op_err = OrdenPago(
            id=orden_err_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=venta_err_id,
            clave_externa=pi_err_ref,
            referencia_externa=pi_err_ref,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            monto_usd=Decimal("14.29"),
            centavos_usd=1429,
            creada_en=ahora,
            actualizada_en=ahora,
        )
        db.add(op_err)
        await db.commit()

    fake.intenciones[pi_err_ref] = IntencionPago(
        id=pi_err_ref,
        venta_id=str(venta_err_id),
        monto_centavos=1429,
        moneda="usd",
        estado="REQUIRES_PAYMENT",
    )
    # Simular fallo de pasarela
    fake.fallos_temporales_restantes = 1

    resp_err = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_err_id}/cancelar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_err.status_code == 502, f"Esperado 502 BAD_GATEWAY por fallo de pasarela pero devolvió {resp_err.status_code}: {resp_err.text}"

    # Verificar que el estado en BD sigue siendo PENDIENTE y stock NO fue liberado
    async with fabrica_sesiones() as db:
        op_check = await db.get(OrdenPago, orden_err_id)
        assert op_check.estado == "PENDIENTE", f"La orden debió quedar PENDIENTE pero quedó en {op_check.estado}"
        v_check = await db.get(Venta, venta_err_id)
        assert v_check.estado == "PENDIENTE_PAGO", f"La venta debió quedar PENDIENTE_PAGO pero quedó en {v_check.estado}"
        stmt_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_check = (await db.execute(stmt_inv)).scalars().first()
        assert inv_check.comprometido_digital == 2, "El stock comprometido no debió ser liberado en incertidumbre"
        assert inv_check.disponible == 10

    # --- CASO 2: PaymentIntent ya está SUCCEEDED en Stripe ---
    venta_succ_id = uuid.uuid4()
    orden_succ_id = uuid.uuid4()
    pi_succ_ref = f"pi_test_succ_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        v_succ = Venta(
            id=venta_succ_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-SUCC-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=ahora,
        )
        db.add(v_succ)
        await db.flush()

        op_succ = OrdenPago(
            id=orden_succ_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=venta_succ_id,
            clave_externa=pi_succ_ref,
            referencia_externa=pi_succ_ref,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            monto_usd=Decimal("14.29"),
            centavos_usd=1429,
            creada_en=ahora,
            actualizada_en=ahora,
        )
        db.add(op_succ)
        await db.commit()

    fake.intenciones[pi_succ_ref] = IntencionPago(
        id=pi_succ_ref,
        venta_id=str(venta_succ_id),
        monto_centavos=1429,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"empresa_id": str(escenario.empresa_a_id), "venta_id": str(venta_succ_id)},
    )

    resp_succ = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_succ_id}/cancelar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_succ.status_code == 409, f"Esperado 409 CONFLICT por PI ya capturado pero devolvió {resp_succ.status_code}: {resp_succ.text}"

    async with fabrica_sesiones() as db:
        op_succ_db = await db.get(OrdenPago, orden_succ_id)
        assert op_succ_db.estado == "CAPTURADO", f"La orden debió sincronizarse a CAPTURADO pero quedó en {op_succ_db.estado}"
        v_succ_db = await db.get(Venta, venta_succ_id)
        assert v_succ_db.estado != "CANCELADA", "La venta no debe ser cancelada si los fondos fueron capturados"


@pytest.mark.asyncio


async def test_contraejemplo_p1_confirmar_orden_metadata_incompleta_rechaza_400(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """P1 (H4): En confirmar_orden_pago (/ordenes/{id}/confirmar), un PaymentIntent sin metadata
    empresa_id o sin venta_id (en contexto VENTA) DEBE ser rechazado estrictamente con 400 BAD REQUEST.
    """
    fake = configurar_fake_stripe
    http.usar(escenario.usuario_admin_a)
    ahora = datetime.now(timezone.utc)

    from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import IntencionPago

    venta_id = uuid.uuid4()
    orden_id = uuid.uuid4()
    pi_ref = f"pi_test_nometa_{uuid.uuid4().hex[:8]}"

    async with fabrica_sesiones() as db:
        v = Venta(
            id=venta_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-NOMETA-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=ahora,
        )
        db.add(v)
        await db.flush()

        op = OrdenPago(
            id=orden_id,
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=venta_id,
            clave_externa=pi_ref,
            referencia_externa=pi_ref,
            estado="PENDIENTE",
            monto_bob=Decimal("100.00"),
            monto_usd=Decimal("14.29"),
            centavos_usd=1429,
            creada_en=ahora,
            actualizada_en=ahora,
        )
        db.add(op)
        await db.commit()

    # Sub-caso A: Falta metadata empresa_id (o es None)
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=1429,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"venta_id": str(venta_id)},  # NO tiene empresa_id
    )

    resp_no_empresa = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_no_empresa.status_code == 400, f"Esperado 400 por falta de empresa_id pero devolvió {resp_no_empresa.status_code}: {resp_no_empresa.text}"

    async with fabrica_sesiones() as db:
        op_check = await db.get(OrdenPago, orden_id)
        assert op_check.estado == "PENDIENTE"

    # Sub-caso B: Falta metadata venta_id en contexto VENTA
    fake.intenciones[pi_ref] = IntencionPago(
        id=pi_ref,
        venta_id=str(venta_id),
        monto_centavos=1429,
        moneda="usd",
        estado="SUCCEEDED",
        metadata={"empresa_id": str(escenario.empresa_a_id)},  # NO tiene venta_id
    )

    resp_no_venta = await http.cliente.post(
        f"/api/v1/pagos/stripe/ordenes/{orden_id}/confirmar",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_no_venta.status_code == 400, f"Esperado 400 por falta de venta_id pero devolvió {resp_no_venta.status_code}: {resp_no_venta.text}"

    async with fabrica_sesiones() as db:
        op_check = await db.get(OrdenPago, orden_id)
        assert op_check.estado == "PENDIENTE"
