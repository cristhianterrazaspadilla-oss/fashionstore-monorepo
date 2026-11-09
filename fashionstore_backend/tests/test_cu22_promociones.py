"""CU22 — Promociones: CRUD con RBAC, vigencia UTC, no acumulables, congelación."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.helpers_ciclo2 import (
    crear_cliente, crear_staff, crear_sucursal, crear_variante_con_stock,
    sucursal_semilla,
)
from tests.helpers_ciclo3 import agregar_linea, clave, crear_promocion, hacer_checkout


async def test_crud_promocion_rbac_y_validaciones(cliente_http: AsyncClient):
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_con_stock(admin, suc, 5, tag="p1")
    # Crear OK como admin (código único por corrida).
    promo = await crear_promocion(admin, "PROMO10", "PORCENTAJE", "10.00", [var["variante_id"]])
    assert promo["codigo"].startswith("PROMO10-")
    assert promo["variante_ids"] == [var["variante_id"]]
    # Código duplicado -> 409.
    dup = await admin.post("/api/v1/promociones", json={
        "codigo": promo["codigo"], "nombre": "Otra Promo", "tipo": "PORCENTAJE", "valor": "5.00"})
    assert dup.status_code == 409, dup.text
    # Porcentaje > 100 -> 400.
    mala = await admin.post("/api/v1/promociones", json={
        "codigo": "MAL100", "nombre": "Mala", "tipo": "PORCENTAJE", "valor": "150.00"})
    assert mala.status_code == 400, mala.text
    # Vigencia incoherente (inicio > fin) -> 400.
    ahora = datetime.now(timezone.utc)
    inco = await admin.post("/api/v1/promociones", json={
        "codigo": "INCOH", "nombre": "Incoherente", "tipo": "MONTO_FIJO", "valor": "5.00",
        "vigencia_inicio": (ahora + timedelta(days=2)).isoformat(),
        "vigencia_fin": ahora.isoformat()})
    assert inco.status_code == 400, inco.text
    # Cliente no puede crear -> 403; encargado tampoco.
    async with await crear_cliente("p1c") as cli:
        r = await cli.client.post("/api/v1/promociones", json={
            "codigo": "CLIX", "nombre": "Promo Cliente X", "tipo": "PORCENTAJE", "valor": "5.00"})
        assert r.status_code == 403, r.text
        # ...pero el listado también es solo administración.
        assert (await cli.client.get("/api/v1/promociones")).status_code == 403
    enc = await crear_staff(admin, "ENCARGADO", suc, tag="p1e")
    try:
        r = await enc.client.post("/api/v1/promociones", json={
            "codigo": "ENCX", "nombre": "Promo Encargado", "tipo": "PORCENTAJE", "valor": "5.00"})
        assert r.status_code == 403, r.text
        # Encargado sí puede listar.
        assert (await enc.client.get("/api/v1/promociones")).status_code == 200
    finally:
        await enc.client.aclose()
    # Actualizar y eliminar como admin.
    pid = promo["id"]
    up = await admin.patch(f"/api/v1/promociones/{pid}", json={"valor": "15.00"})
    assert up.status_code == 200 and up.json()["valor"] == "15.00", up.text
    assert (await admin.delete(f"/api/v1/promociones/{pid}")).status_code == 204
    assert (await admin.get(f"/api/v1/promociones/{pid}")).status_code == 404


async def test_asociar_desasociar_variantes(cliente_http: AsyncClient):
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    v1 = await crear_variante_con_stock(admin, suc, 5, tag="pa")
    v2 = await crear_variante_con_stock(admin, suc, 5, tag="pb")
    promo = await crear_promocion(admin, "ASOC1", "MONTO_FIJO", "5.00", [v1["variante_id"]])
    pid = promo["id"]
    # Asociar segunda variante.
    r = await admin.post(f"/api/v1/promociones/{pid}/variantes",
                         json={"variante_ids": [v2["variante_id"]]})
    assert r.status_code == 200, r.text
    assert set(r.json()["variante_ids"]) == {v1["variante_id"], v2["variante_id"]}
    # Asociar variante inexistente -> 404.
    r = await admin.post(f"/api/v1/promociones/{pid}/variantes",
                         json={"variante_ids": [str(uuid.uuid4())]})
    assert r.status_code == 404, r.text
    # Desasociar.
    r = await admin.delete(f"/api/v1/promociones/{pid}/variantes/{v2['variante_id']}")
    assert r.status_code == 200 and r.json()["variante_ids"] == [v1["variante_id"]], r.text
    # Desasociar de nuevo -> 404.
    assert (await admin.delete(
        f"/api/v1/promociones/{pid}/variantes/{v2['variante_id']}")).status_code == 404


async def test_ganadora_mayor_descuento_y_desempate(cliente_http: AsyncClient):
    """No acumulables: gana el mayor descuento; empate -> ID determinista."""
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_con_stock(admin, suc, 10, tag="pg", precio="200.00")
    vid = var["variante_id"]
    p10 = await crear_promocion(admin, "GAN10", "PORCENTAJE", "10.00", [vid])   # 20.00
    p25 = await crear_promocion(admin, "GAN25", "MONTO_FIJO", "25.00", [vid])    # 25.00 x cant
    # Checkout x1: gana MONTO_FIJO 25.
    async with await crear_cliente("pgc") as cli:
        await agregar_linea(cli, vid, 1)
        out = await hacer_checkout(cli, suc, "WEB", "RECOJO")
        venta = (await admin.get(f"/api/v1/ventas/{out['venta_id']}")).json()
        assert venta["descuento"] == "25.00", venta
        assert venta["detalles"][0]["promocion_id"] == p25["id"], venta
        # La futura y la vencida no aplican: crearlas no cambia el resultado.
        await crear_promocion(admin, "FUTURA", "PORCENTAJE", "90.00", [vid],
                              dias_inicio=5, dias_fin=10)
        await crear_promocion(admin, "VENC", "PORCENTAJE", "90.00", [vid],
                              dias_inicio=-10, dias_fin=-5)
        await agregar_linea(cli, vid, 1)
        out2 = await hacer_checkout(cli, suc, "WEB", "RECOJO")
        venta2 = (await admin.get(f"/api/v1/ventas/{out2['venta_id']}")).json()
        assert venta2["detalles"][0]["promocion_id"] == p25["id"], venta2


async def test_descuento_topado_al_subtotal_y_congelacion(cliente_http: AsyncClient):
    """Monto fijo mayor al subtotal se topa; la promo queda congelada en la venta."""
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_con_stock(admin, suc, 10, tag="pt", precio="30.00")
    vid = var["variante_id"]
    promo = await crear_promocion(admin, "TOPADA", "MONTO_FIJO", "100.00", [vid])
    async with await crear_cliente("ptc") as cli:
        await agregar_linea(cli, vid, 1)
        out = await hacer_checkout(cli, suc, "WEB", "RECOJO")
        venta = (await admin.get(f"/api/v1/ventas/{out['venta_id']}")).json()
        assert venta["subtotal"] == "30.00", venta
        assert venta["descuento"] == "30.00", venta  # topada, nunca mayor
        assert venta["total"] == "0.00", venta
        det = venta["detalles"][0]
        assert det["descuento"] == "30.00" and det["promocion_id"] == promo["id"], venta
        # Congelación histórica: desactivar la promo no cambia la venta.
        await admin.patch(f"/api/v1/promociones/{promo['id']}", json={"activa": False})
        venta2 = (await admin.get(f"/api/v1/ventas/{out['venta_id']}")).json()
        assert venta2["descuento"] == "30.00"
        assert venta2["detalles"][0]["promocion_id"] == promo["id"], venta2
