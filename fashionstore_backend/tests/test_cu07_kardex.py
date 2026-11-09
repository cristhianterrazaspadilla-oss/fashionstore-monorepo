"""
CU07 — Registrar Kardex, inventario por sucursal y valorización de costos (RF21, RF22, RF26)
Contratos SKILL.md CU07:
Presentación consultarKardex(), consultarExistencias(), consultarValorizacion()
Controller InventarioService.kardexPorVariante()/existenciasPorSucursal()/valorizacion()
Datos MovimientoRepository.listar(), InventarioRepository.existencias()
"""
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.modules.catalogo.models import Categoria, Talla, Color, Producto, VarianteProducto
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from tests.helpers_ciclo2 import EMPRESA_TEST_ID, crear_ciudad_plataforma
from backend.app.core.modules.inventario.services.inventario_service import InventarioService
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository


async def _obtener_ciudad_sucursal(cliente_http: AsyncClient):
    resp_list = await cliente_http.get("/api/v1/sucursales")
    sucursales = resp_list.json()
    if sucursales:
        return sucursales[0]["id"]
    uid = uuid.uuid4().hex[:6]
    ciudad = await crear_ciudad_plataforma(f"Ciudad CU07 {uid}")
    ciudad_id = ciudad["id"]
    payload = {
        "ciudad_id": ciudad_id,
        "nombre": f"Sucursal CU07 {uid}",
        "direccion": "Av. test CU07 123",
        "numero_anillo": 3,
        "tarifa_base_delivery": "10.00",
        "incremento_anillo_delivery": "2.00",
    }
    resp_suc = await cliente_http.post("/api/v1/sucursales", json=payload)
    assert resp_suc.status_code == 201, resp_suc.text
    return resp_suc.json()["id"]


async def _crear_sucursal_extra(cliente_http: AsyncClient):
    uid = uuid.uuid4().hex[:6]
    ciudad = await crear_ciudad_plataforma(f"Ciudad Extra CU07 {uid}")
    ciudad_id = ciudad["id"]
    payload = {
        "ciudad_id": ciudad_id,
        "nombre": f"Sucursal Extra CU07 {uid}",
        "direccion": "Av. extra 999",
        "numero_anillo": 5,
        "tarifa_base_delivery": "12.00",
        "incremento_anillo_delivery": "1.50",
    }
    resp_suc = await cliente_http.post("/api/v1/sucursales", json=payload)
    assert resp_suc.status_code == 201
    return resp_suc.json()["id"]


async def _crear_usuario_receptor(cliente_http: AsyncClient):
    resp_suc = await cliente_http.get("/api/v1/sucursales")
    suc_id = resp_suc.json()[0]["id"] if resp_suc.json() else None
    resp_roles = await cliente_http.get("/api/v1/roles")
    roles = resp_roles.json()
    rol = next((r for r in roles if r["nombre"] == "ENCARGADO"), roles[0])
    uid = uuid.uuid4().hex[:8]
    correo = f"cu07.recep.{uid}@fashionstore.com"
    payload = {
        "rol_id": rol["id"],
        "nombres": "Receptor CU07",
        "apellidos": f"Test {uid}",
        "correo_electronico": correo,
        "contrasenia": "clave123456",
        "telefono": "+591 70000000",
        "sucursal_id": suc_id,
        "cargo": "Encargado CU07"
    }
    resp = await cliente_http.post("/api/v1/usuarios", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _crear_producto_variante(sku_suffix: str, precio: str = "100.00"):
    async with AsyncSessionLocal() as db:
        res_cat = await db.execute(select(Categoria).limit(1))
        cat = res_cat.scalars().first()
        if not cat:
            cat = Categoria(empresa_id=EMPRESA_TEST_ID, nombre=f"Cat CU07 {sku_suffix}", activo=True)
            db.add(cat)
            await db.flush()
        res_talla = await db.execute(select(Talla).limit(1))
        talla = res_talla.scalars().first()
        res_color = await db.execute(select(Color).limit(1))
        color = res_color.scalars().first()
        producto = Producto(
            empresa_id=EMPRESA_TEST_ID,
            categoria_id=cat.id,
            nombre=f"Producto CU07 {sku_suffix}",
            descripcion="Producto de prueba CU07 Kardex",
            genero="UNISEX",
            marca="FashionStore",
            precio_base=Decimal(precio),
            activo=True
        )
        db.add(producto)
        await db.flush()
        sku = f"SKU-CU07-{sku_suffix}-{uuid.uuid4().hex[:6].upper()}"
        variante = VarianteProducto(
            empresa_id=EMPRESA_TEST_ID,
            producto_id=producto.id,
            talla_id=talla.id,
            color_id=color.id,
            sku=sku,
            precio=Decimal(precio),
            costo_promedio=Decimal("0.00"),
            costo_ultimo=Decimal("0.00"),
            activa=True
        )
        db.add(variante)
        await db.commit()
        await db.refresh(variante)
        return variante.id, producto.id, sku


async def _registrar_lote(cliente_http, proveedor_id, sucursal_id, receptor_id, variante_id, cantidad, costo, nro_doc):
    payload = {
        "proveedor_id": proveedor_id,
        "sucursal_id": sucursal_id,
        "recibido_por_id": receptor_id,
        "numero_documento": nro_doc,
        "detalles": [{"variante_id": str(variante_id), "cantidad": cantidad, "costo_unitario": costo}]
    }
    resp = await cliente_http.post("/api/v1/recepciones", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_kardex_orden_desc_y_costos_unitarios(cliente_http: AsyncClient):
    """
    Crear proveedor+producto+variante, registrar 2 lotes con costos diferentes,
    verificar kardexPorVariante retorna 2 movimientos orden desc con costo_unitario correcto.
    """
    sucursal_id = await _obtener_ciudad_sucursal(cliente_http)
    receptor_id = await _crear_usuario_receptor(cliente_http)
    uid = uuid.uuid4().hex[:6]
    resp_prov = await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov CU07 Ord {uid}", "nit": f"700700{uid}"})
    assert resp_prov.status_code == 201
    proveedor_id = resp_prov.json()["id"]
    variante_id, _, _ = await _crear_producto_variante(uid + "ORD", precio="120.00")

    # Lote 1: 10 x 20.00 (más antiguo)
    lote1_id = await _registrar_lote(cliente_http, proveedor_id, sucursal_id, receptor_id, variante_id, 10, "20.00", f"DOC-ORD-{uid}-001")
    await asyncio.sleep(0.05)
    # Lote 2: 10 x 30.00 (más reciente)
    lote2_id = await _registrar_lote(cliente_http, proveedor_id, sucursal_id, receptor_id, variante_id, 10, "30.00", f"DOC-ORD-{uid}-002")

    # Verificar via Service kardexPorVariante
    async with AsyncSessionLocal() as db:
        servicio = InventarioService(db)
        kardex = await servicio.kardexPorVariante(variante_id)
        # Debe contener al menos los 2 creados
        assert len([k for k in kardex if k["referencia_id"] in [lote1_id, lote2_id]]) == 2
        # Orden desc: el más reciente primero
        # Filtrar solo los dos lotes de este test para verificar orden y costos
        kardex_filtrado = [k for k in kardex if k["referencia_id"] in [lote1_id, lote2_id]]
        # Debe estar ordenado desc por fecha_hora, por lo que el primero debe ser lote2 (costo 30)
        assert kardex_filtrado[0]["costo_unitario"] == 30.0, f"Esperado costo 30.0 primero, got {kardex_filtrado[0]}"
        assert kardex_filtrado[1]["costo_unitario"] == 20.0
        assert kardex_filtrado[0]["tipo"] == "RECEPCION_PROVEEDOR"
        assert kardex_filtrado[0]["cantidad"] == 10
        assert kardex_filtrado[0]["variante_id"] == str(variante_id)
        assert kardex_filtrado[0]["sucursal_destino_id"] == sucursal_id
        # IDs, fecha_hora deben existir y no ser None (auditoría inmutable)
        for mov in kardex_filtrado:
            assert mov["id"] is not None
            assert mov["fecha_hora"] is not None
            assert mov["responsable_id"] == receptor_id

    # Verificar via HTTP endpoint GET /inventario/kardex
    resp_kardex = await cliente_http.get("/api/v1/inventario/kardex", params={"variante_id": str(variante_id)})
    assert resp_kardex.status_code == 200, resp_kardex.text
    data = resp_kardex.json()
    assert isinstance(data, list)
    assert len([k for k in data if k["referencia_id"] in [lote1_id, lote2_id]]) >= 2
    # Verificar que endpoint respeta orden desc
    data_filtrado = [k for k in data if k["referencia_id"] in [lote1_id, lote2_id]]
    assert data_filtrado[0]["costo_unitario"] == 30.0


@pytest.mark.asyncio
async def test_existencias_separadas_por_sucursal(cliente_http: AsyncClient):
    """
    Verificar existenciasPorSucursal separa disponible, reservado, comprometido_traslado, en_transito
    """
    sucursal_id = await _obtener_ciudad_sucursal(cliente_http)
    receptor_id = await _crear_usuario_receptor(cliente_http)
    uid = uuid.uuid4().hex[:6]
    resp_prov = await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov CU07 Exist {uid}", "nit": f"710710{uid}"})
    assert resp_prov.status_code == 201
    proveedor_id = resp_prov.json()["id"]
    variante_id, _, _ = await _crear_producto_variante(uid + "EX", precio="150.00")
    lote_id = await _registrar_lote(cliente_http, proveedor_id, sucursal_id, receptor_id, variante_id, 15, "40.00", f"DOC-EX-{uid}-001")

    async with AsyncSessionLocal() as db:
        servicio = InventarioService(db)
        existencias = await servicio.existenciasPorSucursal(uuid.UUID(sucursal_id))
        # Debe contener la variante creada con disponible 15 y demás en 0
        match = [e for e in existencias if str(e["variante_id"]) == str(variante_id)]
        assert len(match) == 1, f"No se encontró existencia para variante {variante_id} en sucursal {sucursal_id}, existencias={existencias[:2]}"
        inv = match[0]
        assert inv["disponible"] == 15
        assert inv["reservado"] == 0
        assert inv["comprometido_traslado"] == 0
        assert inv["en_transito"] == 0
        # Campos enriquecidos
        assert "sku" in inv
        assert "costo_promedio" in inv
        assert "valorizacion" in inv
        assert inv["existencia_total"] == 15
        # existencias por variante (agrupado)
        por_variante = await servicio.existenciasPorVariante(variante_id)
        assert any(str(p) != "" for p in por_variante)  # al menos un resultado
        # Verificar que porVarianteEnriquecido retorna disponible>0
        assert any(p["disponible"] == 15 for p in por_variante)

    # HTTP endpoint /inventario/existencias
    resp_exist = await cliente_http.get("/api/v1/inventario/existencias", params={"sucursal_id": sucursal_id})
    assert resp_exist.status_code == 200, resp_exist.text
    data = resp_exist.json()
    assert isinstance(data, list)
    assert any(d["variante_id"] == str(variante_id) and d["disponible"] == 15 for d in data)
    # Sin filtro debe retornar lista global
    resp_all = await cliente_http.get("/api/v1/inventario/existencias")
    assert resp_all.status_code == 200
    assert isinstance(resp_all.json(), list)
    assert len(resp_all.json()) >= 1


@pytest.mark.asyncio
async def test_valorizacion_sucursal_y_global(cliente_http: AsyncClient):
    """
    Verificar valorizacion = sumatoria existencia*costo_promedio
    Ej. disponible 20 * promedio 25 = 500
    """
    # Crear sucursal dedicada para aislar valorización
    sucursal_id = await _crear_sucursal_extra(cliente_http)
    receptor_id = await _crear_usuario_receptor(cliente_http)
    uid = uuid.uuid4().hex[:6]
    resp_prov = await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov CU07 Val {uid}", "nit": f"720720{uid}"})
    assert resp_prov.status_code == 201
    proveedor_id = resp_prov.json()["id"]
    variante_id, _, _ = await _crear_producto_variante(uid + "VA", precio="80.00")

    # Lote 1: 10 x 20.00 => promedio 20
    await _registrar_lote(cliente_http, proveedor_id, sucursal_id, receptor_id, variante_id, 10, "20.00", f"DOC-VAL-{uid}-001")
    # Lote 2: 10 x 30.00 => promedio (10*20+10*30)/20 = 25.00, existencia total 20
    await _registrar_lote(cliente_http, proveedor_id, sucursal_id, receptor_id, variante_id, 10, "30.00", f"DOC-VAL-{uid}-002")

    async with AsyncSessionLocal() as db:
        # Verificar costo promedio recalculado
        res_var = await db.execute(select(VarianteProducto).where(VarianteProducto.id == variante_id))
        var = res_var.scalars().first()
        assert float(var.costo_promedio) == 25.0, f"Promedio esperado 25.0, got {var.costo_promedio}"
        assert float(var.costo_ultimo) == 30.0

        servicio = InventarioService(db)
        val = await servicio.valorizacion(uuid.UUID(sucursal_id))
        # Debe contener por_sucursal y global
        assert "por_sucursal" in val
        assert "global" in val
        por_suc = val["por_sucursal"]
        # Filtrar nuestra sucursal
        item = next((s for s in por_suc if s["sucursal_id"] == uuid.UUID(sucursal_id)), None)
        assert item is not None, f"No se encontró valorización para sucursal {sucursal_id}: {por_suc}"
        assert item["total_unidades"] == 20
        # Valorización: 20 * 25.00 = 500.00
        assert item["valorizacion"] == 500.0, f"Valorización esperada 500.0, got {item['valorizacion']}"
        # Margen bruto: precio 80 - costo 25 = 55 unitario *20 = 1100
        assert item["margen_bruto_total"] == 1100.0, f"Margen esperado 1100.0, got {item['margen_bruto_total']}"

        # Valorización global (sin filtro) debe incluir esta sucursal y valorización >=500
        val_global = await servicio.valorizacion(None)
        assert val_global["global"]["valorizacion"] >= 500.0
        assert val_global["global"]["total_unidades"] >= 20

    # HTTP endpoint /inventario/valorizacion?sucursal_id=...
    resp_val = await cliente_http.get("/api/v1/inventario/valorizacion", params={"sucursal_id": sucursal_id})
    assert resp_val.status_code == 200, resp_val.text
    data = resp_val.json()
    assert "por_sucursal" in data
    assert any(s["valorizacion"] == 500.0 for s in data["por_sucursal"])
    # Sin filtro
    resp_global = await cliente_http.get("/api/v1/inventario/valorizacion")
    assert resp_global.status_code == 200
    assert "global" in resp_global.json()


@pytest.mark.asyncio
async def test_filtros_kardex_tipo_y_sucursal_y_rango(cliente_http: AsyncClient):
    """
    Probar filtros por tipo y por sucursal, y rango fecha.
    """
    sucursal_a = await _obtener_ciudad_sucursal(cliente_http)
    sucursal_b = await _crear_sucursal_extra(cliente_http)
    receptor_id = await _crear_usuario_receptor(cliente_http)
    uid = uuid.uuid4().hex[:6]
    resp_prov = await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov CU07 Filt {uid}", "nit": f"730730{uid}"})
    assert resp_prov.status_code == 201
    proveedor_id = resp_prov.json()["id"]
    variante_id, _, _ = await _crear_producto_variante(uid + "FI", precio="90.00")

    # Lote en sucursal A
    lote_a = await _registrar_lote(cliente_http, proveedor_id, sucursal_a, receptor_id, variante_id, 5, "10.00", f"DOC-FI-{uid}-A")
    await asyncio.sleep(0.02)
    # Lote en sucursal B
    lote_b = await _registrar_lote(cliente_http, proveedor_id, sucursal_b, receptor_id, variante_id, 7, "15.00", f"DOC-FI-{uid}-B")

    async with AsyncSessionLocal() as db:
        servicio = InventarioService(db)
        # Filtro por sucursal A -> solo lote A
        kardex_a = await servicio.kardexPorVariante(variante_id, sucursal_id=uuid.UUID(sucursal_a))
        ids_a = [k["referencia_id"] for k in kardex_a]
        assert lote_a in ids_a
        assert lote_b not in ids_a, f"Filtro sucursal A no debería incluir lote B. Kardex A={ids_a}"

        # Filtro por sucursal B -> solo lote B
        kardex_b = await servicio.kardexPorVariante(variante_id, sucursal_id=uuid.UUID(sucursal_b))
        ids_b = [k["referencia_id"] for k in kardex_b]
        assert lote_b in ids_b
        assert lote_a not in ids_b

        # Filtro por tipo RECEPCION_PROVEEDOR (debe retornar ambos si se consulta sin sucursal)
        kardex_tipo = await servicio.kardexPorVariante(variante_id, tipo="RECEPCION_PROVEEDOR")
        assert len([k for k in kardex_tipo if k["referencia_id"] in [lote_a, lote_b]]) == 2

        # Filtro por tipo inexistente -> vacío
        kardex_vacio = await servicio.kardexPorVariante(variante_id, tipo="VENTA_PRESENCIAL")
        assert len([k for k in kardex_vacio if k["referencia_id"] in [lote_a, lote_b]]) == 0

        # Filtro por rango fecha: desde futuro -> vacío
        futuro = datetime.now(timezone.utc) + timedelta(days=1)
        kardex_futuro = await servicio.kardexPorVariante(variante_id, desde=futuro)
        assert len(kardex_futuro) == 0

        # Rango hasta pasado (ayer) -> vacío para estos lotes recientes
        ayer = datetime.now(timezone.utc) - timedelta(days=1)
        # Pero nuestros lotes son recientes, hasta ayer no deberían aparecer
        # Para probar rango válido, usar desde ayer
        desde_ayer = datetime.now(timezone.utc) - timedelta(days=1)
        kardex_rango = await servicio.kardexPorVariante(variante_id, desde=desde_ayer)
        assert len([k for k in kardex_rango if k["referencia_id"] in [lote_a, lote_b]]) == 2

        # Verificar Repositorio directo con listarPaginado
        mov_repo = MovimientoRepository(db)
        pag = await mov_repo.listarPaginado(variante_id=variante_id, sucursal_id=uuid.UUID(sucursal_a), tipo="RECEPCION_PROVEEDOR", limit=10, offset=0)
        assert "total" in pag and "items" in pag
        assert pag["total"] >= 1

    # HTTP filtros
    resp_filtro_suc = await cliente_http.get("/api/v1/inventario/kardex", params={"variante_id": str(variante_id), "sucursal_id": sucursal_a})
    assert resp_filtro_suc.status_code == 200
    assert any(k["referencia_id"] == lote_a for k in resp_filtro_suc.json())
    assert not any(k["referencia_id"] == lote_b for k in resp_filtro_suc.json())

    resp_filtro_tipo = await cliente_http.get("/api/v1/inventario/kardex", params={"variante_id": str(variante_id), "tipo": "RECEPCION_PROVEEDOR"})
    assert resp_filtro_tipo.status_code == 200
    assert len([k for k in resp_filtro_tipo.json() if k["referencia_id"] in [lote_a, lote_b]]) == 2

    # Rango fecha via HTTP
    desde_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    resp_rango = await cliente_http.get("/api/v1/inventario/kardex", params={"variante_id": str(variante_id), "desde": desde_iso})
    assert resp_rango.status_code == 200
    assert len([k for k in resp_rango.json() if k["referencia_id"] in [lote_a, lote_b]]) == 2


@pytest.mark.asyncio
async def test_kardex_detalle_y_contratos_presentacion(cliente_http: AsyncClient):
    """
    Verificar contratos Presentación consultarKardex(), consultarExistencias(), consultarValorizacion()
    y endpoint GET /api/v1/inventario/kardex/{id}
    """
    sucursal_id = await _obtener_ciudad_sucursal(cliente_http)
    receptor_id = await _crear_usuario_receptor(cliente_http)
    uid = uuid.uuid4().hex[:6]
    resp_prov = await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov CU07 Cont {uid}", "nit": f"740740{uid}"})
    assert resp_prov.status_code == 201
    proveedor_id = resp_prov.json()["id"]
    variante_id, _, _ = await _crear_producto_variante(uid + "CO", precio="110.00")
    lote_id = await _registrar_lote(cliente_http, proveedor_id, sucursal_id, receptor_id, variante_id, 8, "22.50", f"DOC-CO-{uid}-001")

    async with AsyncSessionLocal() as db:
        # Contratos Controller
        servicio = InventarioService(db)
        assert hasattr(servicio, "kardexPorVariante")
        assert hasattr(servicio, "existenciasPorSucursal")
        assert hasattr(servicio, "valorizacion")
        # Aliases Presentación
        assert hasattr(servicio, "consultarKardex")
        assert hasattr(servicio, "consultarExistencias")
        assert hasattr(servicio, "consultarValorizacion")

        # Datos
        inv_repo = InventarioRepository(db)
        mov_repo = MovimientoRepository(db)
        assert hasattr(mov_repo, "listar")
        assert hasattr(mov_repo, "listarPaginado")
        assert hasattr(inv_repo, "existencias")
        assert hasattr(inv_repo, "valorizacionPorSucursal")

        # Kardex detalle
        kardex = await servicio.kardexPorVariante(variante_id)
        mov_id = kardex[0]["id"]
        detalle = await servicio.kardexPorId(uuid.UUID(mov_id))
        assert detalle["id"] == mov_id
        assert detalle["variante_id"] == str(variante_id)
        assert detalle["tipo"] == "RECEPCION_PROVEEDOR"
        assert detalle["costo_unitario"] == 22.5
        assert detalle["cantidad"] == 8

        # Consultar aliases
        kardex2 = await servicio.consultarKardex(variante_id)
        assert len(kardex2) >= 1
        exist = await servicio.consultarExistencias(uuid.UUID(sucursal_id))
        assert isinstance(exist, list)
        val = await servicio.consultarValorizacion(uuid.UUID(sucursal_id))
        assert "por_sucursal" in val

    # HTTP detalle
    # Obtener id via kardex list
    resp_kardex = await cliente_http.get("/api/v1/inventario/kardex", params={"variante_id": str(variante_id)})
    assert resp_kardex.status_code == 200
    mov_id_http = resp_kardex.json()[0]["id"]
    resp_detalle = await cliente_http.get(f"/api/v1/inventario/kardex/{mov_id_http}")
    assert resp_detalle.status_code == 200, resp_detalle.text
    detalle_http = resp_detalle.json()
    assert detalle_http["id"] == mov_id_http
    assert detalle_http["tipo"] == "RECEPCION_PROVEEDOR"
    assert "costo_unitario" in detalle_http
    assert "fecha_hora" in detalle_http

    # Verificar estructura existencias y valorización endpoints ya probados pero validar no necesidad alineación derecha
    resp_ex = await cliente_http.get("/api/v1/inventario/existencias", params={"sucursal_id": sucursal_id})
    assert resp_ex.status_code == 200
    for row in resp_ex.json()[:1]:
        assert "disponible" in row and isinstance(row["disponible"], int)
        assert "reservado" in row

    resp_val = await cliente_http.get("/api/v1/inventario/valorizacion", params={"sucursal_id": sucursal_id})
    assert resp_val.status_code == 200
    assert "por_sucursal" in resp_val.json()


@pytest.mark.asyncio
async def test_repository_existencias_y_valorizacion_directo(cliente_http: AsyncClient):
    """
    Test directo de repositories existencias() y valorizacionPorSucursal cálculo
    """
    sucursal_id = await _crear_sucursal_extra(cliente_http)
    receptor_id = await _crear_usuario_receptor(cliente_http)
    uid = uuid.uuid4().hex[:6]
    resp_prov = await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov Repo {uid}", "nit": f"750750{uid}"})
    assert resp_prov.status_code == 201
    proveedor_id = resp_prov.json()["id"]
    variante_id, _, _ = await _crear_producto_variante(uid + "RE", precio="60.00")
    await _registrar_lote(cliente_http, proveedor_id, sucursal_id, receptor_id, variante_id, 12, "18.00", f"DOC-RE-{uid}-001")

    async with AsyncSessionLocal() as db:
        inv_repo = InventarioRepository(db)
        exist = await inv_repo.existencias(uuid.UUID(sucursal_id))
        assert len([e for e in exist if e.variante_id == variante_id]) == 1
        # Enriquecido
        val = await inv_repo.valorizacionPorSucursal(uuid.UUID(sucursal_id))
        assert len(val) == 1
        assert val[0]["total_unidades"] == 12
        assert val[0]["valorizacion"] == 216.0  # 12 * 18
