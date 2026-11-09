"""Corrección 2 — RBAC de cancelación de pedidos (EntregaService.cancelar).

Solo pueden cancelar: cliente propietario (si el estado lo permite),
ENCARGADO/CAJERO de la sucursal, ADMINISTRADOR. Proveedor u otro rol -> 403
sin mutación.
"""
from httpx import AsyncClient
from sqlalchemy import text

from backend.app.core.database import AsyncSessionLocal
from tests.helpers_ciclo2 import crear_cliente, crear_staff, crear_sucursal, crear_variante_con_stock
from tests.helpers_ciclo3 import agregar_linea, hacer_checkout


async def _pedido_recojo(cli, suc, var):
    await agregar_linea(cli, var["variante_id"], 1)
    return await hacer_checkout(cli, suc, "WEB", "RECOJO")


async def _estado_pedido(pid: str) -> str:
    async with AsyncSessionLocal() as db:
        return (await db.execute(
            text("SELECT estado FROM comercial.pedidos_entrega WHERE id = :p"), {"p": pid}
        )).scalar()


async def test_cancelar_rbac_siete_casos(cliente_http: AsyncClient):
    admin = cliente_http
    s1 = await crear_sucursal(admin, tag="rb1")
    s2 = await crear_sucursal(admin, tag="rb2")
    v1 = await crear_variante_con_stock(admin, s1, 10, tag="rb1")
    enc1 = await crear_staff(admin, "ENCARGADO", s1, tag="rb1")
    enc2 = await crear_staff(admin, "ENCARGADO", s2, tag="rb2")
    caj1 = await crear_staff(admin, "CAJERO", s1, tag="rb1")
    prov = await crear_staff(admin, "PROVEEDOR", s1, tag="rb1")
    try:
        async with await crear_cliente("rbc1") as duenio, await crear_cliente("rbc2") as otro:
            # 1. Cliente propietario: cancela OK.
            out = await _pedido_recojo(duenio, s1, v1)
            r = await duenio.client.post(f"/api/v1/entregas/{out['pedido_entrega_id']}/cancelar")
            assert r.status_code == 200 and r.json()["estado"] == "CANCELADO", r.text

            # 2. Otro cliente: 403 sin mutación.
            out2 = await _pedido_recojo(duenio, s1, v1)
            antes = await _estado_pedido(out2["pedido_entrega_id"])
            r = await otro.client.post(f"/api/v1/entregas/{out2['pedido_entrega_id']}/cancelar")
            assert r.status_code == 403, r.text
            assert await _estado_pedido(out2["pedido_entrega_id"]) == antes

            # 3. Encargado de la sucursal: OK.
            r = await enc1.client.post(f"/api/v1/entregas/{out2['pedido_entrega_id']}/cancelar")
            assert r.status_code == 200 and r.json()["estado"] == "CANCELADO", r.text

            # 4. Encargado de otra sucursal: 403 sin mutación.
            out3 = await _pedido_recojo(duenio, s1, v1)
            antes = await _estado_pedido(out3["pedido_entrega_id"])
            r = await enc2.client.post(f"/api/v1/entregas/{out3['pedido_entrega_id']}/cancelar")
            assert r.status_code == 403, r.text
            assert await _estado_pedido(out3["pedido_entrega_id"]) == antes

            # 5. Cajero correspondiente: OK.
            r = await caj1.client.post(f"/api/v1/entregas/{out3['pedido_entrega_id']}/cancelar")
            assert r.status_code == 200, r.text

            # 6. Proveedor: 403 sin mutación.
            out4 = await _pedido_recojo(duenio, s1, v1)
            antes = await _estado_pedido(out4["pedido_entrega_id"])
            r = await prov.client.post(f"/api/v1/entregas/{out4['pedido_entrega_id']}/cancelar")
            assert r.status_code == 403, r.text
            assert await _estado_pedido(out4["pedido_entrega_id"]) == antes

            # 7. Administrador: OK.
            r = await admin.post(f"/api/v1/entregas/{out4['pedido_entrega_id']}/cancelar")
            assert r.status_code == 200 and r.json()["estado"] == "CANCELADO", r.text
    finally:
        for u in (enc1, enc2, caj1, prov):
            await u.client.aclose()
