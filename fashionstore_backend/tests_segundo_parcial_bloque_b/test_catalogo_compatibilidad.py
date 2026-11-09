"""Pruebas de compatibilidad del catálogo para CU03, CU05 y CU16.

Verifica:
1. GET /productos y GET /productos/{id} son públicos (no reservados a administrador)
   y devuelven ProductoPublicoDTO sin costos ni campos internos.
2. GET /variantes y GET /variantes/{id} son públicos y devuelven VariantePublicaDTO
   sin costo_promedio ni costo_ultimo.
3. El acceso administrativo conserva ProductoDTO y VarianteDTO con campos de costo
   mediante autorización empresarial.
4. Las respuestas públicas están aisladas a una sola empresa.
5. GET /variantes/{id}/disponibilidad solo devuelve sucursales de la empresa de la variante.
6. Compatibilidad legacy sin empresa_id ni empresa_codigo resuelve la empresa por defecto.
7. Simulación de llamadas de Angular y Flutter reales.
"""
import uuid
import pytest


@pytest.mark.asyncio
async def test_productos_publicos_sin_sesion_y_sin_campos_privados(escenario, http):
    """GET /productos es accesible públicamente y no expone campos privados."""
    http.usar(None)
    respuesta = await http.cliente.get(
        "/api/v1/productos",
        params={"empresa_id": str(escenario.empresa_a_id)},
    )
    assert respuesta.status_code == 200, respuesta.text
    items = respuesta.json()
    assert len(items) == 1
    prod = items[0]
    assert prod["id"] == str(escenario.producto_a_id)
    assert prod["nombre"].startswith("Producto A")
    # Campos que NO deben existir en ProductoPublicoDTO
    assert "costo_estandar" not in prod
    assert "margen_contribucion_minimo" not in prod
    assert "proveedor_principal_id" not in prod


@pytest.mark.asyncio
async def test_producto_detalle_publico_sin_sesion(escenario, http):
    """GET /productos/{id} es accesible públicamente sin sesión."""
    http.usar(None)
    respuesta = await http.cliente.get(
        f"/api/v1/productos/{escenario.producto_a_id}",
        params={"empresa_id": str(escenario.empresa_a_id)},
    )
    assert respuesta.status_code == 200, respuesta.text
    prod = respuesta.json()
    assert prod["id"] == str(escenario.producto_a_id)
    assert "proveedor_principal_id" not in prod
    assert "costo_estandar" not in prod


@pytest.mark.asyncio
async def test_variantes_publicas_no_exponen_costos_internos(escenario, http):
    """GET /variantes y GET /variantes/{id} públicos no exponen costo_promedio ni costo_ultimo."""
    http.usar(None)

    # 1. Listado público
    res_lista = await http.cliente.get(
        "/api/v1/variantes",
        params={"empresa_id": str(escenario.empresa_a_id)},
    )
    assert res_lista.status_code == 200, res_lista.text
    items = res_lista.json()
    assert len(items) >= 1
    for v in items:
        assert "costo_promedio" not in v, f"costo_promedio expuesto en variante pública: {v}"
        assert "costo_ultimo" not in v, f"costo_ultimo expuesto en variante pública: {v}"
        assert "precio" in v
        assert "sku" in v

    # 2. Detalle público
    res_det = await http.cliente.get(
        f"/api/v1/variantes/{escenario.variante_a_id}",
        params={"empresa_id": str(escenario.empresa_a_id)},
    )
    assert res_det.status_code == 200, res_det.text
    detalle = res_det.json()
    assert detalle["id"] == str(escenario.variante_a_id)
    assert "costo_promedio" not in detalle
    assert "costo_ultimo" not in detalle
    assert "precio" in detalle


@pytest.mark.asyncio
async def test_acceso_administrativo_conserva_costos(escenario, http):
    """Administrador autenticado con empresa sí recibe campos de costo y proveedor."""
    http.usar(escenario.usuario_admin_a)

    # 1. Productos admin
    res_prod = await http.cliente.get("/api/v1/productos")
    assert res_prod.status_code == 200
    prod = res_prod.json()[0]
    assert "proveedor_principal_id" in prod

    # 2. Variantes admin
    res_var = await http.cliente.get("/api/v1/variantes")
    assert res_var.status_code == 200
    variantes = res_var.json()
    assert len(variantes) >= 1
    v = variantes[0]
    assert "costo_promedio" in v, "costo_promedio debe estar presente para administrador"
    assert "costo_ultimo" in v, "costo_ultimo debe estar presente para administrador"

    # 3. Variante detalle admin
    res_v_det = await http.cliente.get(f"/api/v1/variantes/{escenario.variante_a_id}")
    assert res_v_det.status_code == 200
    v_det = res_v_det.json()
    assert "costo_promedio" in v_det
    assert "costo_ultimo" in v_det


@pytest.mark.asyncio
async def test_disponibilidad_solo_muestra_sucursales_de_la_misma_empresa(escenario, http):
    """GET /variantes/{id}/disponibilidad solo devuelve sucursales de la empresa de la variante."""
    http.usar(None)
    respuesta = await http.cliente.get(
        f"/api/v1/variantes/{escenario.variante_a_id}/disponibilidad"
    )
    assert respuesta.status_code == 200, respuesta.text
    items = respuesta.json()
    assert len(items) >= 1
    # Todas las sucursales devueltas deben ser de la empresa_a (sucursal_a_id), NINGUNA de empresa_b
    sucursales_ids = {it["sucursal_id"] for it in items}
    assert str(escenario.sucursal_a_id) in sucursales_ids
    assert str(escenario.sucursal_b_id) not in sucursales_ids


@pytest.mark.asyncio
async def test_compatibilidad_legacy_sin_empresa(escenario, http):
    """Peticiones legacy que no envían empresa_id ni empresa_codigo resuelven empresa por defecto."""
    http.usar(None)

    # 1. GET /productos sin params
    res_prod = await http.cliente.get("/api/v1/productos")
    assert res_prod.status_code == 200
    items_prod = res_prod.json()
    assert isinstance(items_prod, list)
    if items_prod:
        # Asegurar que son públicos
        assert "proveedor_principal_id" not in items_prod[0]
        assert "costo_estandar" not in items_prod[0]

    # 2. GET /variantes sin params
    res_var = await http.cliente.get("/api/v1/variantes")
    assert res_var.status_code == 200
    items_var = res_var.json()
    assert isinstance(items_var, list)
    if items_var:
        assert "costo_promedio" not in items_var[0]
        assert "costo_ultimo" not in items_var[0]

    # 3. GET /catalogo/filtros-opciones sin params
    res_filtros = await http.cliente.get("/api/v1/catalogo/filtros-opciones")
    assert res_filtros.status_code == 200
    filtros = res_filtros.json()
    assert "categorias" in filtros
    assert "marcas" in filtros


@pytest.mark.asyncio
async def test_llamadas_reales_angular_y_flutter(escenario, http):
    """Simula los contratos exactos que consumen los servicios de frontend-web y app-movil."""
    http.usar(None)

    # Angular - EnriquecimientoService / ProductoService
    # 1. this.http.get<ProductoDTO[]>(`${this.api}/productos?solo_activos=true&limit=100`)
    res_ng_prod = await http.cliente.get(
        "/api/v1/productos",
        params={"solo_activos": "true", "limit": 100, "empresa_id": str(escenario.empresa_a_id)},
    )
    assert res_ng_prod.status_code == 200
    assert len(res_ng_prod.json()) == 1

    # 2. this.http.get<VarianteDTO[]>(`${this.api}/variantes?solo_activas=true&limit=100`)
    res_ng_var = await http.cliente.get(
        "/api/v1/variantes",
        params={
            "producto_id": str(escenario.producto_a_id),
            "solo_activas": "true",
            "limit": 100,
        },
    )
    assert res_ng_var.status_code == 200
    assert len(res_ng_var.json()) == 3
    assert "costo_promedio" not in res_ng_var.json()[0]

    # 3. this.http.get<DisponibilidadItem[]>(`${this.api}/variantes/${varianteId}/disponibilidad`)
    res_ng_disp = await http.cliente.get(
        f"/api/v1/variantes/{escenario.variante_a_id}/disponibilidad"
    )
    assert res_ng_disp.status_code == 200
    assert any(d["sucursal_id"] == str(escenario.sucursal_a_id) for d in res_ng_disp.json())

    # Flutter - CatalogoService
    # 4. api.get<List>('/productos', ...)
    res_fl_prod = await http.cliente.get(
        "/api/v1/productos",
        params={"empresa_id": str(escenario.empresa_a_id)},
    )
    assert res_fl_prod.status_code == 200

    # 5. api.get('/productos/$id', ...)
    res_fl_det = await http.cliente.get(
        f"/api/v1/productos/{escenario.producto_a_id}",
        params={"empresa_id": str(escenario.empresa_a_id)},
    )
    assert res_fl_det.status_code == 200

    # 6. api.get('/catalogo/productos?empresa_codigo=$codigo', ...)
    res_fl_cat = await http.cliente.get(
        "/api/v1/catalogo/productos",
        params={"empresa_codigo": escenario.codigo_a},
    )
    assert res_fl_cat.status_code == 200
    assert len(res_fl_cat.json()) == 1

    # 7. api.get('/catalogo/filtros-opciones?empresa_codigo=$codigo', ...)
    res_fl_filtros = await http.cliente.get(
        "/api/v1/catalogo/filtros-opciones",
        params={"empresa_codigo": escenario.codigo_a},
    )
    assert res_fl_filtros.status_code == 200
    assert "categorias" in res_fl_filtros.json()
