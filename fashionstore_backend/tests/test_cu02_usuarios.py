import uuid
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_listar_roles(cliente_http: AsyncClient):
    resp = await cliente_http.get("/api/v1/roles")
    assert resp.status_code == 200
    roles = resp.json()
    assert len(roles) >= 5
    nombres_roles = [r["nombre"] for r in roles]
    for rol_esperado in ["ADMINISTRADOR", "ENCARGADO", "CAJERO", "PROVEEDOR", "CLIENTE"]:
        assert rol_esperado in nombres_roles

@pytest.mark.asyncio
async def test_crear_usuario_con_rol_unico(cliente_http: AsyncClient):
    # 1. Obtener sucursal para encargado
    resp_suc = await cliente_http.get("/api/v1/sucursales")
    suc_id = resp_suc.json()[0]["id"] if resp_suc.json() else None
    # 1b. Obtener ID del rol ENCARGADO
    resp_roles = await cliente_http.get("/api/v1/roles")
    roles = resp_roles.json()
    rol_encargado = next(r for r in roles if r["nombre"] == "ENCARGADO")

    uid = uuid.uuid4().hex[:8]
    correo = f"encargado.{uid}@fashionstore.com"
    payload = {
        "rol_id": rol_encargado["id"],
        "nombres": "Pedro",
        "apellidos": "Alvarez",
        "correo_electronico": correo,
        "contrasenia": "claveSegura123",
        "telefono": "+591 78945612",
        "sucursal_id": suc_id,
        "cargo": "Encargado de Sucursal"
    }

    resp = await cliente_http.post("/api/v1/usuarios", json=payload)
    assert resp.status_code == 201
    datos = resp.json()
    assert datos["correo_electronico"] == correo
    assert datos["rol_id"] == rol_encargado["id"]
    assert datos["rol_nombre"] == "ENCARGADO"
    assert datos["estado"] == "ACTIVO"

@pytest.mark.asyncio
async def test_asignar_y_cambiar_rol_usuario(cliente_http: AsyncClient):
    resp_roles = await cliente_http.get("/api/v1/roles")
    roles = resp_roles.json()
    rol_cajero = next(r for r in roles if r["nombre"] == "CAJERO")
    rol_encargado = next(r for r in roles if r["nombre"] == "ENCARGADO")

    uid = uuid.uuid4().hex[:8]
    correo = f"personal.{uid}@fashionstore.com"
    resp_suc2 = await cliente_http.get("/api/v1/sucursales")
    suc_id2 = resp_suc2.json()[0]["id"] if resp_suc2.json() else None
    payload = {
        "rol_id": rol_cajero["id"],
        "nombres": "Roberto",
        "apellidos": "Gomez",
        "correo_electronico": correo,
        "contrasenia": "clave123456",
        "telefono": "+591 71234567",
        "sucursal_id": suc_id2,
        "cargo": "Cajero"
    }

    # Crear como Cajero
    resp_crear = await cliente_http.post("/api/v1/usuarios", json=payload)
    usuario_id = resp_crear.json()["id"]

    # Cambiar rol a Encargado
    resp_cambio = await cliente_http.patch(
        f"/api/v1/usuarios/{usuario_id}/rol",
        json={"rol_id": rol_encargado["id"]}
    )
    assert resp_cambio.status_code == 200
    datos_actualizados = resp_cambio.json()
    assert datos_actualizados["rol_id"] == rol_encargado["id"]
    assert datos_actualizados["rol_nombre"] == "ENCARGADO"

@pytest.mark.asyncio
async def test_desactivar_usuario_y_bloqueo_login(cliente_http: AsyncClient):
    resp_roles = await cliente_http.get("/api/v1/roles")
    roles = resp_roles.json()
    rol_cajero = next(r for r in roles if r["nombre"] == "CAJERO")

    uid = uuid.uuid4().hex[:8]
    correo = f"cajero.inactivo.{uid}@fashionstore.com"
    resp_suc3 = await cliente_http.get("/api/v1/sucursales")
    suc_id3 = resp_suc3.json()[0]["id"] if resp_suc3.json() else None
    payload = {
        "rol_id": rol_cajero["id"],
        "nombres": "Ana",
        "apellidos": "Rios",
        "correo_electronico": correo,
        "contrasenia": "claveAna2026",
        "telefono": "+591 79998877",
        "sucursal_id": suc_id3,
        "cargo": "Cajero"
    }

    resp_crear = await cliente_http.post("/api/v1/usuarios", json=payload)
    usuario_id = resp_crear.json()["id"]

    # Desactivar usuario
    resp_desactivar = await cliente_http.patch(f"/api/v1/usuarios/{usuario_id}/desactivar")
    assert resp_desactivar.status_code == 200
    assert resp_desactivar.json()["estado"] == "INACTIVO"

    # Intentar login con usuario desactivado -> debe retornar 403 Forbidden
    resp_login = await cliente_http.post("/api/v1/sesion", json={
        "correo_electronico": correo,
        "contrasenia": "claveAna2026"
    })
    assert resp_login.status_code == 403
    assert "inactiva" in resp_login.json()["detail"]
