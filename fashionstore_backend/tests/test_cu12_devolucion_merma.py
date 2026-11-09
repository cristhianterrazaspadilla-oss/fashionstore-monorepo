"""CU12 — Devoluciones y mermas (RF22).

Acumuladas con tope, costo congelado, causa/responsable, idempotencia,
permisos y rollback.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select, func
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.ventas_pagos.models import Venta
from backend.app.core.modules.posventa.services.devolucion_service import Devolucion
from tests.helpers_ciclo2 import (
    bolsa,
    crear_cliente,
    crear_staff,
    post_reserva,
    preparar_atender,
    sucursal_semilla,
    crear_variante_con_stock,
    vender_reserva,
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


async def _flujo_venta(admin, tag, cantidad=4, precio="100.00", costo="40.00"):
    """Reserva -> atiende -> vende todo. Retorna (suc, var, venta, detalle_venta)."""
    suc = await sucursal_semilla(admin)
    var = await crear_variante_con_stock(admin, suc, cantidad, tag=tag, precio=precio, costo=costo)
    cajero = await crear_staff(admin, "CAJERO", suc, tag=f"{tag}c")
    enc = await crear_staff(admin, "ENCARGADO", suc, tag=f"{tag}e")
    cli = await crear_cliente(tag)
    creada_reserva = await post_reserva(
        cli, bolsa(suc, [(var["variante_id"], cantidad, None)])
    )
    assert creada_reserva.status_code == 201, creada_reserva.text
    rid = creada_reserva.json()["id"]
    await preparar_atender(enc.client, rid)
    det_reserva = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()["detalles"][0]["id"]
    comp = await vender_reserva(cajero, rid, suc, [(det_reserva, var["variante_id"], cantidad)])
    return suc, var, comp, cajero, enc, cli


async def test_devolucion_parcial_y_acumulada_hasta_total(cliente_http: AsyncClient):
    suc, var, comp, cajero, enc, cli = await _flujo_venta(cliente_http, tag="d1")
    try:
        det_venta = comp["detalles"][0]["id"]
        r1 = await enc.client.post(
            "/api/v1/devoluciones",
            json={"detalle_venta_id": det_venta, "cantidad": 1, "motivo": "Talla"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r1.status_code == 201, r1.text
        assert Decimal(str(r1.json()["costo_unitario"])) == Decimal("40.00")
        reg = await _stock(var["variante_id"], suc)
        assert reg.disponible == 1
        venta = (await enc.client.get(f"/api/v1/ventas/{comp['id']}")).json()
        assert venta["estado"] == "PARCIALMENTE_DEVUELTA"
        # Acumula hasta el total vendido (4): 1 + 3.
        r2 = await enc.client.post(
            "/api/v1/devoluciones",
            json={"detalle_venta_id": det_venta, "cantidad": 3},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r2.status_code == 201, r2.text
        venta = (await enc.client.get(f"/api/v1/ventas/{comp['id']}")).json()
        assert venta["estado"] == "DEVUELTA"
        reg = await _stock(var["variante_id"], suc)
        assert reg.disponible == 4
        # Exceso sobre lo vendido -> 409.
        r3 = await enc.client.post(
            "/api/v1/devoluciones",
            json={"detalle_venta_id": det_venta, "cantidad": 1},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r3.status_code == 409, r3.text
        async with AsyncSessionLocal() as db:
            n = await db.execute(
                select(func.count()).select_from(MovimientoInventario).where(
                    MovimientoInventario.tipo == "DEVOLUCION",
                    MovimientoInventario.referencia_tipo == "DETALLE_VENTA",
                    MovimientoInventario.referencia_id == uuid.UUID(det_venta),
                )
            )
            assert n.scalar() == 2
    finally:
        await cajero.client.aclose()
        await enc.client.aclose()
        await cli.client.aclose()


async def test_listas_posventa_propias_tienen_rutas_y_aislamiento_de_cliente(
    cliente_http: AsyncClient,
):
    sucursal_id = await sucursal_semilla(cliente_http)
    cliente = await crear_cliente("posventa-mias")
    otro_cliente = await crear_cliente("posventa-otro")
    try:
        async with AsyncSessionLocal() as db:
            usuario = await db.get(Usuario, uuid.UUID(cliente.id))
            assert usuario is not None and usuario.empresa_id is not None
            venta_id = uuid.uuid4()
            devolucion_id = uuid.uuid4()
            creada_en = datetime.now(timezone.utc)
            db.add(
                Venta(
                    id=venta_id,
                    empresa_id=usuario.empresa_id,
                    numero=f"POS-{uuid.uuid4().hex[:16]}",
                    cliente_id=usuario.id,
                    sucursal_id=uuid.UUID(sucursal_id),
                    canal="WEB",
                    estado="PAGADA",
                    subtotal=100,
                    descuento=0,
                    costo_entrega=0,
                    total=100,
                    creada_en=creada_en,
                    confirmada_en=creada_en,
                    entregada_en=creada_en,
                )
            )
            await db.flush()
            db.add(
                Devolucion(
                    id=devolucion_id,
                    empresa_id=usuario.empresa_id,
                    venta_id=venta_id,
                    cliente_id=usuario.id,
                    sucursal_id=uuid.UUID(sucursal_id),
                    estado="SOLICITADA",
                    motivo_codigo="TALLA",
                    motivo_descripcion="Prueba de aislamiento de consulta",
                    solicitada_en=creada_en,
                )
            )
            await db.commit()
        devolucion_id_texto = str(devolucion_id)

        propias = await cliente.client.get("/api/v1/devoluciones/mias")
        assert propias.status_code == 200, propias.text
        assert [item["id"] for item in propias.json()] == [devolucion_id_texto]

        ajenas = await otro_cliente.client.get("/api/v1/devoluciones/mias")
        assert ajenas.status_code == 200, ajenas.text
        assert all(item["id"] != devolucion_id_texto for item in ajenas.json())
        ajena = await otro_cliente.client.get(f"/api/v1/devoluciones/{devolucion_id_texto}")
        assert ajena.status_code == 404, ajena.text

        cambios = await cliente.client.get("/api/v1/cambios/mios")
        assert cambios.status_code == 200, cambios.text
        assert cambios.json() == []
        reembolsos = await cliente.client.get("/api/v1/reembolsos/mios")
        assert reembolsos.status_code == 200, reembolsos.text
        assert reembolsos.json() == []
        saldo = await cliente.client.get("/api/v1/saldos/mio")
        assert saldo.status_code == 200, saldo.text
    finally:
        await cliente.client.aclose()
        await otro_cliente.client.aclose()


async def test_cu20_solicitud_inspeccion_idempotencia_y_stock(
    cliente_http: AsyncClient,
):
    suc, var, comp, cajero, enc, cli = await _flujo_venta(
        cliente_http, tag="cu20-flow", cantidad=3
    )
    try:
        detalle_id = comp["detalles"][0]["id"]
        venta_id = comp["id"]
        stock_antes = await _stock(var["variante_id"], suc)
        assert stock_antes.disponible == 0

        solicitud = {
            "venta_id": venta_id,
            "lineas": [{"detalle_venta_id": detalle_id, "cantidad": 1}],
            "motivo_codigo": "TALLA",
        }
        clave_solicitud = str(uuid.uuid4())
        creada = await cli.client.post(
            "/api/v1/devoluciones/solicitudes",
            json=solicitud,
            headers={"Idempotency-Key": clave_solicitud},
        )
        assert creada.status_code == 201, creada.text
        devolucion_id = creada.json()["id"]
        assert creada.json()["estado"] == "SOLICITADA"

        repetida = await cli.client.post(
            "/api/v1/devoluciones/solicitudes",
            json=solicitud,
            headers={"Idempotency-Key": clave_solicitud},
        )
        assert repetida.status_code == 201, repetida.text
        assert repetida.json()["id"] == devolucion_id

        distinta = {**solicitud, "lineas": [{"detalle_venta_id": detalle_id, "cantidad": 2}]}
        conflicto = await cli.client.post(
            "/api/v1/devoluciones/solicitudes",
            json=distinta,
            headers={"Idempotency-Key": clave_solicitud},
        )
        assert conflicto.status_code == 409, conflicto.text

        propias = await cli.client.get("/api/v1/devoluciones/mias")
        assert propias.status_code == 200, propias.text
        assert sum(item["id"] == devolucion_id for item in propias.json()) == 1
        stock_solicitada = await _stock(var["variante_id"], suc)
        assert stock_solicitada.disponible == 0  # custodia no se vende antes del dictamen

        inspeccion = {
            "condicion_fisica": "BUENA",
            "responsabilidad_tienda": True,
            "dictamen": "APROBADA_REPOSICION",
        }
        clave_inspeccion = str(uuid.uuid4())
        recibida = await enc.client.post(
            f"/api/v1/devoluciones/{devolucion_id}/inspecciones",
            json=inspeccion,
            headers={"Idempotency-Key": clave_inspeccion},
        )
        assert recibida.status_code == 200, recibida.text
        assert recibida.json()["estado"] == "APROBADA_REPOSICION"
        assert recibida.json()["detalles"][0]["cantidad_aceptada"] == 1

        reintento_inspeccion = await enc.client.post(
            f"/api/v1/devoluciones/{devolucion_id}/inspecciones",
            json=inspeccion,
            headers={"Idempotency-Key": clave_inspeccion},
        )
        assert reintento_inspeccion.status_code == 200, reintento_inspeccion.text
        assert reintento_inspeccion.json()["id"] == devolucion_id
        stock_repuesto = await _stock(var["variante_id"], suc)
        assert stock_repuesto.disponible == 1  # el reintento no acredita otra unidad
    finally:
        await cajero.client.aclose()
        await enc.client.aclose()
        await cli.client.aclose()


async def test_devolucion_idempotente_y_permisos(cliente_http: AsyncClient):
    suc, var, comp, cajero, enc, cli = await _flujo_venta(cliente_http, tag="d2")
    try:
        det_venta = comp["detalles"][0]["id"]
        clave = str(uuid.uuid4())
        carga = {"detalle_venta_id": det_venta, "cantidad": 1}
        a = await enc.client.post("/api/v1/devoluciones", json=carga, headers={"Idempotency-Key": clave})
        assert a.status_code == 201, a.text
        b = await enc.client.post("/api/v1/devoluciones", json=carga, headers={"Idempotency-Key": clave})
        assert b.status_code in (200, 201) and b.json()["id"] == a.json()["id"]
        c = await enc.client.post(
            "/api/v1/devoluciones",
            json={"detalle_venta_id": det_venta, "cantidad": 2},
            headers={"Idempotency-Key": clave},
        )
        assert c.status_code == 409, c.text
        assert (
            await cli.client.post("/api/v1/devoluciones", json=carga, headers=cli.headers_clave())
        ).status_code == 403
        assert (
            await cajero.client.post("/api/v1/devoluciones", json=carga, headers={"Idempotency-Key": str(uuid.uuid4())})
        ).status_code == 403
    finally:
        await cajero.client.aclose()
        await enc.client.aclose()
        await cli.client.aclose()


async def test_merma_ok_sin_causa_400_y_permisos(cliente_http: AsyncClient):
    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, suc, 6, tag="d3")
    enc = await crear_staff(cliente_http, "ENCARGADO", suc, tag="d3e")
    try:
        r = await enc.client.post(
            "/api/v1/mermas",
            json={"variante_id": var["variante_id"], "sucursal_id": suc, "cantidad": 2, "causa": "Dano por humedad"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text
        assert r.json()["responsable_id"] == enc.id
        reg = await _stock(var["variante_id"], suc)
        assert reg.disponible == 4  # no reingresa a ningun otro bucket
        assert (reg.reservado, reg.comprometido_traslado, reg.en_transito) == (0, 0, 0)
        # Sin causa -> 400.
        r2 = await enc.client.post(
            "/api/v1/mermas",
            json={"variante_id": var["variante_id"], "sucursal_id": suc, "cantidad": 1},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r2.status_code == 400, r2.text
        # Exceso -> 409. Cantidad cero -> 400.
        r3 = await enc.client.post(
            "/api/v1/mermas",
            json={"variante_id": var["variante_id"], "sucursal_id": suc, "cantidad": 99, "causa": "X"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r3.status_code == 409
        r4 = await enc.client.post(
            "/api/v1/mermas",
            json={"variante_id": var["variante_id"], "sucursal_id": suc, "cantidad": 0, "causa": "X"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r4.status_code == 422
        async with await crear_cliente("d3") as cli:
            assert (
                await cli.client.post(
                    "/api/v1/mermas",
                    json={"variante_id": var["variante_id"], "sucursal_id": suc, "cantidad": 1, "causa": "X"},
                    headers=cli.headers_clave(),
                )
            ).status_code == 403
        # Repetir misma clave+payload no duplica.
        clave = str(uuid.uuid4())
        m1 = await enc.client.post(
            "/api/v1/mermas",
            json={"variante_id": var["variante_id"], "sucursal_id": suc, "cantidad": 1, "causa": "Rotura"},
            headers={"Idempotency-Key": clave},
        )
        m2 = await enc.client.post(
            "/api/v1/mermas",
            json={"variante_id": var["variante_id"], "sucursal_id": suc, "cantidad": 1, "causa": "Rotura"},
            headers={"Idempotency-Key": clave},
        )
        assert m1.status_code == 201 and m2.status_code in (200, 201)
        assert m1.json()["id"] == m2.json()["id"]
        reg = await _stock(var["variante_id"], suc)
        assert reg.disponible == 3
    finally:
        await enc.client.aclose()


async def test_fallo_kardex_revierte_devolucion(monkeypatch, cliente_http: AsyncClient):
    from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository

    suc, var, comp, cajero, enc, cli = await _flujo_venta(cliente_http, tag="d4")
    try:
        det_venta = comp["detalles"][0]["id"]

        async def _roto(self, movimiento):
            raise RuntimeError("Kardex caido")

        monkeypatch.setattr(MovimientoRepository, "registrar", _roto)
        from httpx import AsyncClient, ASGITransport
        from backend.app.main import app as aplicacion

        transporte = ASGITransport(app=aplicacion, raise_app_exceptions=False)
        async with AsyncClient(transport=transporte, base_url="http://test") as anon:
            anon.headers["Authorization"] = f"Bearer {enc.token}"
            r = await anon.post(
                "/api/v1/devoluciones",
                json={"detalle_venta_id": det_venta, "cantidad": 1},
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
        assert r.status_code == 500, r.text
        reg = await _stock(var["variante_id"], suc)
        assert reg.disponible == 0
    finally:
        await cajero.client.aclose()
        await enc.client.aclose()
        await cli.client.aclose()
