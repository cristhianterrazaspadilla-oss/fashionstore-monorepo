"""CU10 — Preparar y atender reserva (RF11, RF12).

Cola paginada por sucursal, elegibilidad, auditoria y permisos.
"""
from httpx import AsyncClient
from tests.helpers_ciclo2 import (
    bolsa,
    crear_cliente,
    crear_staff,
    crear_sucursal,
    crear_variante_con_stock,
    forzar_vencimiento,
    post_reserva,
)


async def _reserva_local(admin, tag="p"):
    from tests.helpers_ciclo2 import sucursal_semilla

    destino = await sucursal_semilla(admin)
    var = await crear_variante_con_stock(admin, destino, 5, tag=tag)
    return destino, var


async def test_preparar_y_atender_ok_con_auditoria(cliente_http: AsyncClient):
    destino, var = await _reserva_local(cliente_http, tag="p1")
    enc = await crear_staff(cliente_http, "ENCARGADO", destino, tag="p1e")
    try:
        async with await crear_cliente("p1") as cli:
            rid = (await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, None)]))).json()["id"]
            rp = await enc.client.patch(f"/api/v1/reservas/{rid}/preparar")
            assert rp.status_code == 200, rp.text
            assert rp.json()["estado"] == "PREPARADA"
            assert rp.json()["preparada_por"] == enc.id
            assert rp.json()["preparada_en"] is not None
            ra = await enc.client.patch(f"/api/v1/reservas/{rid}/atender")
            assert ra.status_code == 200, ra.text
            assert ra.json()["estado"] == "ATENDIDA"
            assert ra.json()["atendida_por"] == enc.id
            # Repetir es idempotente.
            assert (await enc.client.patch(f"/api/v1/reservas/{rid}/preparar")).status_code == 409
            ra2 = await enc.client.patch(f"/api/v1/reservas/{rid}/atender")
            assert ra2.status_code == 200 and ra2.json()["estado"] == "ATENDIDA"
    finally:
        await enc.client.aclose()


async def test_preparar_con_traslado_pendiente_o_vencida_409(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="p2d")
    origen = await crear_sucursal(cliente_http, tag="p2o")
    var = await crear_variante_con_stock(cliente_http, origen, 4, tag="p2a")
    enc = await crear_staff(cliente_http, "ENCARGADO", destino, tag="p2e")
    try:
        async with await crear_cliente("p2") as cli:
            rid = (
                await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, origen)]))
            ).json()["id"]
            r = await enc.client.patch(f"/api/v1/reservas/{rid}/preparar")
            assert r.status_code == 409, r.text
            assert (await enc.client.patch(f"/api/v1/reservas/{rid}/atender")).status_code == 409
    finally:
        await enc.client.aclose()
    destino2, var2 = await _reserva_local(cliente_http, tag="p2b")
    enc2 = await crear_staff(cliente_http, "ENCARGADO", destino2, tag="p2e2")
    try:
        async with await crear_cliente("p2c") as cli:
            rid = (await post_reserva(cli, bolsa(destino2, [(var2["variante_id"], 1, None)]))).json()["id"]
            await forzar_vencimiento(rid)
            assert (await enc2.client.patch(f"/api/v1/reservas/{rid}/preparar")).status_code == 409
    finally:
        await enc2.client.aclose()


async def test_permisos_preparacion(cliente_http: AsyncClient):
    destino, var = await _reserva_local(cliente_http, tag="p3")
    otra = await crear_sucursal(cliente_http, tag="p3o")
    enc_otra = await crear_staff(cliente_http, "ENCARGADO", otra, tag="p3e")
    cajero = await crear_staff(cliente_http, "CAJERO", destino, tag="p3c")
    try:
        async with await crear_cliente("p3") as cli:
            rid = (await post_reserva(cli, bolsa(destino, [(var["variante_id"], 1, None)]))).json()["id"]
            assert (await cli.client.patch(f"/api/v1/reservas/{rid}/preparar")).status_code == 403
            assert (await enc_otra.client.patch(f"/api/v1/reservas/{rid}/preparar")).status_code == 403
            assert (await cajero.client.patch(f"/api/v1/reservas/{rid}/preparar")).status_code == 403
            assert (await cajero.client.patch(f"/api/v1/reservas/{rid}/atender")).status_code == 403
    finally:
        await enc_otra.client.aclose()
        await cajero.client.aclose()


async def test_panel_sucursal(cliente_http: AsyncClient):
    destino, var = await _reserva_local(cliente_http, tag="p4")
    enc = await crear_staff(cliente_http, "ENCARGADO", destino, tag="p4e")
    try:
        async with await crear_cliente("p4") as cli:
            rid = (await post_reserva(cli, bolsa(destino, [(var["variante_id"], 1, None)]))).json()["id"]
            panel = await enc.client.get("/api/v1/reservas/panel/cola", params={"sucursal": destino})
            assert panel.status_code == 200, panel.text
            assert panel.json()["total"] >= 1
            assert any(i["id"] == rid for i in panel.json()["items"])
            filtrado = await enc.client.get(
                "/api/v1/reservas/panel/cola", params={"sucursal": destino, "estado": "ATENDIDA"}
            )
            assert all(i["estado"] == "ATENDIDA" for i in filtrado.json()["items"])
            # Cliente no accede al panel -> 403.
            assert (await cli.client.get("/api/v1/reservas/panel/cola", params={"sucursal": destino})).status_code == 403
    finally:
        await enc.client.aclose()


async def test_cancelar_en_preparada_ok_y_en_atendida_409(cliente_http: AsyncClient):
    destino, var = await _reserva_local(cliente_http, tag="p5")
    enc = await crear_staff(cliente_http, "ENCARGADO", destino, tag="p5e")
    try:
        async with await crear_cliente("p5a") as cli:
            rid = (await post_reserva(cli, bolsa(destino, [(var["variante_id"], 1, None)]))).json()["id"]
            assert (await enc.client.patch(f"/api/v1/reservas/{rid}/preparar")).status_code == 200
            r = await cli.client.patch(f"/api/v1/reservas/{rid}/cancelar")
            assert r.status_code == 200 and r.json()["estado"] == "CANCELADA"
        async with await crear_cliente("p5b") as cli2:
            rid2 = (await post_reserva(cli2, bolsa(destino, [(var["variante_id"], 1, None)]))).json()["id"]
            assert (await enc.client.patch(f"/api/v1/reservas/{rid2}/preparar")).status_code == 200
            assert (await enc.client.patch(f"/api/v1/reservas/{rid2}/atender")).status_code == 200
            # En ATENDIDA ni el cliente ni el personal cancelan: se cierra con venta.
            assert (await cli2.client.patch(f"/api/v1/reservas/{rid2}/cancelar")).status_code == 409
            assert (await enc.client.patch(f"/api/v1/reservas/{rid2}/cancelar")).status_code == 409
    finally:
        await enc.client.aclose()
