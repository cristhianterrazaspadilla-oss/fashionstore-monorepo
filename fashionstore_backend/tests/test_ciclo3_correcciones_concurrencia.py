"""Corrección 6 — Pruebas de concurrencia reales (asyncio.gather, sin sesión compartida)."""
import asyncio
import json
import uuid

from httpx import AsyncClient

from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw
from backend.app.core.config import settings
from tests.helpers_ciclo2 import crear_cliente, crear_variante_con_stock, sucursal_semilla
from tests.helpers_ciclo3 import (
    FakeStripe, agregar_linea, clave, contar_kardex, forzar_vencimiento_venta,
    hacer_checkout, stock_en,
)


async def test_dos_clientes_ultima_unidad_concurrente(cliente_http: AsyncClient):
    """Dos sesiones independientes compiten por la última unidad con barrera real."""
    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, suc, 1, tag="ccu")
    async with await crear_cliente("ccu1") as c1, await crear_cliente("ccu2") as c2:
        await agregar_linea(c1, var["variante_id"], 1)
        await agregar_linea(c2, var["variante_id"], 1)
        barrera = asyncio.Event()

        async def _checkout(cli):
            await barrera.wait()
            return await cli.client.post(
                "/api/v1/carritos/mio/checkout", params={"canal": "WEB"},
                json={"sucursal_id": suc, "canal": "WEB", "modalidad": "RECOJO"},
                headers={"Idempotency-Key": clave()})

        t1 = asyncio.create_task(_checkout(c1))
        t2 = asyncio.create_task(_checkout(c2))
        await asyncio.sleep(0.05)
        barrera.set()
        r1, r2 = await asyncio.gather(t1, t2)
        oks = [r for r in (r1, r2) if r.status_code == 201]
        conflicts = [r for r in (r1, r2) if r.status_code == 409]
        assert len(oks) == 1 and len(conflicts) == 1, (r1.status_code, r1.text, r2.status_code, r2.text)
        disp, res = await stock_en(suc, var["variante_id"])
        assert disp >= 0 and (disp, res) in ((0, 1),), (disp, res)
        assert await contar_kardex(oks[0].json()["venta_id"], "COMPROMISO_DIGITAL") == 1


async def _carrera_webhook_vs_expirador(cliente_http: AsyncClient, tag: str, expirada: bool) -> None:
    """Una carrera real webhook-vs-expirador con sesiones independientes.

    Webhook viaja por el cliente del comprador y el expirador por el cliente
    admin (`cliente_http`): cada request abre su propia AsyncSession, nunca se
    comparte una sesión entre operaciones concurrentes. Al finalizar ambas,
    la venta debe estar en un único estado terminal coherente.
    """
    from tests.helpers_ciclo2 import crear_cliente as _crear_cliente
    from tests.helpers_ciclo2 import crear_variante_con_stock as _crear_var
    from tests.helpers_ciclo2 import sucursal_semilla as _suc

    async with await _crear_cliente(tag) as cli:
        suc = await _suc(cliente_http)
        var = await _crear_var(cliente_http, suc, 3, tag=tag)
        await agregar_linea(cli, var["variante_id"], 1)
        out = await hacer_checkout(cli, suc, "WEB", "RECOJO")
        venta_id = out["venta_id"]
        pi = (await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": venta_id},
            headers={"Idempotency-Key": clave()})).json()["payment_intent_id"]
        disp0, res0 = await stock_en(suc, var["variante_id"])
        assert (disp0, res0) == (2, 1), (disp0, res0)
        if expirada:
            await forzar_vencimiento_venta(venta_id)
        cuerpo = json.dumps(
            {"id": f"e-{pi}", "type": "payment_intent.succeeded",
             "data": {"object": {"id": pi}}}).encode()
        firma = gw.firmar_prueba(cuerpo, "whsec_prueba")
        barrera = asyncio.Event()

        async def _webhook():
            await barrera.wait()
            return await cli.client.post(
                "/api/v1/pagos/stripe/webhook", content=cuerpo,
                headers={"Stripe-Signature": firma})

        async def _expirar():
            await barrera.wait()
            return await cliente_http.post("/api/v1/pagos/stripe/expiracion/ejecutar")

        t1 = asyncio.create_task(_webhook())
        t2 = asyncio.create_task(_expirar())
        await asyncio.sleep(0.05)
        barrera.set()
        rw, re = await asyncio.gather(t1, t2)
        assert rw.status_code == 200 and re.status_code == 200, (rw.text, re.text)
        estado = (await cli.client.get(
            f"/api/v1/pagos/stripe/estado/{venta_id}")).json()
        n_venta = await contar_kardex(venta_id, "VENTA_DIGITAL")
        n_lib = await contar_kardex(venta_id, "LIBERACION_DIGITAL")
        disp, res = await stock_en(suc, var["variante_id"])
        # Invariantes universales: terminal único, sin doble efecto, sin negativos.
        assert estado["estado_venta"] != "PENDIENTE_PAGO", estado
        assert not (n_venta == 1 and n_lib == 1), (n_venta, n_lib)
        assert disp >= 0 and res >= 0, (disp, res)
        assert res == 0, (disp, res)
        if not expirada:
            # Gana el webhook: venta pagada y consumo definitivo.
            assert estado["estado_venta"] == "PAGADA", estado
            assert estado["estado_pago"] == "APROBADO", estado
            assert n_venta == 1 and n_lib == 0, (n_venta, n_lib)
            assert (disp, res) == (disp0, 0), (disp, res)
        else:
            # Gana el expirador: venta cancelada e inventario restaurado.
            assert estado["estado_venta"] == "CANCELADA", estado
            assert estado["estado_pago"] in ("ANULADO", "RECHAZADO"), estado
            assert n_venta == 0 and n_lib == 1, (n_venta, n_lib)
            assert (disp, res) == (disp0 + 1, 0), (disp, res)


async def test_webhook_y_expirador_simultaneos(cliente_http: AsyncClient, monkeypatch):
    """Webhook aprobado y expirador se ejecutan simultáneamente: un solo ganador.

    Se repiten ambas ramas (vigente/vencida) para forzar intercalado real:
    si gana el webhook la venta queda PAGADA con un único VENTA_DIGITAL;
    si gana el expirador queda CANCELADA con una única LIBERACION_DIGITAL.
    Nunca PENDIENTE_PAGO al final, nunca ambos efectos, nunca negativos.
    """
    monkeypatch.setattr(settings, "STRIPE_ENABLED", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_falsa")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_prueba")
    fake = FakeStripe()
    fake.instalar()
    try:
        for i in range(3):
            await _carrera_webhook_vs_expirador(cliente_http, f"ccw{i}", expirada=False)
        for i in range(3):
            await _carrera_webhook_vs_expirador(cliente_http, f"ccx{i}", expirada=True)
    finally:
        fake.desinstalar()


async def test_misma_idempotency_key_simultanea(cliente_http: AsyncClient):
    """Dos checkouts con la misma Idempotency-Key llegan simultáneamente: sin duplicar.

    Sesiones/conexiones independientes (sin compartir AsyncSession): dos
    clientes HTTP con el mismo token compiten con barrera para garantizar
    solapamiento real. La venta global por clave se serializa y el segundo
    reutiliza la misma venta sin duplicar Kardex.
    """
    from tests.helpers_ciclo2 import _nuevo_client

    async with await crear_cliente("cck") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 9, tag="cck")
        await agregar_linea(cli, var["variante_id"], 2)
        k = clave()
        barrera = asyncio.Event()
        c2 = await _nuevo_client(cli.token)
        cuerpo = {"sucursal_id": suc, "canal": "WEB", "modalidad": "RECOJO"}

        async def _checkout(client):
            await barrera.wait()
            return await client.post(
                "/api/v1/carritos/mio/checkout", params={"canal": "WEB"},
                json=cuerpo,
                headers={"Idempotency-Key": k,
                         "Authorization": f"Bearer {cli.token}"})

        try:
            t1 = asyncio.create_task(_checkout(cli.client))
            t2 = asyncio.create_task(_checkout(c2))
            await asyncio.sleep(0.05)
            barrera.set()
            r1, r2 = await asyncio.gather(t1, t2)
            assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
            assert r1.json()["venta_id"] == r2.json()["venta_id"]
            assert await contar_kardex(r1.json()["venta_id"], "COMPROMISO_DIGITAL") == 1
        finally:
            await c2.aclose()
