"""CU16 — Pruebas de capacidades calculadas por backend en PedidoDTO."""
import json as _json
import pytest
from httpx import AsyncClient

from tests.helpers_ciclo2 import (
    crear_cliente, crear_staff, crear_sucursal, crear_variante_con_stock,
    sucursal_semilla,
)
from tests.helpers_ciclo3 import FakeStripe, agregar_linea, clave, hacer_checkout


async def _checkout(cli, suc, var, modalidad="RECOJO"):
    await agregar_linea(cli, var["variante_id"], 1)
    if modalidad == "RECOJO":
        return await hacer_checkout(cli, suc, "WEB", "RECOJO")
    else:
        return await hacer_checkout(cli, suc, "WEB", "DELIVERY", direccion="Av. Banzer 4567", anillo=2)


async def _pagar_venta(cli, venta_id: str, monkeypatch):
    from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "STRIPE_ENABLED", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_falsa")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_prueba")
    fake = FakeStripe()
    fake.instalar()
    try:
        inten = (await cli.client.post(
            "/api/v1/pagos/stripe/intenciones", json={"venta_id": venta_id},
            headers={"Idempotency-Key": clave()})).json()
        cuerpo = _json.dumps({
            "id": "evt_pago",
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": inten["payment_intent_id"]}}
        }).encode()
        await cli.client.post(
            "/api/v1/pagos/stripe/webhook", content=cuerpo,
            headers={"Stripe-Signature": gw.firmar_prueba(cuerpo, "whsec_prueba")}
        )
    finally:
        fake.desinstalar()


async def _forzar_venta_pagada_pedido_solicitado(pedido_id: str, venta_id: str):
    from backend.app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE comercial.ventas SET estado = 'PAGADA' WHERE id = :vid"), {"vid": venta_id})
        await db.execute(text("UPDATE comercial.pedidos_entrega SET estado = 'SOLICITADO' WHERE id = :pid"), {"pid": pedido_id})
        await db.commit()


async def test_capacidades_cliente_pendiente_vs_pagado(cliente_http: AsyncClient):
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_con_stock(admin, suc, 10, tag="cap1", precio="100.00")

    async with await crear_cliente("capcli") as cli:
        out = await _checkout(cli, suc, var, modalidad="RECOJO")
        pid = out["pedido_entrega_id"]
        vid = out["venta_id"]

        # 1. Con venta PENDIENTE_PAGO en SOLICITADO: cliente puede cancelar
        ped_pendiente = (await cli.client.get(f"/api/v1/entregas/{pid}")).json()
        assert ped_pendiente["estado"] == "SOLICITADO"
        assert ped_pendiente["puede_cancelar"] is True
        assert ped_pendiente["puede_transicionar"] is False
        assert ped_pendiente["siguiente_estado"] is None

        # 2. Venta PAGADA en SOLICITADO: cliente no puede cancelar
        await _forzar_venta_pagada_pedido_solicitado(pid, vid)

        ped_pagado = (await cli.client.get(f"/api/v1/entregas/{pid}")).json()
        assert ped_pagado["estado"] == "SOLICITADO"
        assert ped_pagado["puede_cancelar"] is False
        assert ped_pagado["puede_transicionar"] is False
        assert ped_pagado["siguiente_estado"] is None


async def test_capacidades_operativo_misma_vs_otra_sucursal(cliente_http: AsyncClient):
    admin = cliente_http
    s1 = await crear_sucursal(admin, tag="s1cap")
    s2 = await crear_sucursal(admin, tag="s2cap")
    enc1 = await crear_staff(admin, "ENCARGADO", s1, tag="enc1cap")
    enc2 = await crear_staff(admin, "ENCARGADO", s2, tag="enc2cap")
    v1 = await crear_variante_con_stock(admin, s1, 10, tag="v1cap", precio="80.00")

    try:
        async with await crear_cliente("opcap") as cli:
            out = await _checkout(cli, s1, v1, modalidad="RECOJO")
            pid = out["pedido_entrega_id"]
            vid = out["venta_id"]

            # Antes de pagar: enc1 (misma sucursal) no puede transicionar a PREPARADO porque venta está PENDIENTE_PAGO
            p_enc1_nopago = (await enc1.client.get(f"/api/v1/entregas/{pid}")).json()
            assert p_enc1_nopago["puede_transicionar"] is False
            assert p_enc1_nopago["siguiente_estado"] is None
            assert p_enc1_nopago["puede_cancelar"] is True

            # enc2 (otra sucursal) no puede ni ver el pedido directamente (403 por autorizar_pedido)
            r_enc2 = await enc2.client.get(f"/api/v1/entregas/{pid}")
            assert r_enc2.status_code == 403

            # Venta PAGADA en SOLICITADO
            await _forzar_venta_pagada_pedido_solicitado(pid, vid)

            # Ahora enc1 puede transicionar a PREPARADO
            p_enc1_pago = (await enc1.client.get(f"/api/v1/entregas/{pid}")).json()
            assert p_enc1_pago["puede_cancelar"] is False
            assert p_enc1_pago["puede_transicionar"] is True
            assert p_enc1_pago["siguiente_estado"] == "PREPARADO"
    finally:
        for u in (enc1, enc2):
            await u.client.aclose()


async def test_capacidades_flujo_recojo_completo(cliente_http: AsyncClient):
    admin = cliente_http
    suc = await crear_sucursal(admin, tag="recflow")
    enc = await crear_staff(admin, "ENCARGADO", suc, tag="encrec")
    var = await crear_variante_con_stock(admin, suc, 10, tag="vrec", precio="50.00")

    try:
        async with await crear_cliente("clirec") as cli:
            out = await _checkout(cli, suc, var, modalidad="RECOJO")
            pid = out["pedido_entrega_id"]
            vid = out["venta_id"]
            await _forzar_venta_pagada_pedido_solicitado(pid, vid)

            # 1. SOLICITADO -> siguiente: PREPARADO
            p = (await enc.client.get(f"/api/v1/entregas/{pid}")).json()
            assert p["siguiente_estado"] == "PREPARADO"
            assert p["puede_transicionar"] is True

            # Avanzar a PREPARADO
            p = (await enc.client.patch(f"/api/v1/entregas/{pid}/estado", json={"estado": "PREPARADO"})).json()
            assert p["estado"] == "PREPARADO"
            assert p["siguiente_estado"] == "LISTO_RECOJO"
            assert p["puede_transicionar"] is True

            # Avanzar a LISTO_RECOJO
            p = (await enc.client.patch(f"/api/v1/entregas/{pid}/estado", json={"estado": "LISTO_RECOJO"})).json()
            assert p["estado"] == "LISTO_RECOJO"
            assert p["siguiente_estado"] == "RECOGIDO"
            assert p["puede_transicionar"] is True

            # Avanzar a RECOGIDO
            p = (await enc.client.patch(f"/api/v1/entregas/{pid}/estado", json={"estado": "RECOGIDO"})).json()
            assert p["estado"] == "RECOGIDO"
            # Estado terminal
            assert p["siguiente_estado"] is None
            assert p["puede_transicionar"] is False
            assert p["puede_cancelar"] is False
    finally:
        await enc.client.aclose()


async def test_capacidades_flujo_delivery_completo(cliente_http: AsyncClient):
    admin = cliente_http
    suc = await crear_sucursal(admin, tag="delflow")
    enc = await crear_staff(admin, "ENCARGADO", suc, tag="encdel")
    var = await crear_variante_con_stock(admin, suc, 10, tag="vdel", precio="75.00")

    try:
        async with await crear_cliente("clidel") as cli:
            out = await _checkout(cli, suc, var, modalidad="DELIVERY")
            pid = out["pedido_entrega_id"]
            vid = out["venta_id"]
            await _forzar_venta_pagada_pedido_solicitado(pid, vid)

            # 1. SOLICITADO -> PREPARADO
            p = (await enc.client.get(f"/api/v1/entregas/{pid}")).json()
            assert p["siguiente_estado"] == "PREPARADO"

            p = (await enc.client.patch(f"/api/v1/entregas/{pid}/estado", json={"estado": "PREPARADO"})).json()
            assert p["estado"] == "PREPARADO"
            assert p["siguiente_estado"] == "EN_REPARTO"
            assert p["puede_transicionar"] is True

            p = (await enc.client.patch(f"/api/v1/entregas/{pid}/estado", json={"estado": "EN_REPARTO"})).json()
            assert p["estado"] == "EN_REPARTO"
            assert p["siguiente_estado"] == "ENTREGADO"
            assert p["puede_transicionar"] is True

            p = (await enc.client.patch(f"/api/v1/entregas/{pid}/estado", json={"estado": "ENTREGADO"})).json()
            assert p["estado"] == "ENTREGADO"
            assert p["siguiente_estado"] is None
            assert p["puede_transicionar"] is False
    finally:
        await enc.client.aclose()


async def test_transicion_concurrente_409(cliente_http: AsyncClient):
    admin = cliente_http
    suc = await crear_sucursal(admin, tag="concur")
    enc = await crear_staff(admin, "ENCARGADO", suc, tag="enccon")
    var = await crear_variante_con_stock(admin, suc, 10, tag="vcon", precio="90.00")

    try:
        async with await crear_cliente("clicon") as cli:
            out = await _checkout(cli, suc, var, modalidad="RECOJO")
            pid = out["pedido_entrega_id"]
            vid = out["venta_id"]
            await _forzar_venta_pagada_pedido_solicitado(pid, vid)

            # Primer operador avanza a PREPARADO
            r1 = await enc.client.patch(f"/api/v1/entregas/{pid}/estado", json={"estado": "PREPARADO"})
            assert r1.status_code == 200

            # Segundo operador intenta avanzar a RECOGIDO saltando LISTO_RECOJO -> 409
            r2 = await enc.client.patch(f"/api/v1/entregas/{pid}/estado", json={"estado": "RECOGIDO"})
            assert r2.status_code == 409
    finally:
        await enc.client.aclose()
