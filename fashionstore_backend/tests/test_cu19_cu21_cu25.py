"""CU19 — Dashboard con importes conocidos + CU21/CU25 IA administrativa."""
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from backend.app.core.config import settings
from tests.helpers_ciclo2 import (
    crear_cliente, crear_staff, crear_sucursal, crear_variante_con_stock,
    sucursal_semilla,
)
from tests.helpers_ciclo3 import agregar_linea, clave, hacer_checkout


async def _venta_pagada(cli, suc, var, cantidad, precio="100.00"):
    await agregar_linea(cli, var["variante_id"], cantidad)
    out = await hacer_checkout(cli, suc, "WEB", "RECOJO")
    # Pago directo en pruebas: aprobar vía servicios (sin Stripe) es costoso;
    # el dashboard cuenta PAGADA, así que marcamos con SQL de prueba.
    from backend.app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                text("UPDATE comercial.ventas SET estado='PAGADA', confirmada_en=now() "
                     "WHERE id=:v"), {"v": out["venta_id"]})
    return out


async def test_dashboard_importes_conocidos_y_rbac(cliente_http: AsyncClient):
    admin = cliente_http
    suc = await crear_sucursal(admin, tag="dash")
    enc = await crear_staff(admin, "ENCARGADO", suc, tag="dash")
    try:
        var = await crear_variante_con_stock(admin, suc, 20, tag="dash",
                                             precio="100.00", costo="40.00")
        async with await crear_cliente("dash") as cli:
            await _venta_pagada(cli, suc, var, 2)  # 200 - costo 80
            await _venta_pagada(cli, suc, var, 1)  # 100 - costo 40
            r = await admin.get("/api/v1/reportes/dashboard", params={"sucursal": suc})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["ventas_total"] == 2, d
            assert d["ingresos_total"] == "300.00", d
            assert d["margen_bruto_total"] == "180.00", d
            assert d["ticket_promedio"] == "150.00", d
            assert any(p["unidades"] == 3 for p in d["top_productos"]), d
            assert "conversion_reservas" in d and "estados_pedidos" in d
            assert "efectividad_promociones" in d
            assert float(d["valorizacion_total"]) > 0, d
            # Encargado de la sucursal OK; cliente y cajero -> 403.
            assert (await enc.client.get("/api/v1/reportes/dashboard",
                                         params={"sucursal": suc})).status_code == 200
            otra = await crear_sucursal(admin, tag="dash2")
            assert (await enc.client.get("/api/v1/reportes/dashboard",
                                         params={"sucursal": otra})).status_code == 403
            assert (await cli.client.get("/api/v1/reportes/dashboard")).status_code == 403
    finally:
        await enc.client.aclose()


async def test_cu21_reporte_funcion_cerrada_y_auditoria(
    cliente_http: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    # Las pruebas nunca consumen Gemini real, aunque el entorno local tenga clave.
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_con_stock(admin, suc, 6, tag="rep", precio="100.00", costo="40.00")
    async with await crear_cliente("rep") as cli:
        await _venta_pagada(cli, suc, var, 1)
        r = await admin.post("/api/v1/ia/reportes",
                             json={"consulta": "¿qué sucursal vendió menos este mes?"})
        assert r.status_code == 200, r.text
        dto = r.json()
        assert dto["funcion_usada"] in (
            "ventasPorSucursal", "ventasPorTemporada", "stockCritico",
            "topVendidos", "efectividadReservas", "rotacionPorTemporada"), dto
        assert isinstance(dto["datos"], dict) and dto["narrativa"], dto
        assert dto["proveedor"] == "DETERMINISTA"
        inventario = await admin.post(
            "/api/v1/ia/reportes",
            json={"consulta": "inventario por sucursal"},
        )
        assert inventario.status_code == 200, inventario.text
        reporte_inventario = inventario.json()
        assert reporte_inventario["funcion_usada"] == "inventarioPorSucursal"
        assert reporte_inventario["datos"]["inventario_por_sucursal"], reporte_inventario
        assert any(
            fila["disponible"] >= 6
            for fila in reporte_inventario["datos"]["inventario_por_sucursal"]
        )
        # Cliente no puede pedir reportes -> 403.
        assert (await cli.client.post("/api/v1/ia/reportes",
                                      json={"consulta": "ventas"})).status_code == 403


async def test_cu25_solo_recomienda_sin_mutar(cliente_http: AsyncClient):
    from backend.app.core.database import AsyncSessionLocal

    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_con_stock(admin, suc, 12, tag="dec", precio="100.00", costo="40.00")
    async with AsyncSessionLocal() as db:
        n_ventas0 = (await db.execute(text("SELECT count(*) FROM comercial.ventas"))).scalar()
        n_promo0 = (await db.execute(text("SELECT count(*) FROM catalogo.promociones"))).scalar()
    r = await admin.post("/api/v1/ia/decisiones-inventario",
                         json={"dias_ventana": 30, "umbral_rotacion": 50})
    assert r.status_code == 200, r.text
    dto = r.json()
    assert dto["items"], dto
    assert {i["accion"] for i in dto["items"]} <= {
        "PROMOCION", "LIQUIDACION", "TRASLADO", "REPOSICION", "MANTENER"}, dto
    # Dead-stock (12 un. sin ventas, umbral 50) sugiere PROMOCION, no crea nada.
    fila = next(i for i in dto["items"] if i["variante_id"] == var["variante_id"])
    assert fila["accion"] == "PROMOCION", fila
    async with AsyncSessionLocal() as db:
        assert (await db.execute(text("SELECT count(*) FROM comercial.ventas"))).scalar() == n_ventas0
        assert (await db.execute(text("SELECT count(*) FROM catalogo.promociones"))).scalar() == n_promo0
        assert (await db.execute(
            text("SELECT count(*) FROM inventario.movimientos_inventario "
                 "WHERE tipo IN ('VENTA_DIGITAL','COMPROMISO_DIGITAL') "
                 "AND referencia_id IN (SELECT id FROM comercial.ventas WHERE cliente_id IS NULL)"))
        ).scalar() == 0
