"""CU13/CU23 — Historial del cliente y ventas por sucursal + contrato OpenAPI.

Filtros, orden (creada_en desc), paginacion, costos por rol y
verificacion del contrato Ciclo 2 + presencia de rutas Ciclo 3 (Puerta B).
"""
from httpx import AsyncClient
from tests.helpers_ciclo2 import (
    bolsa,
    crear_cliente,
    crear_staff,
    crear_sucursal,
    crear_variante_con_stock,
    post_reserva,
    preparar_atender,
    sucursal_semilla,
    vender_reserva,
)


async def _dos_ventas(admin, tag="h"):
    suc = await crear_sucursal(admin, tag=f"{tag}s")
    var = await crear_variante_con_stock(admin, suc, 10, tag=tag, precio="100.00", costo="40.00")
    cajero = await crear_staff(admin, "CAJERO", suc, tag=f"{tag}c")
    enc = await crear_staff(admin, "ENCARGADO", suc, tag=f"{tag}e")
    cli = await crear_cliente(tag)
    rid = (await post_reserva(cli, bolsa(suc, [(var["variante_id"], 2, None)]))).json()["id"]
    await preparar_atender(enc.client, rid)
    det = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()["detalles"][0]["id"]
    comp1 = await vender_reserva(cajero, rid, suc, [(det, var["variante_id"], 2)])
    r2 = await cajero.client.post(
        "/api/v1/ventas/presenciales",
        json={
            "sucursal_id": suc, "cliente_id": cli.id, "metodo": "EFECTIVO",
            "items": [{"variante_id": var["variante_id"], "cantidad": 1}],
        },
        headers={"Idempotency-Key": __import__("uuid").uuid4().hex},
    )
    assert r2.status_code == 201, r2.text
    return suc, var, cli, cajero, enc, comp1, r2.json()


async def test_historial_propio_paginado_y_permisos(cliente_http: AsyncClient):
    suc, var, cli, cajero, enc, comp1, comp2 = await _dos_ventas(cliente_http, tag="h1")
    try:
        h = await cli.client.get(f"/api/v1/clientes/{cli.id}/compras")
        assert h.status_code == 200, h.text
        assert h.json()["total"] == 2
        assert {i["id"] for i in h.json()["items"]} == {comp1["id"], comp2["id"]}
        # Sin costos para el cliente.
        assert all(d["costo_promedio"] is None for v in h.json()["items"] for d in v["detalles"])
        p1 = await cli.client.get(f"/api/v1/clientes/{cli.id}/compras", params={"limit": 1})
        assert p1.json()["total"] == 2 and len(p1.json()["items"]) == 1
        # Otro cliente -> 403; admin ve costos.
        async with await crear_cliente("h1b") as otro:
            assert (await otro.client.get(f"/api/v1/clientes/{cli.id}/compras")).status_code == 403
        ha = await cliente_http.get(f"/api/v1/clientes/{cli.id}/compras")
        assert ha.status_code == 200
        assert all(d["costo_promedio"] == "40.00" for v in ha.json()["items"] for d in v["detalles"])
        # Encargado no es propietario ni admin -> 403.
        assert (await enc.client.get(f"/api/v1/clientes/{cli.id}/compras")).status_code == 403
    finally:
        await cli.client.aclose()
        await cajero.client.aclose()
        await enc.client.aclose()


async def test_ventas_sucursal_resumen_y_ambito(cliente_http: AsyncClient):
    suc, var, cli, cajero, enc, comp1, comp2 = await _dos_ventas(cliente_http, tag="h2")
    otra = await crear_sucursal(cliente_http, tag="h2o")
    enc_otra = await crear_staff(cliente_http, "ENCARGADO", otra, tag="h2e")
    try:
        r = await enc.client.get("/api/v1/reportes/ventas-sucursal", params={"sucursal": suc})
        assert r.status_code == 200, r.text
        datos = r.json()
        assert datos["total"] == 2
        assert datos["resumen"]["monto_total"] == "300.00"  # 200 + 100
        assert datos["resumen"]["unidades"] == 3
        assert datos["resumen"]["ticket_promedio"] == "150.00"
        assert datos["resumen"]["costo_total"] == "120.00"  # 3 x 40
        assert datos["resumen"]["margen_bruto_total"] == "180.00"
        assert (await enc.client.get("/api/v1/reportes/ventas-sucursal", params={"sucursal": otra})).status_code == 403
        assert (await enc_otra.client.get("/api/v1/reportes/ventas-sucursal", params={"sucursal": suc})).status_code == 403
        assert (await cli.client.get("/api/v1/reportes/ventas-sucursal", params={"sucursal": suc})).status_code == 403
        assert (await cajero.client.get("/api/v1/reportes/ventas-sucursal", params={"sucursal": suc})).status_code == 403
        ra = await cliente_http.get("/api/v1/reportes/ventas-sucursal", params={"sucursal": suc})
        assert ra.status_code == 200 and ra.json()["total"] == 2
        # Rango futuro vacio.
        rf = await enc.client.get(
            "/api/v1/reportes/ventas-sucursal",
            params={"sucursal": suc, "desde": "2099-01-01T00:00:00Z"},
        )
        assert rf.status_code == 200 and rf.json()["total"] == 0
    finally:
        await cli.client.aclose()
        await cajero.client.aclose()
        await enc.client.aclose()
        await enc_otra.client.aclose()


async def test_openapi_contrato_ciclo2_sin_ciclo3(cliente_http: AsyncClient):
    r = await cliente_http.get("/api/v1/openapi.json")
    assert r.status_code == 200
    paths = set(r.json()["paths"].keys())
    esperadas = [
        "/api/v1/reservas", "/api/v1/reservas/{reserva_id}",
        "/api/v1/reservas/codigo/{codigo}", "/api/v1/reservas/{reserva_id}/cancelar",
        "/api/v1/reservas/{reserva_id}/preparar", "/api/v1/reservas/{reserva_id}/atender",
        "/api/v1/reservas/panel/cola", "/api/v1/reservas/expiracion/ejecutar",
        "/api/v1/pagos/adelantos", "/api/v1/traslados/solicitudes",
        "/api/v1/traslados", "/api/v1/traslados/{traslado_id}",
        "/api/v1/traslados/{traslado_id}/aprobar", "/api/v1/traslados/{traslado_id}/rechazar",
        "/api/v1/traslados/{traslado_id}/despachar", "/api/v1/traslados/{traslado_id}/recibir",
        "/api/v1/ventas/presenciales", "/api/v1/ventas/{venta_id}",
        "/api/v1/ventas/{venta_id}/comprobante", "/api/v1/devoluciones",
        "/api/v1/mermas", "/api/v1/clientes/{cliente_id}/compras",
        "/api/v1/reportes/ventas-sucursal",
    ]
    for ruta in esperadas:
        assert ruta in paths, f"falta {ruta}"
    # Puerta B Ciclo 3: el contrato aprobado YA expone las rutas digitales.
    # (Antes prohibidas en Ciclo 2; ver test_openapi_contrato_ciclo3_presente.)
    esperadas_ciclo3 = [
        "/api/v1/carritos/mio", "/api/v1/carritos/mio/lineas",
        "/api/v1/carritos/mio/checkout", "/api/v1/promociones",
        "/api/v1/pagos/stripe/intenciones", "/api/v1/pagos/stripe/webhook",
        "/api/v1/entregas/cotizacion", "/api/v1/entregas/cola",
        "/api/v1/ia/recomendaciones", "/api/v1/ia/busqueda",
        "/api/v1/probador/autorizaciones",
        "/api/v1/variantes/{variante_id}/prueba-virtual",
        "/api/v1/reportes/dashboard",
    ]
    for ruta in esperadas_ciclo3:
        assert ruta in paths, f"falta ruta Ciclo 3 {ruta}"


async def test_openapi_tipos_y_paginacion_corregidos(cliente_http: AsyncClient):
    r = await cliente_http.get("/api/v1/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    # 1. creada_en como string/date-time en VentaSucursalItemDTO.
    item = spec["components"]["schemas"]["VentaSucursalItemDTO"]["properties"]["creada_en"]
    assert item.get("type") == "string", item
    assert item.get("format") == "date-time", item
    # 2. GET /traslados referencia TrasladoListaDTO (total/limit/offset/items).
    get_traslados = spec["paths"]["/api/v1/traslados"]["get"]
    ref = get_traslados["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("TrasladoListaDTO"), ref
    lista = spec["components"]["schemas"]["TrasladoListaDTO"]
    assert set(lista["required"]) == {"total", "limit", "offset", "items"}
    assert lista["properties"]["items"]["items"]["$ref"].endswith("TrasladoDTO")
