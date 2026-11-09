"""CU16 — Entregas: cotización por anillos, snapshots y transiciones."""
import uuid

from httpx import AsyncClient

from tests.helpers_ciclo2 import (
    crear_cliente, crear_staff, crear_sucursal, crear_variante_con_stock,
    sucursal_semilla,
)
from tests.helpers_ciclo3 import agregar_linea, clave, hacer_checkout


async def _checkout_delivery(cli, suc, var, anillo=3, cantidad=1):
    await agregar_linea(cli, var["variante_id"], cantidad)
    return await hacer_checkout(cli, suc, "WEB", "DELIVERY",
                                direccion="Av. Banzer 4567", anillo=anillo)


async def _sucursal_datos(admin, sucursal_id: str) -> dict:
    lista = (await admin.get("/api/v1/sucursales")).json()
    return next(s for s in lista if s["id"] == sucursal_id)


async def test_cotizacion_formula_y_rango(cliente_http: AsyncClient):
    from decimal import Decimal

    admin = cliente_http
    semilla = await sucursal_semilla(admin)
    suc = await _sucursal_datos(admin, semilla)
    base = Decimal(suc["tarifa_base_delivery"])
    incr = Decimal(suc["incremento_anillo_delivery"])
    anillo_suc = suc["numero_anillo"] or suc["anillo_minimo_delivery"]
    minimo, maximo = suc["anillo_minimo_delivery"], suc["anillo_maximo_delivery"]
    destino = min(maximo, anillo_suc + 2)
    r = await admin.get("/api/v1/entregas/cotizacion",
                        params={"sucursal_id": semilla, "anillo_destino": destino})
    assert r.status_code == 200, r.text
    cot = r.json()
    esperado = (base + abs(destino - anillo_suc) * incr).quantize(Decimal("0.01"))
    assert cot["costo_entrega"] == str(esperado), cot
    assert cot["tarifa_base"] == str(base) and cot["incremento_anillo"] == str(incr), cot
    assert cot["anillo_sucursal"] == anillo_suc, cot
    # Fuera de rango -> 400 (si el máximo lo permite); sucursal inexistente -> 404.
    if maximo < 12:
        assert (await admin.get("/api/v1/entregas/cotizacion",
                                params={"sucursal_id": semilla,
                                        "anillo_destino": maximo + 1})).status_code == 400
    assert (await admin.get("/api/v1/entregas/cotizacion",
                            params={"sucursal_id": str(uuid.uuid4()),
                                    "anillo_destino": 2})).status_code == 404


async def test_pedido_congela_snapshot(cliente_http: AsyncClient):
    from decimal import Decimal

    async with await crear_cliente("e16s") as cli:
        suc = await sucursal_semilla(cliente_http)
        datos = await _sucursal_datos(cliente_http, suc)
        anillo_suc = datos["numero_anillo"] or datos["anillo_minimo_delivery"]
        destino = min(datos["anillo_maximo_delivery"], anillo_suc + 1)
        if destino == anillo_suc:
            destino = max(datos["anillo_minimo_delivery"], anillo_suc - 1)
        var = await crear_variante_con_stock(cliente_http, suc, 4, tag="e16s")
        out = await _checkout_delivery(cli, suc, var, anillo=destino)
        pedido = (await cli.client.get(f"/api/v1/entregas/{out['pedido_entrega_id']}")).json()
        assert pedido["modalidad"] == "DELIVERY" and pedido["estado"] == "SOLICITADO", pedido
        assert pedido["direccion"] == "Av. Banzer 4567" and pedido["anillo_destino"] == destino, pedido
        esperado = (Decimal(datos["tarifa_base_delivery"])
                    + abs(destino - anillo_suc) * Decimal(datos["incremento_anillo_delivery"]))
        assert pedido["costo_entrega"] == str(esperado.quantize(Decimal("0.01"))), pedido
        assert pedido["tarifa_base"] == datos["tarifa_base_delivery"], pedido
        assert pedido["anillo_sucursal"] == anillo_suc, pedido
        # Recojo congela costo 0 y código de recojo.
        await agregar_linea(cli, var["variante_id"], 1)
        out2 = await hacer_checkout(cli, suc, "WEB", "RECOJO")
        p2 = (await cli.client.get(f"/api/v1/entregas/{out2['pedido_entrega_id']}")).json()
        assert p2["costo_entrega"] == "0.00" and p2["codigo_recojo"], p2


async def test_transiciones_recojo_y_delivery(cliente_http: AsyncClient, monkeypatch):
    admin = cliente_http
    suc = await crear_sucursal(admin, tag="trk")
    enc = await crear_staff(admin, "ENCARGADO", suc, tag="trk")
    try:
        var = await crear_variante_con_stock(admin, suc, 6, tag="trk",
                                             precio="100.00", costo="40.00")
        async with await crear_cliente("trk") as cli:
            out = await _checkout_delivery(cli, suc, var, anillo=4)
            pid = out["pedido_entrega_id"]
            # Sin pagar no entra a preparación -> 409.
            r = await enc.client.patch(f"/api/v1/entregas/{pid}/estado",
                                       json={"estado": "PREPARADO"})
            assert r.status_code == 409, r.text
            # Pagar vía webhook fake para habilitar el flujo.
            from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw
            from backend.app.core.config import settings
            from tests.helpers_ciclo3 import FakeStripe
            import json as _json
            monkeypatch.setattr(settings, "STRIPE_ENABLED", True)
            monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_falsa")
            monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_prueba")
            fake = FakeStripe()
            fake.instalar()
            try:
                inten = (await cli.client.post(
                    "/api/v1/pagos/stripe/intenciones", json={"venta_id": out["venta_id"]},
                    headers={"Idempotency-Key": clave()})).json()
                cuerpo = _json.dumps({"id": "e1", "type": "payment_intent.succeeded",
                                      "data": {"object": {"id": inten["payment_intent_id"]}}}).encode()
                await cli.client.post(
                    "/api/v1/pagos/stripe/webhook", content=cuerpo,
                    headers={"Stripe-Signature": gw.firmar_prueba(cuerpo, "whsec_prueba")})
            finally:
                fake.desinstalar()
            for estado in ("PREPARADO", "EN_REPARTO", "ENTREGADO"):
                r = await enc.client.patch(f"/api/v1/entregas/{pid}/estado",
                                           json={"estado": estado})
                assert r.status_code == 200 and r.json()["estado"] == estado, r.text
            # Salto inválido en recojo: SOLICITADO -> RECOGIDO directo es 409.
            await agregar_linea(cli, var["variante_id"], 1)
            out2 = await hacer_checkout(cli, suc, "WEB", "RECOJO")
            pid2 = out2["pedido_entrega_id"]
            r = await enc.client.patch(f"/api/v1/entregas/{pid2}/estado",
                                       json={"estado": "EN_REPARTO"})
            assert r.status_code == 409, r.text
    finally:
        await enc.client.aclose()


async def test_cola_paginada_filtrada_y_rbac(cliente_http: AsyncClient):
    admin = cliente_http
    s1 = await crear_sucursal(admin, tag="col1")
    s2 = await crear_sucursal(admin, tag="col2")
    enc1 = await crear_staff(admin, "ENCARGADO", s1, tag="col1")
    try:
        v1 = await crear_variante_con_stock(admin, s1, 4, tag="col1")
        async with await crear_cliente("colc") as cli:
            await _checkout_delivery(cli, s1, v1, anillo=2)
            await agregar_linea(cli, v1["variante_id"], 1)
            await hacer_checkout(cli, s1, "WEB", "RECOJO")
            cola = (await enc1.client.get("/api/v1/entregas/cola",
                                          params={"sucursal_id": s1, "limit": 1})).json()
            assert cola["total"] == 2 and len(cola["items"]) == 1, cola
            sols = (await enc1.client.get("/api/v1/entregas/cola",
                                          params={"sucursal_id": s1, "estado": "SOLICITADO"})).json()
            assert sols["total"] == 2, sols
            # Otra sucursal -> 403; cliente -> 403; sin sucursal -> 400.
            assert (await enc1.client.get("/api/v1/entregas/cola",
                                          params={"sucursal_id": s2})).status_code == 403
            assert (await cli.client.get("/api/v1/entregas/cola",
                                         params={"sucursal_id": s1})).status_code == 403
            assert (await enc1.client.get("/api/v1/entregas/cola")).status_code == 400
            # Admin ve todo sin filtro.
            todo = (await admin.get("/api/v1/entregas/cola")).json()
            assert todo["total"] >= 2
    finally:
        await enc1.client.aclose()


async def test_cancelacion_solo_si_pago_e_inventario_permiten(cliente_http: AsyncClient):
    async with await crear_cliente("e16x") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 4, tag="e16x")
        out = await _checkout_delivery(cli, suc, var, anillo=2)
        # PENDIENTE_PAGO en SOLICITADO: cancela y libera.
        r = await cli.client.post(f"/api/v1/entregas/{out['pedido_entrega_id']}/cancelar")
        assert r.status_code == 200 and r.json()["estado"] == "CANCELADO", r.text
        # Cancelado de nuevo: idempotente.
        r = await cli.client.post(f"/api/v1/entregas/{out['pedido_entrega_id']}/cancelar")
        assert r.status_code == 200 and r.json()["estado"] == "CANCELADO", r.text
