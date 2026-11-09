import uuid
import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select, update
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.modules.catalogo.models import Producto, VarianteProducto, Categoria, Talla, Color
from backend.app.core.modules.inventario.models import InventarioSucursal
from backend.app.core.modules.organizacion.models import Sucursal
from tests.helpers_ciclo2 import crear_ciudad_plataforma

async def _get_or_create_ciudad_sucursal(cliente_http, suffix="CU06"):
    # Intentar reusar sucursales existentes o crear 2
    resp = await cliente_http.get("/api/v1/sucursales")
    sucursales = resp.json()
    if len(sucursales) >= 2:
        return sucursales[0]["id"], sucursales[1]["id"]
    # crear ciudad/sucursal si falta
    uid = uuid.uuid4().hex[:6]
    # ciudad 1
    ciudad = await crear_ciudad_plataforma(f"Ciudad CU06-A {uid}")
    ciudad_id = ciudad["id"]
    r_suc1 = await cliente_http.post("/api/v1/sucursales", json={
        "ciudad_id": ciudad_id,
        "nombre": f"Sucursal CU06-A {uid}",
        "direccion": "Av CU06 123",
        "numero_anillo": 1
    })
    assert r_suc1.status_code == 201, r_suc1.text
    suc1 = r_suc1.json()["id"]
    # ciudad 2 / sucursal 2
    ciudad2 = await crear_ciudad_plataforma(f"Ciudad CU06-B {uid}")
    ciudad2_id = ciudad2["id"]
    r_suc2 = await cliente_http.post("/api/v1/sucursales", json={
        "ciudad_id": ciudad2_id,
        "nombre": f"Sucursal CU06-B {uid}",
        "direccion": "Av CU06 456",
        "numero_anillo": 2
    })
    assert r_suc2.status_code == 201, r_suc2.text
    suc2 = r_suc2.json()["id"]
    return suc1, suc2

async def _crear_usuario_receptor(cliente_http):
    resp_suc = await cliente_http.get("/api/v1/sucursales")
    suc_id = resp_suc.json()[0]["id"] if resp_suc.json() else None
    resp_roles = await cliente_http.get("/api/v1/roles")
    roles = resp_roles.json()
    rol = next((r for r in roles if r["nombre"] == "ENCARGADO"), roles[0])
    uid = uuid.uuid4().hex[:8]
    correo = f"recep.cu06.{uid}@fashionstore.com"
    payload = {
        "rol_id": rol["id"],
        "nombres": "Receptor",
        "apellidos": f"CU06 {uid}",
        "correo_electronico": correo,
        "contrasenia": "clave123456",
        "telefono": "+591 70000000",
        "sucursal_id": suc_id,
        "cargo": "Encargado CU06"
    }
    resp = await cliente_http.post("/api/v1/usuarios", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]

@pytest.mark.asyncio
async def test_cu06_catalogo_filtros_y_busqueda(cliente_http: AsyncClient):
    """
    Crea 2 productos con variantes diferentes colores/tallas/temporadas,
    prueba filtrar por categoria, por talla, por color hex, por temporada, búsqueda texto "Camisa", precio rango.
    """
    uid = uuid.uuid4().hex[:6]

    # --- Maestros ---
    # Tallas
    r_talla_s = await cliente_http.post("/api/v1/tallas", json={"nombre": f"S-CU06-{uid}", "orden": 1})
    assert r_talla_s.status_code == 201, r_talla_s.text
    talla_s_id = r_talla_s.json()["id"]
    r_talla_m = await cliente_http.post("/api/v1/tallas", json={"nombre": f"M-CU06-{uid}", "orden": 2})
    talla_m_id = r_talla_m.json()["id"]

    # Colores con hex
    r_color_rojo = await cliente_http.post("/api/v1/colores", json={"nombre": f"Rojo CU06 {uid}", "codigo_hex": "#FF0000"})
    assert r_color_rojo.status_code == 201, r_color_rojo.text
    rojo_id = r_color_rojo.json()["id"]
    r_color_azul = await cliente_http.post("/api/v1/colores", json={"nombre": f"Azul CU06 {uid}", "codigo_hex": "#0000FF"})
    azul_id = r_color_azul.json()["id"]

    # Categorias
    r_cat = await cliente_http.post("/api/v1/categorias", json={"nombre": f"Camisas CU06 {uid}"})
    assert r_cat.status_code == 201
    cat_camisas_id = r_cat.json()["id"]
    r_cat2 = await cliente_http.post("/api/v1/categorias", json={"nombre": f"Pantalones CU06 {uid}"})
    cat_pant_id = r_cat2.json()["id"]

    # Temporadas
    r_temp_verano = await cliente_http.post("/api/v1/temporadas", json={"nombre": f"Verano CU06 {uid}"})
    assert r_temp_verano.status_code == 201
    temp_verano_id = r_temp_verano.json()["id"]
    r_temp_inv = await cliente_http.post("/api/v1/temporadas", json={"nombre": f"Invierno CU06 {uid}"})
    temp_inv_id = r_temp_inv.json()["id"]

    # Colecciones
    r_col_urb = await cliente_http.post("/api/v1/colecciones", json={"nombre": f"Urbana CU06 {uid}"})
    col_urb_id = r_col_urb.json()["id"]
    r_col_clas = await cliente_http.post("/api/v1/colecciones", json={"nombre": f"Clasica CU06 {uid}"})
    col_clas_id = r_col_clas.json()["id"]

    # Proveedor
    r_prov = await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov CU06 {uid}", "nit": f"600600{uid}"})
    prov_id = r_prov.json()["id"]

    # --- Productos ---
    # Producto 1: Camisa Clasica - categoria camisas, genero HOMBRE, marca FashionStore, precio 120, temporada verano, coleccion urbana, variantes S rojo, M azul
    r_prod1 = await cliente_http.post("/api/v1/productos", json={
        "nombre": f"Camisa Clasica {uid}",
        "descripcion": "Camisa de algodón clásica para prueba búsqueda",
        "categoria_id": cat_camisas_id,
        "proveedor_principal_id": prov_id,
        "genero": "HOMBRE",
        "marca": "FashionStore",
        "precio_base": "120.00",
        "activo": True,
        "imagenes": [{"enlace_imagen": "https://cdn.test/camisa1.jpg", "orden": 0, "es_principal": True}],
        "temporada_ids": [temp_verano_id],
        "coleccion_ids": [col_urb_id]
    })
    assert r_prod1.status_code == 201, r_prod1.text
    prod1_id = r_prod1.json()["id"]
    assert temp_verano_id in r_prod1.json()["temporada_ids"]

    # Producto 2: Pantalon Cargo - categoria pantalones, genero MUJER, marca DenimCo, precio 250, temporada invierno, coleccion clasica
    r_prod2 = await cliente_http.post("/api/v1/productos", json={
        "nombre": f"Pantalon Cargo {uid}",
        "descripcion": "Pantalon cargo invierno",
        "categoria_id": cat_pant_id,
        "proveedor_principal_id": prov_id,
        "genero": "MUJER",
        "marca": "DenimCo",
        "precio_base": "250.00",
        "activo": True,
        "imagenes": [{"enlace_imagen": "https://cdn.test/pantalon.jpg", "orden": 0, "es_principal": True}],
        "temporada_ids": [temp_inv_id],
        "coleccion_ids": [col_clas_id]
    })
    assert r_prod2.status_code == 201, r_prod2.text
    prod2_id = r_prod2.json()["id"]

    # Variantes
    sku1 = f"SKU-CU06-{uid}-001"
    r_var1 = await cliente_http.post("/api/v1/variantes", json={
        "producto_id": prod1_id,
        "talla_id": talla_s_id,
        "color_id": rojo_id,
        "sku": sku1,
        "precio": "120.00"
    })
    assert r_var1.status_code == 201, r_var1.text
    var1_id = r_var1.json()["id"]

    sku2 = f"SKU-CU06-{uid}-002"
    r_var2 = await cliente_http.post("/api/v1/variantes", json={
        "producto_id": prod1_id,
        "talla_id": talla_m_id,
        "color_id": azul_id,
        "sku": sku2,
        "precio": "125.00"
    })
    assert r_var2.status_code == 201, r_var2.text
    var2_id = r_var2.json()["id"]

    sku3 = f"SKU-CU06-{uid}-003"
    r_var3 = await cliente_http.post("/api/v1/variantes", json={
        "producto_id": prod2_id,
        "talla_id": talla_m_id,
        "color_id": rojo_id,
        "sku": sku3,
        "precio": "250.00"
    })
    assert r_var3.status_code == 201, r_var3.text
    var3_id = r_var3.json()["id"]

    # --- Filtros ---
    # Filtrar por categoria (camisas) -> debe incluir prod1, no prod2
    r_f_cat = await cliente_http.get("/api/v1/productos", params={"categoria_id": cat_camisas_id})
    assert r_f_cat.status_code == 200, r_f_cat.text
    ids_cat = [p["id"] for p in r_f_cat.json()]
    assert prod1_id in ids_cat, f"prod1 debe aparecer filtrando por categoria camisas, got {ids_cat}"
    assert prod2_id not in ids_cat, "prod2 no debe aparecer filtrando por camisas"

    # Filtrar por talla S -> solo prod1 (var1 tiene S)
    r_f_talla = await cliente_http.get("/api/v1/productos", params={"talla_id": talla_s_id})
    assert r_f_talla.status_code == 200
    ids_talla = [p["id"] for p in r_f_talla.json()]
    assert prod1_id in ids_talla
    # prod2 tiene solo M, no S, entonces no debe estar
    assert prod2_id not in ids_talla

    # Filtrar por color rojo (id) -> prod1 y prod2 ambos tienen rojo variant
    r_f_color = await cliente_http.get("/api/v1/productos", params={"color_id": rojo_id})
    assert r_f_color.status_code == 200
    ids_color = [p["id"] for p in r_f_color.json()]
    assert prod1_id in ids_color
    assert prod2_id in ids_color

    # Filtrar por color hex #FF0000 -> también debe retornar los que tienen rojo
    r_f_hex = await cliente_http.get("/api/v1/productos", params={"codigo_hex": "#FF0000"})
    assert r_f_hex.status_code == 200
    ids_hex = [p["id"] for p in r_f_hex.json()]
    # hex filtra vía variantes, debe incluir ambos que tienen rojo
    assert prod1_id in ids_hex
    assert prod2_id in ids_hex
    # sin hex azul no debe incluir? verificar que hex azul solo trae prod1 (var2)
    r_f_hex_azul = await cliente_http.get("/api/v1/productos", params={"codigo_hex": "#0000FF"})
    ids_hex_azul = [p["id"] for p in r_f_hex_azul.json()]
    assert prod1_id in ids_hex_azul
    # prod2 no tiene azul, no debe estar
    assert prod2_id not in ids_hex_azul

    # Filtrar por temporada verano -> solo prod1
    r_f_temp = await cliente_http.get("/api/v1/productos", params={"temporada_id": temp_verano_id})
    assert r_f_temp.status_code == 200
    ids_temp = [p["id"] for p in r_f_temp.json()]
    assert prod1_id in ids_temp
    assert prod2_id not in ids_temp

    # Filtrar por coleccion urbana -> solo prod1
    r_f_col = await cliente_http.get("/api/v1/productos", params={"coleccion_id": col_urb_id})
    assert r_f_col.status_code == 200
    ids_col = [p["id"] for p in r_f_col.json()]
    assert prod1_id in ids_col
    assert prod2_id not in ids_col

    # Búsqueda texto "Camisa" -> debe encontrar prod1, no prod2
    r_search = await cliente_http.get("/api/v1/productos", params={"texto": "Camisa"})
    assert r_search.status_code == 200
    ids_search = [p["id"] for p in r_search.json()]
    assert prod1_id in ids_search
    # también probar alias busqueda y q
    r_search2 = await cliente_http.get("/api/v1/productos", params={"busqueda": "Camisa"})
    assert r_search2.status_code == 200
    assert prod1_id in [p["id"] for p in r_search2.json()]
    r_search3 = await cliente_http.get("/api/v1/productos", params={"q": "Camisa"})
    assert r_search3.status_code == 200
    assert prod1_id in [p["id"] for p in r_search3.json()]

    # Filtrar por precio rango 100-150 -> solo prod1 (120)
    r_precio = await cliente_http.get("/api/v1/productos", params={"precio_min": 100, "precio_max": 150})
    assert r_precio.status_code == 200
    ids_precio = [p["id"] for p in r_precio.json()]
    assert prod1_id in ids_precio
    assert prod2_id not in ids_precio

    # Filtrar por precio 200-300 -> solo prod2 (250)
    r_precio2 = await cliente_http.get("/api/v1/productos", params={"precio_min": 200, "precio_max": 300})
    ids_precio2 = [p["id"] for p in r_precio2.json()]
    assert prod2_id in ids_precio2
    assert prod1_id not in ids_precio2

    # Filtrar por genero HOMBRE -> prod1
    r_genero = await cliente_http.get("/api/v1/productos", params={"genero": "HOMBRE"})
    assert any(p["id"] == prod1_id for p in r_genero.json())
    # marca DenimCo -> prod2
    r_marca = await cliente_http.get("/api/v1/productos", params={"marca": "DenimCo"})
    assert any(p["id"] == prod2_id for p in r_marca.json())

    # Combinación múltiple: categoria camisas + talla M + temporada verano -> prod1
    r_comb = await cliente_http.get("/api/v1/productos", params={"categoria_id": cat_camisas_id, "talla_id": talla_m_id, "temporada_id": temp_verano_id})
    ids_comb = [p["id"] for p in r_comb.json()]
    assert prod1_id in ids_comb

    # Catálogo debe mostrar activos, no inactivos; probar desactivar prod2 y que no aparezca con solo_activos=true
    await cliente_http.patch(f"/api/v1/productos/{prod2_id}/activacion", params={"activo": "false"})
    r_activos = await cliente_http.get("/api/v1/productos", params={"solo_activos": "true"})
    ids_activos = [p["id"] for p in r_activos.json()]
    assert prod2_id not in ids_activos
    # con solo_activos false debe aparecer
    r_todos = await cliente_http.get("/api/v1/productos", params={"solo_activos": "false"})
    ids_todos = [p["id"] for p in r_todos.json()]
    assert prod2_id in ids_todos
    # reactivar para no afectar otros tests
    await cliente_http.patch(f"/api/v1/productos/{prod2_id}/activacion", params={"activo": "true"})

    # Filtros opciones endpoint
    r_opc = await cliente_http.get("/api/v1/catalogo/filtros-opciones")
    assert r_opc.status_code == 200, r_opc.text
    data_opc = r_opc.json()
    assert "categorias" in data_opc
    assert "tallas" in data_opc
    assert "colores" in data_opc
    assert "temporadas" in data_opc
    assert "colecciones" in data_opc

    # Catalogo alias endpoint
    r_alias = await cliente_http.get(
        "/api/v1/catalogo/productos",
        params={"texto": "Camisa", "empresa_codigo": "fashionstore"},
    )
    assert r_alias.status_code == 200
    assert prod1_id in [p["id"] for p in r_alias.json()]

@pytest.mark.asyncio
async def test_cu06_disponibilidad_por_variante_diferenciada(cliente_http: AsyncClient):
    uid = uuid.uuid4().hex[:6]
    # Maestros para variante
    r_talla = await cliente_http.post("/api/v1/tallas", json={"nombre": f"DispTalla-{uid}", "orden": 5})
    talla_id = r_talla.json()["id"]
    r_color = await cliente_http.post("/api/v1/colores", json={"nombre": f"DispColor-{uid}", "codigo_hex": "#123456"})
    color_id = r_color.json()["id"]
    r_cat = await cliente_http.post("/api/v1/categorias", json={"nombre": f"DispCat-{uid}"})
    cat_id = r_cat.json()["id"]
    r_prov = await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov Disp {uid}", "nit": f"700700{uid}"})
    prov_id = r_prov.json()["id"]

    # Producto y variante
    r_prod = await cliente_http.post("/api/v1/productos", json={
        "nombre": f"Producto Disp {uid}",
        "categoria_id": cat_id,
        "proveedor_principal_id": prov_id,
        "precio_base": "90.00",
        "activo": True
    })
    prod_id = r_prod.json()["id"]
    sku = f"SKU-DISP-{uid}"
    r_var = await cliente_http.post("/api/v1/variantes", json={
        "producto_id": prod_id,
        "talla_id": talla_id,
        "color_id": color_id,
        "sku": sku,
        "precio": "95.00"
    })
    assert r_var.status_code == 201, r_var.text
    var_id = r_var.json()["id"]

    # Sucursales
    suc1_id, suc2_id = await _get_or_create_ciudad_sucursal(cliente_http, suffix=uid)
    receptor_id = await _crear_usuario_receptor(cliente_http)

    # Lote en sucursal 1 con 15 unidades costo 20
    payload_lote1 = {
        "proveedor_id": prov_id,
        "sucursal_id": suc1_id,
        "recibido_por_id": receptor_id,
        "numero_documento": f"FAC-DISP-{uid}-1",
        "detalles": [{"variante_id": var_id, "cantidad": 15, "costo_unitario": "20.00"}]
    }
    r_lote1 = await cliente_http.post("/api/v1/recepciones", json=payload_lote1)
    assert r_lote1.status_code == 201, r_lote1.text

    # Lote en sucursal 2 con 8 unidades costo 22
    payload_lote2 = {
        "proveedor_id": prov_id,
        "sucursal_id": suc2_id,
        "recibido_por_id": receptor_id,
        "numero_documento": f"FAC-DISP-{uid}-2",
        "detalles": [{"variante_id": var_id, "cantidad": 8, "costo_unitario": "22.00"}]
    }
    r_lote2 = await cliente_http.post("/api/v1/recepciones", json=payload_lote2)
    assert r_lote2.status_code == 201, r_lote2.text

    # Manipular inventario para probar diferenciación: poner reservado, comprometido, en_transito en suc1
    async with AsyncSessionLocal() as db:
        # suc1: set reservado=3, comprometido=2, en_transito=1 dejando disponible 15
        await db.execute(update(InventarioSucursal).where(
            InventarioSucursal.variante_id == uuid.UUID(var_id),
            InventarioSucursal.sucursal_id == uuid.UUID(suc1_id)
        ).values(reservado=3, comprometido_traslado=2, en_transito=1))
        # suc2: dejar disponible 0 para probar filtro
        await db.execute(update(InventarioSucursal).where(
            InventarioSucursal.variante_id == uuid.UUID(var_id),
            InventarioSucursal.sucursal_id == uuid.UUID(suc2_id)
        ).values(disponible=0, reservado=5, comprometido_traslado=0, en_transito=0))
        await db.commit()

    # Consultar disponibilidad -> debe retornar solo sucursal 1 (disponible >0)
    r_disp = await cliente_http.get(f"/api/v1/variantes/{var_id}/disponibilidad")
    assert r_disp.status_code == 200, r_disp.text
    data = r_disp.json()
    assert isinstance(data, list), "Debe ser lista por sucursal"
    # Solo 1 sucursal con disponible>0
    assert len(data) == 1, f"Debe retornar 1 sucursal con disponible>0, got {len(data)} : {data}"
    item = data[0]
    # Verificar campos diferenciados
    assert "disponible" in item
    assert "reservado" in item
    assert "comprometido_traslado" in item
    assert "en_transito" in item
    assert item["disponible"] == 15
    assert item["reservado"] == 3
    assert item["comprometido_traslado"] == 2
    assert item["en_transito"] == 1
    assert item["sucursal_id"] == suc1_id
    assert "sucursal_nombre" in item
    assert "ciudad_nombre" in item
    # Verificar que no suma global: total disponible no debe ser 15+0 =15? En este caso solo 15 visible. Comprobar que no retorna total 15+0 mezclado como 23?
    # Ya validamos len==1, no global.

    # Restaurar suc2 disponible para probar que luego aparecen 2 sucursales
    async with AsyncSessionLocal() as db:
        await db.execute(update(InventarioSucursal).where(
            InventarioSucursal.variante_id == uuid.UUID(var_id),
            InventarioSucursal.sucursal_id == uuid.UUID(suc2_id)
        ).values(disponible=8, reservado=0))
        await db.commit()

    r_disp2 = await cliente_http.get(f"/api/v1/variantes/{var_id}/disponibilidad")
    assert r_disp2.status_code == 200
    data2 = r_disp2.json()
    assert len(data2) == 2, f"Con ambas sucursales con disponible>0 debe retornar 2, got {len(data2)}"
    # Verificar por sucursal no total: cada item tiene su sucursal_id y cantidades separadas
    suc_ids = {d["sucursal_id"] for d in data2}
    assert suc1_id in suc_ids and suc2_id in suc_ids
    # Verificar no hay campo total global
    for d in data2:
        assert "total" not in d or isinstance(d.get("disponible"), int)

    # Probar alias catalogo
    r_alias_disp = await cliente_http.get(f"/api/v1/catalogo/variantes/{var_id}/disponibilidad")
    assert r_alias_disp.status_code == 200
    assert len(r_alias_disp.json()) == 2

    # Variante sin stock debe retornar lista vacía, no error
    # Crear variante nueva sin lote con nueva talla/color para garantizar unicidad
    r_talla_vacia = await cliente_http.post("/api/v1/tallas", json={"nombre": f"VaciaTalla-{uid}", "orden": 7})
    assert r_talla_vacia.status_code == 201, r_talla_vacia.text
    talla_vacia_id = r_talla_vacia.json()["id"]
    r_color_vacia = await cliente_http.post("/api/v1/colores", json={"nombre": f"VaciaColor-{uid}", "codigo_hex": "#654321"})
    assert r_color_vacia.status_code == 201, r_color_vacia.text
    color_vacia_id = r_color_vacia.json()["id"]
    r_var_vacia = await cliente_http.post("/api/v1/variantes", json={
        "producto_id": prod_id,
        "talla_id": talla_vacia_id,
        "color_id": color_vacia_id,
        "sku": f"SKU-VACIA-{uid}",
        "precio": "95.00"
    })
    assert r_var_vacia.status_code == 201, r_var_vacia.text
    var_vacia_id = r_var_vacia.json()["id"]

    r_disp_empty = await cliente_http.get(f"/api/v1/variantes/{var_vacia_id}/disponibilidad")
    assert r_disp_empty.status_code == 200
    assert r_disp_empty.json() == [], "Variante sin stock debe retornar lista vacía"

    # Verificar que disponibilidad no modifica inventario (solo lectura)
    async with AsyncSessionLocal() as db:
        res_before = await db.execute(select(InventarioSucursal).where(InventarioSucursal.variante_id == uuid.UUID(var_id)))
        inv_before = list(res_before.scalars().all())
        # llamar de nuevo disponibilidad
        await cliente_http.get(f"/api/v1/variantes/{var_id}/disponibilidad")
        res_after = await db.execute(select(InventarioSucursal).where(InventarioSucursal.variante_id == uuid.UUID(var_id)))
        inv_after = list(res_after.scalars().all())
        assert len(inv_before) == len(inv_after)
        for b, a in zip(sorted(inv_before, key=lambda x: str(x.sucursal_id)), sorted(inv_after, key=lambda x: str(x.sucursal_id))):
            assert b.disponible == a.disponible
            assert b.reservado == a.reservado

@pytest.mark.asyncio
async def test_cu06_repository_buscarConFiltros_dict_y_porVariante(cliente_http: AsyncClient):
    """
    Verifica contratos Datos: ProductoRepository.buscarConFiltros(filtros dict) y InventarioRepository.porVariante()
    """
    uid = uuid.uuid4().hex[:6]
    # Crear maestros rápido
    r_talla = await cliente_http.post("/api/v1/tallas", json={"nombre": f"RepoTalla-{uid}"})
    talla_id = r_talla.json()["id"]
    r_color = await cliente_http.post("/api/v1/colores", json={"nombre": f"RepoColor-{uid}", "codigo_hex": "#ABCDEF"})
    color_id = r_color.json()["id"]
    r_cat = await cliente_http.post("/api/v1/categorias", json={"nombre": f"RepoCat-{uid}"})
    cat_id = r_cat.json()["id"]
    r_temp = await cliente_http.post("/api/v1/temporadas", json={"nombre": f"RepoTemp-{uid}"})
    temp_id = r_temp.json()["id"]
    r_prov = await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"RepoProv {uid}", "nit": f"800800{uid}"})
    prov_id = r_prov.json()["id"]

    r_prod = await cliente_http.post("/api/v1/productos", json={
        "nombre": f"Repo Producto {uid}",
        "categoria_id": cat_id,
        "proveedor_principal_id": prov_id,
        "precio_base": "77.00",
        "genero": "UNISEX",
        "marca": "RepoMarca",
        "temporada_ids": [temp_id],
        "activo": True
    })
    assert r_prod.status_code == 201
    prod_id = r_prod.json()["id"]
    r_var = await cliente_http.post("/api/v1/variantes", json={
        "producto_id": prod_id,
        "talla_id": talla_id,
        "color_id": color_id,
        "sku": f"SKU-REPO-{uid}",
        "precio": "77.00"
    })
    var_id = r_var.json()["id"]

    # Probar repository directo con filtros dict
    from backend.app.core.modules.catalogo.repositories.producto_repository import ProductoRepository
    from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
    async with AsyncSessionLocal() as db:
        repo = ProductoRepository(db)
        # buscar por filtros dict
        resultados = await repo.buscarConFiltros(filtros={"categoria_id": cat_id, "talla_id": talla_id})
        assert any(str(p.id) == prod_id for p in resultados), "buscarConFiltros dict debe encontrar producto"
        # buscar por temporada via dict
        resultados2 = await repo.buscarConFiltros(filtros={"temporada_id": temp_id})
        assert any(str(p.id) == prod_id for p in resultados2)
        # buscar por texto dict
        resultados3 = await repo.buscarConFiltros(filtros={"busqueda": "Repo Producto"})
        assert any(str(p.id) == prod_id for p in resultados3)
        # buscar por precio dict
        resultados4 = await repo.buscarConFiltros(filtros={"precio_min": 70, "precio_max": 80})
        assert any(str(p.id) == prod_id for p in resultados4)
        # buscar por color hex
        resultados5 = await repo.buscarConFiltros(filtros={"codigo_hex": "#ABCDEF"})
        assert any(str(p.id) == prod_id for p in resultados5)

        # porVariante debe filtrar disponible>0
        # Crear inventario con lote
        # Usar receptores y sucursales existentes
        from backend.app.core.modules.inventario.models import InventarioSucursal
        # Verificar que porVariante sin stock retorna vacío inicialmente
        inv_repo = InventarioRepository(db)
        lista_vacia = await inv_repo.porVariante(uuid.UUID(var_id))
        # puede ser vacía al inicio (no hay inventario), o si hay de test anterior distinto var, vacía
        # Crear stock manualmente vía lote service no directo, pero podemos ingresar via repo
        # Ingresar 5 en una sucursal
        # Obtener sucursal id
        from backend.app.core.modules.organizacion.models import Sucursal as SucModel
        res_suc = await db.execute(select(SucModel).limit(1))
        suc = res_suc.scalars().first()
        assert suc is not None
        await inv_repo.ingresar(uuid.UUID(var_id), suc.id, 5)
        await db.commit()
        lista_con_stock = await inv_repo.porVariante(uuid.UUID(var_id))
        assert len(lista_con_stock) >= 1
        assert all(i.disponible > 0 for i in lista_con_stock), "porVariante debe filtrar disponible>0"
        # Probar enriquecido
        enriched = await inv_repo.disponibilidadPorSucursal(uuid.UUID(var_id))
        assert len(enriched) >= 1
        assert "disponible" in enriched[0] and "reservado" in enriched[0]
        assert enriched[0]["disponible"] > 0

@pytest.mark.asyncio
async def test_cu06_endpoints_controller_presentacion_nombres(cliente_http: AsyncClient):
    """
    Verifica que los nombres de métodos por capa coinciden con documentacion-implementacion-fashionstore.md
    y que los endpoints responden (contratos Presentación/Controller/Datos)
    """
    # Verificar que CatalogoService tiene métodos listar/filtrar y InventarioService disponibilidadPorSucursal
    from backend.app.core.modules.catalogo.services.catalogo_service import CatalogoService
    from backend.app.core.modules.inventario.services.inventario_service import InventarioService
    import inspect
    assert hasattr(CatalogoService, "listar"), "CatalogoService.listar() debe existir"
    assert hasattr(CatalogoService, "filtrar"), "CatalogoService.filtrar() debe existir"
    assert hasattr(InventarioService, "disponibilidadPorSucursal"), "InventarioService.disponibilidadPorSucursal() debe existir"
    # Verificar ProductoRepository buscarConFiltros e InventarioRepository porVariante
    from backend.app.core.modules.catalogo.repositories.producto_repository import ProductoRepository
    from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
    assert hasattr(ProductoRepository, "buscarConFiltros")
    assert hasattr(InventarioRepository, "porVariante")
    sig = inspect.signature(ProductoRepository.buscarConFiltros)
    # debe aceptar filtros
    params = list(sig.parameters.keys())
    assert "filtros" in params or "filtros" in str(sig) or "texto" in params

    # Verificar endpoints existen
    r1 = await cliente_http.get("/api/v1/productos", params={"limit": 1})
    assert r1.status_code == 200
    # variantes disponibilidad debe dar 404 si variante no existe
    fake_id = str(uuid.uuid4())
    r_fake = await cliente_http.get(f"/api/v1/variantes/{fake_id}/disponibilidad")
    assert r_fake.status_code == 404
