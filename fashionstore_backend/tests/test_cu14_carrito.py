"""CU14 — Carrito y checkout: aislamiento, idempotencia, cobertura y compromiso."""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from backend.app.core.database import AsyncSessionLocal
from tests.helpers_ciclo2 import (
    crear_cliente, crear_staff, crear_sucursal, crear_variante_con_stock,
    sucursal_semilla,
)
from tests.helpers_ciclo3 import agregar_linea, clave, contar_kardex, hacer_checkout, stock_en


async def test_carrito_aislado_por_propietario_y_canal(cliente_http: AsyncClient):
    async with await crear_cliente("c14a") as a, await crear_cliente("c14b") as b:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 5, tag="c14a")
        await agregar_linea(a, var["variante_id"], 2, canal="WEB")
        # B no ve la línea de A; su carrito está vacío.
        mio_b = (await b.client.get("/api/v1/carritos/mio", params={"canal": "WEB"})).json()
        assert mio_b["lineas"] == [] and mio_b["cliente_id"] == b.id
        mio_a = (await a.client.get("/api/v1/carritos/mio", params={"canal": "WEB"})).json()
        assert len(mio_a["lineas"]) == 1 and mio_a["lineas"][0]["cantidad"] == 2
        # Canales aislados: MOVIL de A también vacío.
        mio_m = (await a.client.get("/api/v1/carritos/mio", params={"canal": "MOVIL"})).json()
        assert mio_m["lineas"] == []


async def test_lineas_agregar_modificar_quitar_vaciar_e_idempotencia(cliente_http: AsyncClient):
    async with await crear_cliente("c14m") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 9, tag="c14m")
        vid = var["variante_id"]
        k = clave()
        c1 = await agregar_linea(cli, vid, 1, clave_id=k)
        # Reintento misma clave + mismo payload -> mismo resultado, sin duplicar.
        r = await cli.client.post(
            "/api/v1/carritos/mio/lineas", params={"canal": "WEB"},
            json={"variante_id": vid, "cantidad": 1}, headers={"Idempotency-Key": k})
        assert r.status_code == 200 and r.json() == c1, r.text
        # Misma clave + distinto payload -> 409.
        r = await cli.client.post(
            "/api/v1/carritos/mio/lineas", params={"canal": "WEB"},
            json={"variante_id": vid, "cantidad": 3}, headers={"Idempotency-Key": k})
        assert r.status_code == 409, r.text
        # Modificar cantidad.
        k2 = clave()
        r = await cli.client.patch(
            f"/api/v1/carritos/mio/lineas/{vid}", params={"canal": "WEB"},
            json={"cantidad": 4}, headers={"Idempotency-Key": k2})
        assert r.status_code == 200 and r.json()["lineas"][0]["cantidad"] == 4, r.text
        # Quitar.
        r = await cli.client.delete(
            f"/api/v1/carritos/mio/lineas/{vid}", params={"canal": "WEB"},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 200 and r.json()["lineas"] == [], r.text
        # Vaciar con dos líneas.
        v2 = await crear_variante_con_stock(cliente_http, suc, 9, tag="c14m2")
        await agregar_linea(cli, vid, 1)
        await agregar_linea(cli, v2["variante_id"], 1)
        r = await cli.client.delete("/api/v1/carritos/mio", params={"canal": "WEB"},
                                    headers={"Idempotency-Key": clave()})
        assert r.status_code == 200 and r.json()["lineas"] == [], r.text


async def test_agregar_no_compromete_inventario(cliente_http: AsyncClient):
    async with await crear_cliente("c14s") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 7, tag="c14s")
        antes = await stock_en(suc, var["variante_id"])
        await agregar_linea(cli, var["variante_id"], 3)
        despues = await stock_en(suc, var["variante_id"])
        assert antes == despues == (7, 0)


async def test_checkout_una_sola_sucursal_y_compromiso_60min(cliente_http: AsyncClient):
    async with await crear_cliente("c14k") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 6, tag="c14k",
                                             precio="120.00", costo="60.00")
        await agregar_linea(cli, var["variante_id"], 2, canal="MOVIL")
        out = await hacer_checkout(cli, suc, canal="MOVIL", modalidad="RECOJO")
        assert out["estado"] == "PENDIENTE_PAGO"
        # Compromiso: disponible 6->4, reservado 0->2, expira en ~60 min.
        assert await stock_en(suc, var["variante_id"]) == (4, 2)
        assert await contar_kardex(out["venta_id"], "COMPROMISO_DIGITAL") == 1
        venta = (await cli.client.get(f"/api/v1/ventas/{out['venta_id']}")).json()
        assert venta["canal"] == "MOVIL" and venta["subtotal"] == "240.00", venta
        assert venta["expira_en"] is not None
        # Carrito convertido: uno nuevo vacío para seguir comprando.
        mio = (await cli.client.get("/api/v1/carritos/mio", params={"canal": "MOVIL"})).json()
        assert mio["lineas"] == [] and mio["estado"] == "ACTIVO"


async def test_checkout_multiitem_no_cubierto_409_sin_efectos(cliente_http: AsyncClient):
    admin = cliente_http
    s1 = await crear_sucursal(admin, tag="nc1")
    s2 = await crear_sucursal(admin, tag="nc2")
    va = await crear_variante_con_stock(admin, s1, 5, tag="nca")
    vb = await crear_variante_con_stock(admin, s2, 5, tag="ncb")
    async with await crear_cliente("ncc") as cli:
        await agregar_linea(cli, va["variante_id"], 1)
        await agregar_linea(cli, vb["variante_id"], 1)
        # Cobertura informa que ninguna cubre todo.
        cob = (await cli.client.get("/api/v1/carritos/mio/cobertura",
                                    params={"canal": "WEB"})).json()
        assert all(not s["cubre_todo"] for s in cob["sucursales"])
        # Checkout en s1 -> 409 sin efectos parciales.
        r = await cli.client.post(
            "/api/v1/carritos/mio/checkout", params={"canal": "WEB"},
            json={"sucursal_id": s1, "canal": "WEB", "modalidad": "RECOJO"},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 409, r.text
        assert await stock_en(s1, va["variante_id"]) == (5, 0)
        assert await stock_en(s2, vb["variante_id"]) == (5, 0)


async def test_checkout_idempotente_misma_y_distinta(cliente_http: AsyncClient):
    async with await crear_cliente("c14i") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 8, tag="c14i")
        await agregar_linea(cli, var["variante_id"], 1)
        k = clave()
        out1 = await hacer_checkout(cli, suc, "WEB", "RECOJO", clave_id=k)
        # Misma clave + mismo payload -> mismo resultado (201 con mismo id).
        out2 = await hacer_checkout(cli, suc, "WEB", "RECOJO", clave_id=k)
        assert out2["venta_id"] == out1["venta_id"]
        assert await contar_kardex(out1["venta_id"], "COMPROMISO_DIGITAL") == 1
        # Misma clave + payload distinto -> 409.
        r = await cli.client.post(
            "/api/v1/carritos/mio/checkout", params={"canal": "WEB"},
            json={"sucursal_id": suc, "canal": "WEB", "modalidad": "DELIVERY",
                  "direccion": "Av X", "anillo_destino": 2},
            headers={"Idempotency-Key": k})
        assert r.status_code == 409, r.text


async def test_checkout_concurrencia_ultima_unidad(cliente_http: AsyncClient):
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_con_stock(admin, suc, 1, tag="c14u")
    async with await crear_cliente("c14u1") as c1, await crear_cliente("c14u2") as c2:
        await agregar_linea(c1, var["variante_id"], 1)
        await agregar_linea(c2, var["variante_id"], 1)
        ok = await hacer_checkout(c1, suc, "WEB", "RECOJO")
        assert await stock_en(suc, var["variante_id"]) == (0, 1)
        r = await c2.client.post(
            "/api/v1/carritos/mio/checkout", params={"canal": "WEB"},
            json={"sucursal_id": suc, "canal": "WEB", "modalidad": "RECOJO"},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 409, r.text
        assert await contar_kardex(ok["venta_id"], "COMPROMISO_DIGITAL") == 1


async def test_checkout_rollback_si_falla_kardex(cliente_http: AsyncClient, monkeypatch):
    """Si falla Kardex, no hay venta ni movimiento de stock."""
    from backend.app.core.modules.inventario.repositories import movimiento_repository as mov_mod

    async with await crear_cliente("c14r") as cli:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_con_stock(cliente_http, suc, 4, tag="c14r")
        await agregar_linea(cli, var["variante_id"], 1)

        async def _roto(self, movimiento):
            raise RuntimeError("kardex caído")

        monkeypatch.setattr(mov_mod.MovimientoRepository, "registrar", _roto)
        async with AsyncSessionLocal() as db:
            n0 = (await db.execute(text("SELECT count(*) FROM comercial.ventas"))).scalar()
        r = await cli.client.post(
            "/api/v1/carritos/mio/checkout", params={"canal": "WEB"},
            json={"sucursal_id": suc, "canal": "WEB", "modalidad": "RECOJO"},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 500, r.text
        assert await stock_en(suc, var["variante_id"]) == (4, 0)
        async with AsyncSessionLocal() as db:
            n1 = (await db.execute(text("SELECT count(*) FROM comercial.ventas"))).scalar()
        assert n1 == n0
