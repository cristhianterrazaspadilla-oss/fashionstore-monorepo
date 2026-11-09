"""Pruebas backend de limpieza de campos opcionales (Ciclo 3).

Verifica la regla estricta:
- Omisión de campo: conserva el valor actual existente.
- Valor null explícito: limpia / elimina el valor existente dejándolo en None.
- Valor definido: reemplaza con el nuevo valor.

Aplica para:
- Producto: proveedor_principal_id, categoria_id, descripcion, marca, genero.
- Variante: codigo_barras, peso_gramos, recurso_prueba_virtual.
- Promoción: descripcion, vigencia_fin.
"""
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_limpieza_campos_opcionales_producto(cliente_http: AsyncClient):
    uid = uuid.uuid4().hex[:6]

    # Crear maestros de soporte
    resp_cat = await cliente_http.post("/api/v1/categorias", json={"nombre": f"Cat Test {uid}"})
    assert resp_cat.status_code == 201
    categoria_id = resp_cat.json()["id"]

    resp_prov = await cliente_http.post(
        "/api/v1/proveedores",
        json={"razon_social": f"Prov Test {uid}", "nit": f"990990{uid}"}
    )
    assert resp_prov.status_code == 201
    proveedor_id = resp_prov.json()["id"]

    # 1. Crear producto con todos los campos opcionales poblados
    payload_crear = {
        "nombre": f"Producto Original {uid}",
        "descripcion": "Descripción inicial",
        "categoria_id": categoria_id,
        "proveedor_principal_id": proveedor_id,
        "genero": "UNISEX",
        "marca": "MarcaFashion",
        "precio_base": 150.00,
        "activo": True,
    }
    resp = await cliente_http.post("/api/v1/productos", json=payload_crear)
    assert resp.status_code == 201, resp.text
    prod_id = resp.json()["id"]

    # Comprobación de estado inicial
    assert resp.json()["descripcion"] == "Descripción inicial"
    assert resp.json()["categoria_id"] == categoria_id
    assert resp.json()["proveedor_principal_id"] == proveedor_id
    assert resp.json()["genero"] == "UNISEX"
    assert resp.json()["marca"] == "MarcaFashion"

    # 2. Caso 1: Omisión CONSERVA los valores
    resp_omision = await cliente_http.put(
        f"/api/v1/productos/{prod_id}",
        json={"nombre": f"Producto Renombrado {uid}"}
    )
    assert resp_omision.status_code == 200, resp_omision.text
    prod_omision = resp_omision.json()
    assert prod_omision["nombre"] == f"Producto Renombrado {uid}"
    assert prod_omision["descripcion"] == "Descripción inicial"
    assert prod_omision["categoria_id"] == categoria_id
    assert prod_omision["proveedor_principal_id"] == proveedor_id
    assert prod_omision["genero"] == "UNISEX"
    assert prod_omision["marca"] == "MarcaFashion"

    # 3. Caso 2: null LIMPIA los valores existentes a None
    resp_null = await cliente_http.put(
        f"/api/v1/productos/{prod_id}",
        json={
            "descripcion": None,
            "categoria_id": None,
            "proveedor_principal_id": None,
            "genero": None,
            "marca": None,
        }
    )
    assert resp_null.status_code == 200, resp_null.text
    prod_null = resp_null.json()
    assert prod_null["descripcion"] is None
    assert prod_null["categoria_id"] is None
    assert prod_null["proveedor_principal_id"] is None
    assert prod_null["genero"] is None
    assert prod_null["marca"] is None

    # 4. Caso 3: Valor definido REEMPLAZA
    resp_reemplazo = await cliente_http.put(
        f"/api/v1/productos/{prod_id}",
        json={
            "descripcion": "Nueva descripción actualizada",
            "categoria_id": categoria_id,
            "proveedor_principal_id": proveedor_id,
            "genero": "MUJER",
            "marca": "UrbanBoutique",
        }
    )
    assert resp_reemplazo.status_code == 200, resp_reemplazo.text
    prod_reemplazo = resp_reemplazo.json()
    assert prod_reemplazo["descripcion"] == "Nueva descripción actualizada"
    assert prod_reemplazo["categoria_id"] == categoria_id
    assert prod_reemplazo["proveedor_principal_id"] == proveedor_id
    assert prod_reemplazo["genero"] == "MUJER"
    assert prod_reemplazo["marca"] == "UrbanBoutique"


@pytest.mark.asyncio
async def test_limpieza_campos_opcionales_variante(cliente_http: AsyncClient):
    uid = uuid.uuid4().hex[:6]

    # Crear maestros requeridos
    resp_talla = await cliente_http.post("/api/v1/tallas", json={"nombre": f"T-{uid}", "orden": 1})
    assert resp_talla.status_code == 201
    talla_id = resp_talla.json()["id"]

    resp_color = await cliente_http.post("/api/v1/colores", json={"nombre": f"C-{uid}", "codigo_hex": "#112233"})
    assert resp_color.status_code == 201
    color_id = resp_color.json()["id"]

    resp_prod = await cliente_http.post(
        "/api/v1/productos",
        json={"nombre": f"Prod Var {uid}", "precio_base": 100.00}
    )
    assert resp_prod.status_code == 201
    producto_id = resp_prod.json()["id"]

    # 1. Crear variante con campos opcionales poblados
    cb_original = f"CB-{uid}-01"
    sku_original = f"SKU-{uid}-01"
    resp_var = await cliente_http.post(
        "/api/v1/variantes",
        json={
            "producto_id": producto_id,
            "talla_id": talla_id,
            "color_id": color_id,
            "sku": sku_original,
            "codigo_barras": cb_original,
            "precio": 120.00,
            "peso_gramos": 250,
            "recurso_prueba_virtual": "camisa_recurso.glb",
            "activa": True,
        }
    )
    assert resp_var.status_code == 201, resp_var.text
    var_id = resp_var.json()["id"]
    assert resp_var.json()["codigo_barras"] == cb_original
    assert resp_var.json()["peso_gramos"] == 250
    assert resp_var.json()["recurso_prueba_virtual"] == "camisa_recurso.glb"

    # 2. Caso 1: Omisión CONSERVA los valores
    resp_omision = await cliente_http.put(
        f"/api/v1/variantes/{var_id}",
        json={"precio": 130.00}
    )
    assert resp_omision.status_code == 200, resp_omision.text
    var_omision = resp_omision.json()
    assert float(var_omision["precio"]) == 130.00
    assert var_omision["codigo_barras"] == cb_original
    assert var_omision["peso_gramos"] == 250
    assert var_omision["recurso_prueba_virtual"] == "camisa_recurso.glb"

    # 3. Caso 2: null LIMPIA los valores existentes a None
    resp_null = await cliente_http.put(
        f"/api/v1/variantes/{var_id}",
        json={
            "codigo_barras": None,
            "peso_gramos": None,
            "recurso_prueba_virtual": None,
        }
    )
    assert resp_null.status_code == 200, resp_null.text
    var_null = resp_null.json()
    assert var_null["codigo_barras"] is None
    assert var_null["peso_gramos"] is None
    assert var_null["recurso_prueba_virtual"] is None

    # 4. Caso 3: Valor definido REEMPLAZA
    cb_nuevo = f"CB-{uid}-02"
    resp_reemplazo = await cliente_http.put(
        f"/api/v1/variantes/{var_id}",
        json={
            "codigo_barras": cb_nuevo,
            "peso_gramos": 400,
            "recurso_prueba_virtual": "recurso_nuevo.glb",
        }
    )
    assert resp_reemplazo.status_code == 200, resp_reemplazo.text
    var_reemplazo = resp_reemplazo.json()
    assert var_reemplazo["codigo_barras"] == cb_nuevo
    assert var_reemplazo["peso_gramos"] == 400
    assert var_reemplazo["recurso_prueba_virtual"] == "recurso_nuevo.glb"


@pytest.mark.asyncio
async def test_limpieza_campos_opcionales_promocion(cliente_http: AsyncClient):
    uid = uuid.uuid4().hex[:6]
    ahora = datetime.now(timezone.utc)
    fin_original = ahora + timedelta(days=10)

    # 1. Crear promoción con descripción y vigencia_fin
    codigo = f"PROMO-{uid}"
    resp_crear = await cliente_http.post(
        "/api/v1/promociones",
        json={
            "codigo": codigo,
            "nombre": f"Promoción Test {uid}",
            "descripcion": "Descripción de temporada",
            "tipo": "PORCENTAJE",
            "valor": 15.00,
            "activa": True,
            "vigencia_inicio": ahora.isoformat(),
            "vigencia_fin": fin_original.isoformat(),
        }
    )
    assert resp_crear.status_code == 201, resp_crear.text
    promo_id = resp_crear.json()["id"]
    assert resp_crear.json()["descripcion"] == "Descripción de temporada"
    assert resp_crear.json()["vigencia_fin"] is not None

    # 2. Caso 1: Omisión CONSERVA los valores
    resp_omision = await cliente_http.patch(
        f"/api/v1/promociones/{promo_id}",
        json={"nombre": f"Promo Nombre Editado {uid}"}
    )
    assert resp_omision.status_code == 200, resp_omision.text
    promo_omision = resp_omision.json()
    assert promo_omision["nombre"] == f"Promo Nombre Editado {uid}"
    assert promo_omision["descripcion"] == "Descripción de temporada"
    assert promo_omision["vigencia_fin"] is not None

    # 3. Caso 2: null LIMPIA los valores opcionales
    resp_null = await cliente_http.patch(
        f"/api/v1/promociones/{promo_id}",
        json={
            "descripcion": None,
            "vigencia_fin": None,
        }
    )
    assert resp_null.status_code == 200, resp_null.text
    promo_null = resp_null.json()
    assert promo_null["descripcion"] is None
    assert promo_null["vigencia_fin"] is None

    # 4. Caso 3: Valor definido REEMPLAZA
    nueva_fin = ahora + timedelta(days=20)
    resp_reemplazo = await cliente_http.patch(
        f"/api/v1/promociones/{promo_id}",
        json={
            "descripcion": "Nueva descripción de promo",
            "vigencia_fin": nueva_fin.isoformat(),
        }
    )
    assert resp_reemplazo.status_code == 200, resp_reemplazo.text
    promo_reemplazo = resp_reemplazo.json()
    assert promo_reemplazo["descripcion"] == "Nueva descripción de promo"
    assert promo_reemplazo["vigencia_fin"] is not None
