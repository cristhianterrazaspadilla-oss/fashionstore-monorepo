import uuid
import pytest
from httpx import AsyncClient
from tests.helpers_ciclo2 import crear_ciudad_plataforma, crear_superadmin

@pytest.mark.asyncio
async def test_crear_y_listar_ciudades(cliente_http: AsyncClient):
    uid = uuid.uuid4().hex[:6]
    nombre_ciudad = f"Cochabamba {uid}"

    # El catÃ¡logo global de ciudades solo lo gestiona el superadmin.
    async with await crear_superadmin() as plataforma:
        resp_crear = await plataforma.client.post(
            "/api/v1/ciudades", json={"nombre": nombre_ciudad}
        )
        assert resp_crear.status_code == 201, resp_crear.text
        datos = resp_crear.json()
        resp_dup = await plataforma.client.post(
            "/api/v1/ciudades", json={"nombre": nombre_ciudad}
        )
        assert resp_dup.status_code == 409
        resp_listar = await plataforma.client.get("/api/v1/ciudades")
        assert resp_listar.status_code == 200
        ciudades = resp_listar.json()
    assert datos["nombre"] == nombre_ciudad
    assert datos["activo"] == True
    ciudad_id = datos["id"]

    # 2-3. Duplicado y listado se comprobaron con el actor global autorizado.
    assert any(c["id"] == ciudad_id for c in ciudades)

@pytest.mark.asyncio
async def test_crear_sucursal_con_parametros_delivery(cliente_http: AsyncClient):
    # Crear o usar una ciudad
    uid = uuid.uuid4().hex[:6]
    ciudad = await crear_ciudad_plataforma(f"La Paz {uid}")
    ciudad_id = ciudad["id"]

    payload_sucursal = {
        "ciudad_id": ciudad_id,
        "nombre": "Sucursal San Miguel Calacoto",
        "direccion": "Av. Montenegro esq. Calle 21",
        "telefono": "+591 2 2778899",
        "numero_anillo": 2,
        "tarifa_base_delivery": "20.00",
        "incremento_anillo_delivery": "5.00",
        "anillo_minimo_delivery": 1,
        "anillo_maximo_delivery": 6,
        "delivery_activo": True
    }

    resp_sucursal = await cliente_http.post("/api/v1/sucursales", json=payload_sucursal)
    assert resp_sucursal.status_code == 201
    datos_suc = resp_sucursal.json()
    assert datos_suc["nombre"] == "Sucursal San Miguel Calacoto"
    assert datos_suc["ciudad_id"] == ciudad_id
    assert float(datos_suc["tarifa_base_delivery"]) == 20.00
    assert float(datos_suc["incremento_anillo_delivery"]) == 5.00
    assert datos_suc["delivery_activo"] == True

@pytest.mark.asyncio
async def test_configurar_tarifas_delivery_sucursal(cliente_http: AsyncClient):
    # 1. Obtener sucursales existentes
    resp_list = await cliente_http.get("/api/v1/sucursales")
    assert resp_list.status_code == 200
    sucursales = resp_list.json()
    assert len(sucursales) > 0
    sucursal = sucursales[0]
    sucursal_id = sucursal["id"]

    # 2. Actualizar tarifas de delivery
    payload_tarifas = {
        "tarifa_base_delivery": "18.50",
        "incremento_anillo_delivery": "4.00",
        "anillo_minimo_delivery": 1,
        "anillo_maximo_delivery": 9,
        "delivery_activo": True
    }

    resp_patch = await cliente_http.patch(
        f"/api/v1/sucursales/{sucursal_id}/tarifas",
        json=payload_tarifas
    )
    assert resp_patch.status_code == 200
    datos_actualizados = resp_patch.json()
    assert float(datos_actualizados["tarifa_base_delivery"]) == 18.50
    assert float(datos_actualizados["incremento_anillo_delivery"]) == 4.00
    assert datos_actualizados["anillo_maximo_delivery"] == 9
