"""Corrección 5 — Stripe Test Mode estricto + reintento (FAILED vs CANCELED)."""
import json
import uuid

from httpx import AsyncClient

from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw
from backend.app.core.config import settings
from tests.helpers_ciclo2 import crear_cliente, crear_variante_con_stock, sucursal_semilla
from tests.helpers_ciclo3 import (
    FakeStripe, agregar_linea, clave, contar_kardex, hacer_checkout, stock_en,
)


def _ctx_stripe(monkeypatch, fake: FakeStripe):
    monkeypatch.setattr(settings, "STRIPE_ENABLED", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_falsa")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_prueba")
    fake.instalar()


def _webhook(pi_id: str, tipo: str, livemode: bool = False) -> tuple[bytes, dict]:
    evento = {"id": f"evt_{uuid.uuid4().hex[:8]}", "type": tipo,
              "livemode": livemode, "data": {"object": {"id": pi_id}}}
    return json.dumps(evento).encode(), evento


async def test_rechazo_reutiliza_y_cancelado_crea_nuevo(cliente_http: AsyncClient, monkeypatch):
    fake = FakeStripe()
    _ctx_stripe(monkeypatch, fake)
    try:
        async with await crear_cliente("stm1") as cli:
            suc = await sucursal_semilla(cliente_http)
            var = await crear_variante_con_stock(cliente_http, suc, 6, tag="stm1")
            await agregar_linea(cli, var["variante_id"], 1)
            out = await hacer_checkout(cli, suc, "WEB", "RECOJO")
            pi1 = (await cli.client.post(
                "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
                headers={"Idempotency-Key": clave()})).json()["payment_intent_id"]
            # FAILED -> reintento reutiliza el mismo PI.
            cuerpo, _ = _webhook(pi1, "payment_intent.payment_failed")
            r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=cuerpo,
                                      headers={"Stripe-Signature": gw.firmar_prueba(cuerpo, "whsec_prueba")})
            assert r.status_code == 200, r.text
            pi_re = (await cli.client.post(
                "/api/v1/pagos/stripe/intenciones/reintento", json={"venta_id": out["venta_id"]},
                headers={"Idempotency-Key": clave()})).json()["payment_intent_id"]
            assert pi_re == pi1
            # CANCELED (PI marcado cancelado en Stripe) -> nueva intención.
            fake.gw.marcar(pi1, "CANCELED")
            cuerpo2, _ = _webhook(pi1, "payment_intent.canceled")
            r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=cuerpo2,
                                      headers={"Stripe-Signature": gw.firmar_prueba(cuerpo2, "whsec_prueba")})
            assert r.status_code == 200, r.text
            pi2 = (await cli.client.post(
                "/api/v1/pagos/stripe/intenciones/reintento", json={"venta_id": out["venta_id"]},
                headers={"Idempotency-Key": clave()})).json()["payment_intent_id"]
            assert pi2 != pi1 and pi2.startswith("pi_test_")
            # Webhook tardío de la intención reemplazada: sin efectos.
            estado_antes = (await cli.client.get(f"/api/v1/pagos/stripe/estado/{out['venta_id']}")).json()
            cuerpo_viejo, _ = _webhook(pi1, "payment_intent.succeeded")
            r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=cuerpo_viejo,
                                      headers={"Stripe-Signature": gw.firmar_prueba(cuerpo_viejo, "whsec_prueba")})
            assert r.status_code in (200, 404), r.text
            estado_desp = (await cli.client.get(f"/api/v1/pagos/stripe/estado/{out['venta_id']}")).json()
            assert estado_desp["estado_venta"] == estado_antes["estado_venta"]
            assert await contar_kardex(out["venta_id"], "VENTA_DIGITAL") == 0
            # Solo la vigente confirma: webhook de pi2 aprueba.
            cuerpo_ok, _ = _webhook(pi2, "payment_intent.succeeded")
            r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=cuerpo_ok,
                                      headers={"Stripe-Signature": gw.firmar_prueba(cuerpo_ok, "whsec_prueba")})
            assert r.status_code == 200 and r.json()["estado"] == "APROBADO", r.text
            assert await contar_kardex(out["venta_id"], "VENTA_DIGITAL") == 1
    finally:
        fake.desinstalar()


async def test_clave_live_rechazada(cliente_http: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_ENABLED", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_falsa")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_prueba")
    async with await crear_cliente("stml") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 3, tag="stml")
        await agregar_linea(cli, var["variante_id"], 1)
        out = await hacer_checkout(cli, suc, "WEB", "RECOJO")
        r = await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 503, r.text
        assert "sk_live_falsa" not in r.text and "sk_live" not in r.text.replace("STRIPE_MODO", "")


async def test_evento_livemode_true_rechazado_sin_efectos(cliente_http: AsyncClient, monkeypatch):
    fake = FakeStripe()
    _ctx_stripe(monkeypatch, fake)
    try:
        async with await crear_cliente("stlv") as cli:
            suc = await sucursal_semilla(cliente_http)
            var = await crear_variante_con_stock(cliente_http, suc, 4, tag="stlv")
            await agregar_linea(cli, var["variante_id"], 1)
            out = await hacer_checkout(cli, suc, "WEB", "RECOJO")
            pi = (await cli.client.post(
                "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
                headers={"Idempotency-Key": clave()})).json()["payment_intent_id"]
            cuerpo, _ = _webhook(pi, "payment_intent.succeeded", livemode=True)
            r = await cli.client.post("/api/v1/pagos/stripe/webhook", content=cuerpo,
                                      headers={"Stripe-Signature": gw.firmar_prueba(cuerpo, "whsec_prueba")})
            assert r.status_code == 400, r.text
            estado = (await cli.client.get(f"/api/v1/pagos/stripe/estado/{out['venta_id']}")).json()
            assert estado["estado_venta"] == "PENDIENTE_PAGO" and estado["estado_pago"] != "APROBADO"
            assert await contar_kardex(out["venta_id"], "VENTA_DIGITAL") == 0
            assert await stock_en(suc, var["variante_id"]) == (3, 1)
    finally:
        fake.desinstalar()


async def test_sin_llamadas_reales():
    import inspect
    from backend.app.core.modules.ventas_pagos.services import stripe_service as ss
    src = inspect.getsource(ss.StripeService.crearIntencion)
    assert "exigir_test_mode" in src
    src2 = inspect.getsource(ss.StripeService.confirmarWebhook)
    assert "livemode" in src2


async def test_evento_account_update_se_ignora_con_200(cliente_http: AsyncClient, monkeypatch):
    fake = FakeStripe()
    _ctx_stripe(monkeypatch, fake)
    try:
        evento = {
            "id": f"evt_{uuid.uuid4().hex[:8]}",
            "type": "account.updated",
            "livemode": False,
            "data": {"object": {"id": "acct_prueba", "object": "account"}},
        }
        cuerpo = json.dumps(evento).encode()
        respuesta = await cliente_http.post(
            "/api/v1/pagos/stripe/webhook",
            content=cuerpo,
            headers={"Stripe-Signature": gw.firmar_prueba(cuerpo, "whsec_prueba")},
        )
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json() == {"evento": "account.updated", "estado": "IGNORADO"}
    finally:
        fake.desinstalar()
