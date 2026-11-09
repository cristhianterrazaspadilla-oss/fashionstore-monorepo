"""CU15 — Stripe Test Mode: intenciones, webhook firmado, reintento y expiración."""
import json
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw
from backend.app.core.config import settings
from tests.helpers_ciclo2 import (
    crear_cliente, crear_sucursal, crear_variante_con_stock, sucursal_semilla,
)
from tests.helpers_ciclo3 import (
    FakeStripe, agregar_linea, clave, contar_kardex, forzar_vencimiento_venta,
    hacer_checkout, stock_en,
)


@pytest.fixture()
def stripe_fake(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_ENABLED", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_falsa")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_prueba")
    monkeypatch.setattr(settings, "STRIPE_CURRENCY", "usd")
    fake = FakeStripe()
    fake.instalar()
    yield fake
    fake.desinstalar()


async def _checkout(cli, suc, var, cantidad=1, modalidad="RECOJO", **kw):
    await agregar_linea(cli, var["variante_id"], cantidad)
    return await hacer_checkout(cli, suc, "WEB", modalidad, **kw)


def _webhook(pi_id: str, tipo: str) -> tuple[bytes, dict]:
    evento = {"id": f"evt_{uuid.uuid4().hex[:8]}", "type": tipo,
              "data": {"object": {"id": pi_id}}}
    cuerpo = json.dumps(evento).encode()
    return cuerpo, evento


async def test_stripe_deshabilitado_503_y_modulos_sanos(cliente_http: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_ENABLED", False)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")
    async with await crear_cliente("s15d") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 3, tag="s15d")
        out = await _checkout(cli, suc, var)
        r = await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 503, r.text
        assert r.json()["detail"]["codigo"] == "STRIPE_DESHABILITADO"
        # Módulos no relacionados siguen sanos.
        assert (await cli.client.get("/api/v1/carritos/mio", params={"canal": "WEB"})).status_code == 200


async def test_pago_aprobado_consume_stock_y_kardex_unico(cliente_http: AsyncClient, stripe_fake):
    async with await crear_cliente("s15a") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 5, tag="s15a",
                                             precio="100.00", costo="40.00")
        out = await _checkout(cli, suc, var, 2)
        intencion_key = clave()
        inten = (await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
            headers={"Idempotency-Key": intencion_key})).json()
        assert inten["payment_intent_id"].startswith("pi_test_"), inten
        assert inten["moneda"] == "usd"
        assert Decimal(str(inten["monto"])) == Decimal("28.74")
        assert stripe_fake.gw.intenciones[inten["payment_intent_id"]].monto_centavos == 2874
        misma = (await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
            headers={"Idempotency-Key": intencion_key})).json()
        assert misma["payment_intent_id"] == inten["payment_intent_id"]
        assert misma["client_secret"] == inten["client_secret"]
        # Reintento de intención reutiliza el mismo PaymentIntent.
        inten2 = (await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
            headers={"Idempotency-Key": clave()})).json()
        assert inten2["payment_intent_id"] == inten["payment_intent_id"]
        # Webhook aprobado (firmado con cuerpo crudo).
        cuerpo, evento = _webhook(inten["payment_intent_id"], "payment_intent.succeeded")
        firma = gw.firmar_prueba(cuerpo, "whsec_prueba")
        r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=cuerpo,
                                  headers={"Stripe-Signature": firma})
        assert r.status_code == 200 and r.json()["estado"] == "APROBADO", r.text
        # Venta pagada, compromiso convertido en consumo definitivo.
        estado = (await cli.client.get(
            f"/api/v1/pagos/stripe/estado/{out['venta_id']}")).json()
        assert estado["estado_venta"] == "PAGADA" and estado["estado_pago"] == "APROBADO", estado
        assert await stock_en(suc, var["variante_id"]) == (3, 0)
        assert await contar_kardex(out["venta_id"], "VENTA_DIGITAL") == 1
        # Webhook duplicado: idempotente, sin duplicar Kardex.
        r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=cuerpo,
                                  headers={"Stripe-Signature": firma})
        assert r.status_code == 200
        assert await contar_kardex(out["venta_id"], "VENTA_DIGITAL") == 1


async def test_consulta_concilia_pago_capturado_con_importe_usd(cliente_http: AsyncClient, stripe_fake):
    async with await crear_cliente("s15consulta") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 2, tag="s15consulta",
                                             precio="100.00", costo="40.00")
        out = await _checkout(cli, suc, var)
        respuesta = await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
            headers={"Idempotency-Key": clave()})
        assert respuesta.status_code == 201, respuesta.text
        pi_id = respuesta.json()["payment_intent_id"]
        stripe_fake.gw.intenciones[pi_id].estado = "SUCCEEDED"
        estado = await cli.client.get(f"/api/v1/pagos/stripe/estado/{out['venta_id']}")
        assert estado.status_code == 200, estado.text
        assert estado.json()["estado_venta"] == "PAGADA"
        assert estado.json()["estado_pago"] == "APROBADO"
        assert await contar_kardex(out["venta_id"], "VENTA_DIGITAL") == 1


async def test_captura_con_importe_usd_incorrecto_no_confirma_venta(cliente_http: AsyncClient, stripe_fake):
    async with await crear_cliente("s15importe") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 2, tag="s15importe",
                                             precio="100.00", costo="40.00")
        out = await _checkout(cli, suc, var)
        respuesta = await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
            headers={"Idempotency-Key": clave()})
        assert respuesta.status_code == 201, respuesta.text
        pi_id = respuesta.json()["payment_intent_id"]
        stripe_fake.gw.intenciones[pi_id].monto_centavos = 10000
        stripe_fake.gw.intenciones[pi_id].estado = "SUCCEEDED"
        estado = await cli.client.get(f"/api/v1/pagos/stripe/estado/{out['venta_id']}")
        assert estado.status_code == 409
        cuerpo, _ = _webhook(pi_id, "payment_intent.succeeded")
        webhook = await cli.client.post(
            "/api/v1/pagos/stripe/webhook", content=cuerpo,
            headers={"Stripe-Signature": gw.firmar_prueba(cuerpo, "whsec_prueba")})
        assert webhook.status_code == 409
        assert await contar_kardex(out["venta_id"], "VENTA_DIGITAL") == 0


async def test_pago_rechazado_mantiene_ventana_sin_consumo(cliente_http: AsyncClient, stripe_fake):
    async with await crear_cliente("s15r") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 4, tag="s15r")
        out = await _checkout(cli, suc, var, 1)
        inten = (await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
            headers={"Idempotency-Key": clave()})).json()
        cuerpo, evento = _webhook(inten["payment_intent_id"], "payment_intent.payment_failed")
        firma = gw.firmar_prueba(cuerpo, "whsec_prueba")
        r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=cuerpo,
                                  headers={"Stripe-Signature": firma})
        assert r.status_code == 200 and r.json()["estado"] == "RECHAZADO", r.text
        estado = (await cli.client.get(
            f"/api/v1/pagos/stripe/estado/{out['venta_id']}")).json()
        assert estado["estado_venta"] == "PENDIENTE_PAGO", estado
        # Sin consumo definitivo: el compromiso sigue reservado.
        assert await stock_en(suc, var["variante_id"]) == (3, 1)
        assert await contar_kardex(out["venta_id"], "VENTA_DIGITAL") == 0
        # Reintento permitido dentro de la ventana.
        r = await cli.client.post(
            "/api/v1/pagos/stripe/intenciones/reintento", json={"venta_id": out["venta_id"]},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 200, r.text


async def test_firma_invalida_400(cliente_http: AsyncClient, stripe_fake):
    async with await crear_cliente("s15f") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 2, tag="s15f")
        out = await _checkout(cli, suc, var, 1)
        cuerpo, _ = _webhook("pi_test_000001", "payment_intent.succeeded")
        r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=cuerpo,
                                  headers={"Stripe-Signature": "t=1,v1=mala"})
        assert r.status_code == 400, r.text
        r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=cuerpo)
        assert r.status_code == 400, r.text


async def test_webhook_fuera_de_orden_y_carrera_con_expirador(
    cliente_http: AsyncClient, stripe_fake,
):
    async with await crear_cliente("s15o") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 3, tag="s15o")
        # Fuera de orden: failed después de succeeded no revierte el aprobado.
        out = await _checkout(cli, suc, var, 1)
        inten = (await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
            headers={"Idempotency-Key": clave()})).json()
        pi = inten["payment_intent_id"]
        ok_c, _ = _webhook(pi, "payment_intent.succeeded")
        await cli.client.post("/api/v1/pagos/stripe/webhook", content=ok_c,
                              headers={"Stripe-Signature": gw.firmar_prueba(ok_c, "whsec_prueba")})
        bad_c, _ = _webhook(pi, "payment_intent.payment_failed")
        r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=bad_c,
                                  headers={"Stripe-Signature": gw.firmar_prueba(bad_c, "whsec_prueba")})
        assert r.status_code == 200
        estado = (await cli.client.get(f"/api/v1/pagos/stripe/estado/{out['venta_id']}")).json()
        assert estado["estado_venta"] == "PAGADA" and estado["estado_pago"] == "APROBADO", estado
        # Carrera: venta vencida + expirador primero; el webhook tardío no reabre.
        await agregar_linea(cli, var["variante_id"], 1)
        out2 = await hacer_checkout(cli, suc, "WEB", "RECOJO")
        inten2 = (await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": out2["venta_id"]},
            headers={"Idempotency-Key": clave()})).json()
        await forzar_vencimiento_venta(out2["venta_id"])
        exp = await cliente_http.post("/api/v1/pagos/stripe/expiracion/ejecutar")
        assert exp.status_code == 200 and out2["venta_id"] in exp.json()["canceladas"], exp.text
        tarde_c, _ = _webhook(inten2["payment_intent_id"], "payment_intent.succeeded")
        r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=tarde_c,
                                  headers={"Stripe-Signature": gw.firmar_prueba(tarde_c, "whsec_prueba")})
        assert r.status_code == 200
        estado2 = (await cli.client.get(
            f"/api/v1/pagos/stripe/estado/{out2['venta_id']}")).json()
        assert estado2["estado_venta"] == "CANCELADA", estado2
        assert await contar_kardex(out2["venta_id"], "VENTA_DIGITAL") == 0


async def test_expiracion_libera_una_vez_y_es_idempotente(
    cliente_http: AsyncClient, stripe_fake,
):
    async with await crear_cliente("s15e") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 5, tag="s15e")
        out = await _checkout(cli, suc, var, 2)
        assert await stock_en(suc, var["variante_id"]) == (3, 2)
        await forzar_vencimiento_venta(out["venta_id"])
        r1 = await cliente_http.post("/api/v1/pagos/stripe/expiracion/ejecutar")
        assert r1.status_code == 200, r1.text
        assert out["venta_id"] in r1.json()["canceladas"]
        assert await stock_en(suc, var["variante_id"]) == (5, 0)
        assert await contar_kardex(out["venta_id"], "LIBERACION_DIGITAL") == 1
        # Segunda ejecución: idempotente, sin duplicar liberación.
        r2 = await cliente_http.post("/api/v1/pagos/stripe/expiracion/ejecutar")
        assert r2.status_code == 200 and r2.json()["canceladas"] == []
        assert await contar_kardex(out["venta_id"], "LIBERACION_DIGITAL") == 1
        # Expiración es solo ADMIN.
        assert (await cli.client.post("/api/v1/pagos/stripe/expiracion/ejecutar")).status_code == 403


async def test_sin_llamadas_reales_a_stripe(stripe_fake):
    assert isinstance(stripe_fake.gw, gw.FakeStripeGateway)
    assert gw.obtener_gateway() is stripe_fake.gw
