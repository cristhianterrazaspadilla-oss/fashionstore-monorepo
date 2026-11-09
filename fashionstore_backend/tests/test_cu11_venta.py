"""CU11 — Venta presencial y pago en caja (RF17, RF18, RF20).

Directa y desde reserva, total y parcial, adelanto unico, idempotencia,
permisos, comprobante y rollback ante fallo de Kardex.
"""
import uuid
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select, func
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.modules.ventas_pagos.models import Venta
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from tests.helpers_ciclo2 import (
    activar_adelanto,
    bolsa,
    crear_cliente,
    crear_staff,
    crear_sucursal,
    crear_variante_con_stock,
    forzar_vencimiento,
    post_reserva,
    sucursal_semilla,
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


async def preparar_atender(enc, rid):
    assert (await enc.client.patch(f"/api/v1/reservas/{rid}/preparar")).status_code == 200
    assert (await enc.client.patch(f"/api/v1/reservas/{rid}/atender")).status_code == 200


def venta_directa(sucursal, items, metodo="EFECTIVO"):
    return {"sucursal_id": sucursal, "metodo": metodo, "items": items}


async def test_venta_directa_ok_y_costo_congelado(cliente_http: AsyncClient):
    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, suc, 10, tag="v1", precio="150.00", costo="60.00")
    cajero = await crear_staff(cliente_http, "CAJERO", suc, tag="v1c")
    try:
        r = await cajero.client.post(
            "/api/v1/ventas/presenciales",
            json=venta_directa(suc, [{"variante_id": var["variante_id"], "cantidad": 2}]),
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text
        comp = r.json()
        assert comp["estado"] == "PAGADA" and comp["canal"] == "PRESENCIAL"
        assert comp["numero"].startswith("VTA-")
        assert comp["subtotal"] == "300.00" and comp["total"] == "300.00"
        assert len(comp["pagos"]) == 1 and comp["pagos"][0]["monto"] == "300.00"
        assert comp["pagos"][0]["metodo"] == "EFECTIVO"
        reg = await _stock(var["variante_id"], suc)
        assert (reg.disponible, reg.reservado) == (8, 0)
        # El costo cambia despues (nueva recepcion a 100), el detalle queda congelado.
        admin_recep = await cliente_http.post(
            "/api/v1/recepciones",
            json={
                "proveedor_id": (await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov v1 {uuid.uuid4().hex[:6]}"})).json()["id"],
                "sucursal_id": suc,
                "recibido_por_id": cajero.id,
                "detalles": [{"variante_id": var["variante_id"], "cantidad": 10, "costo_unitario": "100.00"}],
            },
        )
        assert admin_recep.status_code == 201, admin_recep.text
        comp2 = (await cajero.client.get(f"/api/v1/ventas/{comp['id']}/comprobante")).json()
        assert comp2["detalles"][0]["precio_unitario"] == "150.00"
        assert comp2["detalles"][0]["costo_promedio"] is None  # cajero no ve costos
        comp_admin = (await cliente_http.get(f"/api/v1/ventas/{comp['id']}/comprobante")).json()
        assert comp_admin["detalles"][0]["costo_promedio"] == "60.00"  # congelado
    finally:
        await cajero.client.aclose()


async def test_venta_total_desde_reserva(cliente_http: AsyncClient):
    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, suc, 5, tag="v2", precio="100.00")
    cajero = await crear_staff(cliente_http, "CAJERO", suc, tag="v2c")
    enc = await crear_staff(cliente_http, "ENCARGADO", suc, tag="v2e")
    try:
        async with await crear_cliente("v2") as cli:
            rid = (await post_reserva(cli, bolsa(suc, [(var["variante_id"], 3, None)]))).json()["id"]
            await preparar_atender(enc, rid)
            det_id = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()["detalles"][0]["id"]
            r = await cajero.client.post(
                "/api/v1/ventas/presenciales",
                json={
                    "reserva_id": rid, "sucursal_id": suc, "metodo": "TARJETA_CAJA",
                    "items": [{"detalle_reserva_id": det_id, "variante_id": var["variante_id"], "cantidad": 3}],
                },
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            assert r.status_code == 201, r.text
            comp = r.json()
            assert comp["reserva_codigo"] is not None and comp["total"] == "300.00"
            reserva = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()
            assert reserva["estado"] == "COMPLETADA"
            assert reserva["detalles"][0]["estado_linea"] == "VENDIDA"
            reg = await _stock(var["variante_id"], suc)
            assert (reg.disponible, reg.reservado) == (2, 0)
    finally:
        await cajero.client.aclose()
        await enc.client.aclose()


async def test_venta_parcial_libera_no_comprado(cliente_http: AsyncClient):
    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, suc, 5, tag="v3", precio="80.00")
    cajero = await crear_staff(cliente_http, "CAJERO", suc, tag="v3c")
    enc = await crear_staff(cliente_http, "ENCARGADO", suc, tag="v3e")
    try:
        async with await crear_cliente("v3") as cli:
            rid = (await post_reserva(cli, bolsa(suc, [(var["variante_id"], 4, None)]))).json()["id"]
            await preparar_atender(enc, rid)
            det_id = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()["detalles"][0]["id"]
            r = await cajero.client.post(
                "/api/v1/ventas/presenciales",
                json={
                    "reserva_id": rid, "sucursal_id": suc, "metodo": "QR_CAJA",
                    "items": [{"detalle_reserva_id": det_id, "variante_id": var["variante_id"], "cantidad": 1}],
                },
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            assert r.status_code == 201, r.text
            assert r.json()["total"] == "80.00"
            reserva = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()
            det = reserva["detalles"][0]
            assert det["estado_linea"] == "VENDIDA_PARCIAL"
            assert (det["cantidad_vendida"], det["cantidad_liberada"]) == (1, 3)
            reg = await _stock(var["variante_id"], suc)
            assert (reg.disponible, reg.reservado) == (4, 0)
            async with AsyncSessionLocal() as db:
                tipos = (
                    await db.execute(
                        select(MovimientoInventario.tipo).where(
                            MovimientoInventario.referencia_tipo == "VENTA",
                            MovimientoInventario.referencia_id == uuid.UUID(r.json()["id"]),
                        )
                    )
                ).scalars().all()
                assert sorted(tipos) == ["LIBERACION_RESERVA", "VENTA_PRESENCIAL"]
    finally:
        await cajero.client.aclose()
        await enc.client.aclose()


async def test_venta_reserva_no_atendida_o_vencida_409(cliente_http: AsyncClient):
    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, suc, 5, tag="v4")
    cajero = await crear_staff(cliente_http, "CAJERO", suc, tag="v4c")
    enc = await crear_staff(cliente_http, "ENCARGADO", suc, tag="v4e")
    try:
        async with await crear_cliente("v4") as cli:
            rid = (await post_reserva(cli, bolsa(suc, [(var["variante_id"], 1, None)]))).json()["id"]
            det_id = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()["detalles"][0]["id"]
            carga = {
                "reserva_id": rid, "sucursal_id": suc, "metodo": "EFECTIVO",
                "items": [{"detalle_reserva_id": det_id, "variante_id": var["variante_id"], "cantidad": 1}],
            }
            assert (await cajero.client.post("/api/v1/ventas/presenciales", json=carga, headers={"Idempotency-Key": str(uuid.uuid4())})).status_code == 409
            await preparar_atender(enc, rid)
            await forzar_vencimiento(rid)
            assert (await cajero.client.post("/api/v1/ventas/presenciales", json=carga, headers={"Idempotency-Key": str(uuid.uuid4())})).status_code == 409
            # Y tras expirar, la reserva vencida tampoco se vende.
            assert (await cliente_http.post("/api/v1/reservas/expiracion/ejecutar")).status_code == 200
            assert (await cajero.client.post("/api/v1/ventas/presenciales", json=carga, headers={"Idempotency-Key": str(uuid.uuid4())})).status_code == 409
    finally:
        await cajero.client.aclose()
        await enc.client.aclose()


async def test_adelanto_descontado_una_vez(cliente_http: AsyncClient):
    suc = await crear_sucursal(cliente_http, tag="v5s")
    await activar_adelanto(cliente_http, suc, "MONTO_FIJO", "50.00")
    var = await crear_variante_con_stock(cliente_http, suc, 5, tag="v5", precio="120.00")
    cajero = await crear_staff(cliente_http, "CAJERO", suc, tag="v5c")
    enc = await crear_staff(cliente_http, "ENCARGADO", suc, tag="v5e")
    try:
        async with await crear_cliente("v5") as cli:
            rid = (await post_reserva(cli, bolsa(suc, [(var["variante_id"], 2, None)]))).json()["id"]
            assert (
                await cli.client.post(
                    "/api/v1/pagos/adelantos",
                    json={"reserva_id": rid, "metodo": "EFECTIVO"},
                    headers=cli.headers_clave(),
                )
            ).status_code == 201
            await preparar_atender(enc, rid)
            det_id = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()["detalles"][0]["id"]
            r = await cajero.client.post(
                "/api/v1/ventas/presenciales",
                json={
                    "reserva_id": rid, "sucursal_id": suc, "metodo": "TRANSFERENCIA",
                    "items": [{"detalle_reserva_id": det_id, "variante_id": var["variante_id"], "cantidad": 2}],
                },
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            assert r.status_code == 201, r.text
            comp = r.json()
            assert comp["subtotal"] == "240.00"
            assert comp["adelanto_descontado"] == "50.00"
            assert comp["total"] == "190.00"
            assert comp["pagos"][0]["monto"] == "190.00"
    finally:
        await cajero.client.aclose()
        await enc.client.aclose()


async def test_venta_idempotente_y_permisos(cliente_http: AsyncClient):
    suc = await sucursal_semilla(cliente_http)
    otra = await crear_sucursal(cliente_http, tag="v6o")
    var = await crear_variante_con_stock(cliente_http, suc, 6, tag="v6")
    cajero = await crear_staff(cliente_http, "CAJERO", suc, tag="v6c")
    cajero_otra = await crear_staff(cliente_http, "CAJERO", otra, tag="v6c2")
    try:
        carga = venta_directa(suc, [{"variante_id": var["variante_id"], "cantidad": 1}])
        clave = str(uuid.uuid4())
        r1 = await cajero.client.post("/api/v1/ventas/presenciales", json=carga, headers={"Idempotency-Key": clave})
        assert r1.status_code == 201, r1.text
        r2 = await cajero.client.post("/api/v1/ventas/presenciales", json=carga, headers={"Idempotency-Key": clave})
        assert r2.status_code in (200, 201) and r2.json()["id"] == r1.json()["id"]
        assert r2.json()["numero"] == r1.json()["numero"]
        reg = await _stock(var["variante_id"], suc)
        assert (reg.disponible, reg.reservado) == (5, 0)
        r3 = await cajero.client.post(
            "/api/v1/ventas/presenciales",
            json=venta_directa(suc, [{"variante_id": var["variante_id"], "cantidad": 2}]),
            headers={"Idempotency-Key": clave},
        )
        assert r3.status_code == 409, r3.text
        async with await crear_cliente("v6") as cli:
            assert (
                await cli.client.post("/api/v1/ventas/presenciales", json=carga, headers=cli.headers_clave())
            ).status_code == 403
        assert (
            await cajero_otra.client.post("/api/v1/ventas/presenciales", json=carga, headers={"Idempotency-Key": str(uuid.uuid4())})
        ).status_code == 403
        r_mal = await cajero.client.post(
            "/api/v1/ventas/presenciales",
            json=venta_directa(suc, [{"variante_id": var["variante_id"], "cantidad": 1}], metodo="BITCOIN"),
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r_mal.status_code == 422, r_mal.text
        r_cero = await cajero.client.post(
            "/api/v1/ventas/presenciales",
            json=venta_directa(suc, [{"variante_id": var["variante_id"], "cantidad": 0}]),
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r_cero.status_code == 400, r_cero.text
    finally:
        await cajero.client.aclose()
        await cajero_otra.client.aclose()


async def test_fallo_kardex_revierte_venta(monkeypatch, cliente_http: AsyncClient):
    from httpx import AsyncClient, ASGITransport
    from backend.app.main import app as aplicacion

    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, suc, 5, tag="v7")
    cajero = await crear_staff(cliente_http, "CAJERO", suc, tag="v7c")
    try:
        async with AsyncSessionLocal() as db:
            antes = await db.execute(select(func.count()).select_from(Venta))
            n_antes = antes.scalar()

        async def _roto(self, movimiento):
            raise RuntimeError("Kardex caido")

        monkeypatch.setattr(MovimientoRepository, "registrar", _roto)
        # raise_app_exceptions=False: el 500 llega como respuesta (el
        # ServerErrorMiddleware re-lanza siempre tras responder).
        transporte = ASGITransport(app=aplicacion, raise_app_exceptions=False)
        async with AsyncClient(transport=transporte, base_url="http://test") as anon:
            anon.headers["Authorization"] = f"Bearer {cajero.token}"
            r = await anon.post(
                "/api/v1/ventas/presenciales",
                json=venta_directa(suc, [{"variante_id": var["variante_id"], "cantidad": 2}]),
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
        assert r.status_code == 500, r.text
        reg = await _stock(var["variante_id"], suc)
        assert (reg.disponible, reg.reservado) == (5, 0)
        async with AsyncSessionLocal() as db:
            despues = await db.execute(select(func.count()).select_from(Venta))
            assert despues.scalar() == n_antes
    finally:
        await cajero.client.aclose()
