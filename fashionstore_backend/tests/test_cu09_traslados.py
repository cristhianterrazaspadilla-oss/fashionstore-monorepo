"""CU09 — Solicitar, aprobar y recibir traslados (RF21, RF22).

Matriz SOLICITADO->APROBADO->DESPACHADO->RECIBIDO / ->RECHAZADO;
rechazo parcial/total, reintento, permisos por sucursal, idempotencia.
"""
import uuid
from httpx import AsyncClient
from sqlalchemy import select
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from tests.helpers_ciclo2 import (
    bolsa,
    crear_cliente,
    crear_staff,
    crear_sucursal,
    crear_variante_con_stock,
    forzar_vencimiento,
    post_reserva,
)


async def _stock(variante_id, sucursal_id):
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.variante_id == uuid.UUID(variante_id),
                    InventarioSucursal.sucursal_id == uuid.UUID(sucursal_id),
                )
            )
        ).scalars().first()


async def _tipos_kardex_traslado(traslado_id):
    async with AsyncSessionLocal() as db:
        movs = (
            await db.execute(
                select(MovimientoInventario).where(
                    MovimientoInventario.referencia_tipo == "TRASLADO",
                    MovimientoInventario.referencia_id == uuid.UUID(traslado_id),
                )
            )
        ).scalars().all()
        return [m.tipo for m in movs]


async def test_flujo_completo_aprobar_despachar_recibir(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="t1d")
    origen = await crear_sucursal(cliente_http, tag="t1o")
    var = await crear_variante_con_stock(cliente_http, origen, 5, tag="t1a")
    enc_origen = await crear_staff(cliente_http, "ENCARGADO", origen, tag="t1eo")
    enc_destino = await crear_staff(cliente_http, "ENCARGADO", destino, tag="t1ed")
    try:
        async with await crear_cliente("t1") as cli:
            resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 3, origen)]))
            assert resp.status_code == 201
            rid, tid = resp.json()["id"], resp.json()["traslados"][0]["id"]
            ra = await enc_origen.client.patch(f"/api/v1/traslados/{tid}/aprobar")
            assert ra.status_code == 200, ra.text
            assert ra.json()["estado"] == "APROBADO"
            reg = await _stock(var["variante_id"], origen)
            assert (reg.disponible, reg.comprometido_traslado) == (2, 3)
            # Repetir aprobar es idempotente.
            ra2 = await enc_origen.client.patch(f"/api/v1/traslados/{tid}/aprobar")
            assert ra2.status_code == 200 and ra2.json()["estado"] == "APROBADO"
            reg = await _stock(var["variante_id"], origen)
            assert (reg.disponible, reg.comprometido_traslado) == (2, 3)
            rd = await enc_origen.client.patch(f"/api/v1/traslados/{tid}/despachar")
            assert rd.status_code == 200, rd.text
            reg = await _stock(var["variante_id"], origen)
            assert (reg.comprometido_traslado, reg.en_transito) == (0, 3)
            rr = await enc_destino.client.patch(f"/api/v1/traslados/{tid}/recibir")
            assert rr.status_code == 200, rr.text
            assert rr.json()["estado"] == "RECIBIDO"
            reg_o = await _stock(var["variante_id"], origen)
            reg_d = await _stock(var["variante_id"], destino)
            assert (reg_o.en_transito, reg_d.reservado) == (0, 3)
            assert await _tipos_kardex_traslado(tid) == [
                "COMPROMISO_TRASLADO", "DESPACHO_TRASLADO", "RECEPCION_TRASLADO",
            ]
            reserva = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()
            assert reserva["estado"] == "PENDIENTE"
            assert reserva["detalles"][0]["estado_linea"] == "RESERVADA"
    finally:
        await enc_origen.client.aclose()
        await enc_destino.client.aclose()


async def test_rechazo_parcial_continua_y_total_cancela(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="t2d")
    origen = await crear_sucursal(cliente_http, tag="t2o")
    var_a = await crear_variante_con_stock(cliente_http, origen, 4, tag="t2a")
    var_b = await crear_variante_con_stock(cliente_http, origen, 4, tag="t2b")
    var_local = await crear_variante_con_stock(cliente_http, destino, 4, tag="t2c")
    enc_origen = await crear_staff(cliente_http, "ENCARGADO", origen, tag="t2e")
    try:
        async with await crear_cliente("t2") as cli:
            resp = await post_reserva(
                cli,
                bolsa(destino, [
                    (var_a["variante_id"], 2, origen),
                    (var_b["variante_id"], 2, origen),
                    (var_local["variante_id"], 1, None),
                ]),
            )
            assert resp.status_code == 201
            rid = resp.json()["id"]
            tids = {t["id"] for t in resp.json()["traslados"]}
            assert len(tids) == 2
            t1, t2 = list(tids)
            r1 = await enc_origen.client.patch(f"/api/v1/traslados/{t1}/rechazar", json={"motivo": "Sin stock fisico"})
            assert r1.status_code == 200 and r1.json()["estado"] == "RECHAZADO"
            reserva = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()
            assert reserva["estado"] == "PENDIENTE_TRASLADO"  # queda un pendiente
            r2 = await enc_origen.client.patch(f"/api/v1/traslados/{t2}/rechazar", json={})
            assert r2.status_code == 200
            reserva = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()
            # Rechazo total de traslados pero hay linea local atendible -> PENDIENTE.
            assert reserva["estado"] == "PENDIENTE"
            reg = await _stock(var_local["variante_id"], destino)
            assert (reg.disponible, reg.reservado) == (3, 1)
    finally:
        await enc_origen.client.aclose()


async def test_rechazo_total_solo_traslado_cancela_y_libera(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="t3d")
    origen = await crear_sucursal(cliente_http, tag="t3o")
    var = await crear_variante_con_stock(cliente_http, origen, 4, tag="t3a")
    enc_origen = await crear_staff(cliente_http, "ENCARGADO", origen, tag="t3e")
    try:
        async with await crear_cliente("t3") as cli:
            resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, origen)]))
            rid, tid = resp.json()["id"], resp.json()["traslados"][0]["id"]
            r = await enc_origen.client.patch(f"/api/v1/traslados/{tid}/rechazar", json={"motivo": "No"})
            assert r.status_code == 200
            reserva = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()
            assert reserva["estado"] == "CANCELADA"
            assert reserva["detalles"][0]["estado_linea"] == "RECHAZADA"
    finally:
        await enc_origen.client.aclose()


async def test_transiciones_invalidas_409(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="t4d")
    origen = await crear_sucursal(cliente_http, tag="t4o")
    var = await crear_variante_con_stock(cliente_http, origen, 4, tag="t4a")
    enc_origen = await crear_staff(cliente_http, "ENCARGADO", origen, tag="t4e")
    enc_destino = await crear_staff(cliente_http, "ENCARGADO", destino, tag="t4ed")
    try:
        async with await crear_cliente("t4") as cli:
            resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, origen)]))
            tid = resp.json()["traslados"][0]["id"]
            # Recibir antes de despachar -> 409.
            assert (await enc_destino.client.patch(f"/api/v1/traslados/{tid}/recibir")).status_code == 409
            # Despachar antes de aprobar -> 409.
            assert (await enc_origen.client.patch(f"/api/v1/traslados/{tid}/despachar")).status_code == 409
            assert (await enc_origen.client.patch(f"/api/v1/traslados/{tid}/aprobar")).status_code == 200
            # Rechazar despues de aprobar -> 409.
            assert (await enc_origen.client.patch(f"/api/v1/traslados/{tid}/rechazar", json={})).status_code == 409
            assert (await enc_origen.client.patch(f"/api/v1/traslados/{tid}/despachar")).status_code == 200
            # Aprobar despues de despachar -> 409.
            assert (await enc_origen.client.patch(f"/api/v1/traslados/{tid}/aprobar")).status_code == 409
            rr = await enc_destino.client.patch(f"/api/v1/traslados/{tid}/recibir")
            assert rr.status_code == 200
            # Repetir recibir es idempotente.
            rr2 = await enc_destino.client.patch(f"/api/v1/traslados/{tid}/recibir")
            assert rr2.status_code == 200 and rr2.json()["estado"] == "RECIBIDO"
            assert await _tipos_kardex_traslado(tid) == [
                "COMPROMISO_TRASLADO", "DESPACHO_TRASLADO", "RECEPCION_TRASLADO",
            ]
    finally:
        await enc_origen.client.aclose()
        await enc_destino.client.aclose()


async def test_permisos_traslado(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="t5d")
    origen = await crear_sucursal(cliente_http, tag="t5o")
    otra = await crear_sucursal(cliente_http, tag="t5x")
    var = await crear_variante_con_stock(cliente_http, origen, 4, tag="t5a")
    enc_otra = await crear_staff(cliente_http, "ENCARGADO", otra, tag="t5e")
    cajero = await crear_staff(cliente_http, "CAJERO", origen, tag="t5c")
    try:
        async with await crear_cliente("t5") as cli:
            resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, origen)]))
            tid = resp.json()["traslados"][0]["id"]
            assert (await cli.client.patch(f"/api/v1/traslados/{tid}/aprobar")).status_code == 403
            assert (await enc_otra.client.patch(f"/api/v1/traslados/{tid}/aprobar")).status_code == 403
            assert (await cajero.client.patch(f"/api/v1/traslados/{tid}/aprobar")).status_code == 403
            assert (await enc_otra.client.patch(f"/api/v1/traslados/{tid}/despachar")).status_code == 403
    finally:
        await enc_otra.client.aclose()
        await cajero.client.aclose()


async def test_reintento_linea_rechazada_otro_origen(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="t6d")
    origen1 = await crear_sucursal(cliente_http, tag="t6o1")
    origen2 = await crear_sucursal(cliente_http, tag="t6o2")
    var = await crear_variante_con_stock(cliente_http, origen1, 4, tag="t6a")
    var_local = await crear_variante_con_stock(cliente_http, destino, 4, tag="t6c")
    enc1 = await crear_staff(cliente_http, "ENCARGADO", origen1, tag="t6e")
    try:
        async with await crear_cliente("t6") as cli:
            resp = await post_reserva(
                cli,
                bolsa(destino, [(var["variante_id"], 2, origen1), (var_local["variante_id"], 1, None)]),
            )
            rid = resp.json()["id"]
            tid = resp.json()["traslados"][0]["id"]
            detalle_id = next(d["id"] for d in resp.json()["detalles"] if d["estado_linea"] == "PENDIENTE_TRASLADO")
            # Con traslado activo no se puede solicitar otro -> 409.
            dup = await cli.client.post(
                "/api/v1/traslados/solicitudes",
                json={"detalle_reserva_id": detalle_id, "sucursal_origen_id": origen1},
                headers=cli.headers_clave(),
            )
            assert dup.status_code == 409, dup.text
            assert (await enc1.client.patch(f"/api/v1/traslados/{tid}/rechazar", json={})).status_code == 200
            # La linea local sigue valida -> la reserva continua PENDIENTE y admite reintento.
            assert (await cli.client.get(f"/api/v1/reservas/{rid}")).json()["estado"] == "PENDIENTE"
            # Reintento con otro origen necesita stock de LA MISMA variante: lo ingresamos.
            r_recep = await cliente_http.post(
                "/api/v1/recepciones",
                json={
                    "proveedor_id": (await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov t6 {uuid.uuid4().hex[:6]}"})).json()["id"],
                    "sucursal_id": origen2,
                    "recibido_por_id": enc1.id,
                    "detalles": [{"variante_id": var["variante_id"], "cantidad": 4, "costo_unitario": "10.00"}],
                },
            )
            assert r_recep.status_code == 201, r_recep.text
            r2 = await cli.client.post(
                "/api/v1/traslados/solicitudes",
                json={"detalle_reserva_id": detalle_id, "sucursal_origen_id": origen2},
                headers=cli.headers_clave(),
            )
            assert r2.status_code == 201, r2.text
            assert r2.json()["estado"] == "SOLICITADO"
            reserva = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()
            assert reserva["estado"] == "PENDIENTE_TRASLADO"
    finally:
        await enc1.client.aclose()


async def test_aprobar_sin_stock_409(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="t7d")
    origen = await crear_sucursal(cliente_http, tag="t7o")
    var = await crear_variante_con_stock(cliente_http, origen, 2, tag="t7a")
    enc_origen = await crear_staff(cliente_http, "ENCARGADO", origen, tag="t7e")
    try:
        async with await crear_cliente("t7a") as cli_a, await crear_cliente("t7b") as cli_b:
            resp = await post_reserva(cli_a, bolsa(destino, [(var["variante_id"], 2, origen)]))
            tid = resp.json()["traslados"][0]["id"]
            # Otro cliente consume el stock local del origen.
            r_local = await post_reserva(cli_b, bolsa(origen, [(var["variante_id"], 2, None)]))
            assert r_local.status_code == 201
            assert (await enc_origen.client.patch(f"/api/v1/traslados/{tid}/aprobar")).status_code == 409
    finally:
        await enc_origen.client.aclose()


async def test_recibir_con_reserva_cancelada_queda_disponible(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="t8d")
    origen = await crear_sucursal(cliente_http, tag="t8o")
    var = await crear_variante_con_stock(cliente_http, origen, 5, tag="t8a")
    enc_origen = await crear_staff(cliente_http, "ENCARGADO", origen, tag="t8e")
    enc_destino = await crear_staff(cliente_http, "ENCARGADO", destino, tag="t8ed")
    try:
        async with await crear_cliente("t8") as cli:
            resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, origen)]))
            rid, tid = resp.json()["id"], resp.json()["traslados"][0]["id"]
            assert (await enc_origen.client.patch(f"/api/v1/traslados/{tid}/aprobar")).status_code == 200
            assert (await enc_origen.client.patch(f"/api/v1/traslados/{tid}/despachar")).status_code == 200
            # Cancelar con traslado despachado: continua hasta destino.
            assert (await cli.client.patch(f"/api/v1/reservas/{rid}/cancelar")).status_code == 200
            rr = await enc_destino.client.patch(f"/api/v1/traslados/{tid}/recibir")
            assert rr.status_code == 200, rr.text
            reg_d = await _stock(var["variante_id"], destino)
            assert (reg_d.disponible, reg_d.reservado) == (2, 0)
    finally:
        await enc_origen.client.aclose()
        await enc_destino.client.aclose()


async def test_listar_traslados_paginado_con_total_y_permisos(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="t9d")
    origen = await crear_sucursal(cliente_http, tag="t9o")
    var_a = await crear_variante_con_stock(cliente_http, origen, 4, tag="t9a")
    var_b = await crear_variante_con_stock(cliente_http, origen, 4, tag="t9b")
    enc_origen = await crear_staff(cliente_http, "ENCARGADO", origen, tag="t9e")
    try:
        async with await crear_cliente("t9") as cli, await crear_cliente("t9b") as otro:
            resp = await post_reserva(
                cli,
                bolsa(destino, [(var_a["variante_id"], 1, origen), (var_b["variante_id"], 1, origen)]),
            )
            assert resp.status_code == 201
            rid = resp.json()["id"]
            # Estructura total/limit/offset/items sin filtros (admin ve todo).
            r = await cliente_http.get("/api/v1/traslados")
            assert r.status_code == 200, r.text
            datos = r.json()
            assert set(datos.keys()) == {"total", "limit", "offset", "items"}
            assert datos["total"] >= 2 and datos["limit"] == 50 and datos["offset"] == 0
            assert len(datos["items"]) <= datos["total"]
            # Total con filtros: por reserva y por estado.
            rf = await cliente_http.get("/api/v1/traslados", params={"reserva_id": rid})
            assert rf.json()["total"] == 2
            re_ = await cliente_http.get("/api/v1/traslados", params={"estado": "SOLICITADO", "reserva_id": rid})
            assert re_.json()["total"] == 2
            rv = await cliente_http.get("/api/v1/traslados", params={"estado": "RECIBIDO", "reserva_id": rid})
            assert rv.json() == {"total": 0, "limit": 50, "offset": 0, "items": []}
            # Segunda pagina: el total se calcula antes de limit/offset.
            p1 = await cliente_http.get("/api/v1/traslados", params={"reserva_id": rid, "limit": 1, "offset": 0})
            p2 = await cliente_http.get("/api/v1/traslados", params={"reserva_id": rid, "limit": 1, "offset": 1})
            assert p1.json()["total"] == 2 and len(p1.json()["items"]) == 1
            assert p2.json()["total"] == 2 and len(p2.json()["items"]) == 1
            assert p1.json()["items"][0]["id"] != p2.json()["items"][0]["id"]
            # Filtro por origen respeta el mismo conteo.
            ro = await cliente_http.get("/api/v1/traslados", params={"sucursal_origen_id": origen})
            assert ro.json()["total"] >= 2
            # Cliente: exige reserva propia.
            rc = await cli.client.get("/api/v1/traslados", params={"reserva_id": rid})
            assert rc.status_code == 200 and rc.json()["total"] == 2
            assert (await cli.client.get("/api/v1/traslados")).status_code == 403
            assert (await otro.client.get("/api/v1/traslados", params={"reserva_id": rid})).status_code == 403
            # Encargado: exige filtro por su sucursal.
            reo = await enc_origen.client.get("/api/v1/traslados", params={"sucursal_origen_id": origen})
            assert reo.status_code == 200 and reo.json()["total"] >= 2
            assert (await enc_origen.client.get("/api/v1/traslados")).status_code == 403
            assert (
                await enc_origen.client.get("/api/v1/traslados", params={"sucursal_origen_id": destino})
            ).status_code == 403
    finally:
        await enc_origen.client.aclose()
