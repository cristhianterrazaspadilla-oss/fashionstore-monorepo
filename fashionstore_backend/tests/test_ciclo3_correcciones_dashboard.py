"""Corrección 7 — Dashboard con filtros estrictos (desde/hasta/sucursal/UTC)."""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import text

from backend.app.core.database import AsyncSessionLocal
from tests.helpers_ciclo2 import (
    crear_cliente, crear_staff, crear_sucursal, crear_variante_con_stock,
)
from tests.helpers_ciclo3 import agregar_linea, hacer_checkout


async def _venta_pagada_en(cli, suc, var, cantidad, cuando: datetime):
    await agregar_linea(cli, var["variante_id"], cantidad)
    out = await hacer_checkout(cli, suc, "WEB", "RECOJO")
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                text("UPDATE comercial.ventas SET estado='PAGADA', confirmada_en=:c, creada_en=:c "
                     "WHERE id=:v"),
                {"c": cuando, "v": out["venta_id"]},
            )
            await db.execute(
                text("UPDATE comercial.pedidos_entrega SET creada_en=:c WHERE venta_id=:v"),
                {"c": cuando, "v": out["venta_id"]},
            )
    return out


async def test_dashboard_respeta_filtros_y_no_contamina(cliente_http: AsyncClient):
    admin = cliente_http
    s1 = await crear_sucursal(admin, tag="flt1")
    s2 = await crear_sucursal(admin, tag="flt2")
    v1 = await crear_variante_con_stock(admin, s1, 20, tag="flt1", precio="100.00", costo="40.00")
    v2 = await crear_variante_con_stock(admin, s2, 20, tag="flt2", precio="100.00", costo="40.00")
    ahora = datetime.now(timezone.utc)
    dentro = ahora - timedelta(days=5)
    fuera = ahora - timedelta(days=60)
    async with await crear_cliente("flt") as cli:
        await _venta_pagada_en(cli, s1, v1, 2, dentro)   # 200 dentro, s1
        await _venta_pagada_en(cli, s2, v2, 1, dentro)   # 100 dentro, s2
        await _venta_pagada_en(cli, s1, v1, 1, fuera)    # 100 fuera, s1 (no contamina)
        desde = (ahora - timedelta(days=10)).isoformat()
        hasta = ahora.isoformat()
        # Filtro por sucursal s1 y periodo: solo 1 venta (200); la de fuera no contamina.
        r = await admin.get("/api/v1/reportes/dashboard",
                            params={"sucursal": s1, "desde": desde, "hasta": hasta})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ventas_total"] == 1, d
        assert d["ingresos_total"] == "200.00", d
        assert d["margen_bruto_total"] == "120.00", d  # 200 - 80
        # Sucursal s2 con el mismo periodo: solo su venta dentro (100).
        r2 = await admin.get("/api/v1/reportes/dashboard",
                             params={"sucursal": s2, "desde": desde, "hasta": hasta})
        assert r2.status_code == 200, r2.text
        assert r2.json()["ventas_total"] == 1, r2.json()
        assert r2.json()["ingresos_total"] == "100.00", r2.json()
        # Periodo amplio que incluye la venta fuera: s1 pasa a 2 ventas (300).
        desde_amplio = (ahora - timedelta(days=70)).isoformat()
        r4 = await admin.get("/api/v1/reportes/dashboard",
                             params={"sucursal": s1, "desde": desde_amplio, "hasta": hasta})
        assert r4.status_code == 200, r4.text
        assert r4.json()["ventas_total"] == 2, r4.json()
        assert r4.json()["ingresos_total"] == "300.00", r4.json()
        # Reserva fuera de periodo / otra sucursal no contamina conversión.
        async with AsyncSessionLocal() as db:
            async with db.begin():
                await db.execute(
                    text("UPDATE comercial.reservas SET fecha_creacion=:f WHERE id IN "
                         "(SELECT id FROM comercial.reservas ORDER BY fecha_creacion DESC LIMIT 1)"),
                    {"f": fuera},
                )
        # desde > hasta -> 400.
        r3 = await admin.get("/api/v1/reportes/dashboard",
                             params={"desde": hasta, "hasta": desde})
        assert r3.status_code == 400, r3.text
