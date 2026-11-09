import uuid
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_registro_cliente_exitoso(cliente_http: AsyncClient):
    uid = uuid.uuid4().hex[:8]
    correo = f"carlos.{uid}@example.com"
    payload = {
        "empresa_codigo": "fashionstore",
        "nombres": "Carlos",
        "apellidos": "Santistevan",
        "correo_electronico": correo,
        "contrasenia": "passwordSeguro123",
        "telefono": "+591 70012345",
        "direccion_referencia": "Av. San Martín y 3er Anillo, Santa Cruz",
        "fecha_nacimiento": "1998-05-15",
        "preferencias": {"estilo": "casual", "talla_favorita": "M"}
    }

    respuesta = await cliente_http.post("/api/v1/clientes", json=payload)
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["correo_electronico"] == correo
    assert datos["nombres"] == "Carlos"
    assert datos["apellidos"] == "Santistevan"
    assert datos["nombre_completo"] == "Carlos Santistevan"
    assert datos["rol"] in ["CLIENTE", "Cliente"]
    assert datos["estado"] == "ACTIVO"
    assert "id" in datos
    assert "usuario_id" in datos

@pytest.mark.asyncio
async def test_registro_cliente_correo_duplicado_rechazado(cliente_http: AsyncClient):
    uid = uuid.uuid4().hex[:8]
    correo = f"mariana.{uid}@example.com"
    payload = {
        "empresa_codigo": "fashionstore",
        "nombres": "Mariana",
        "apellidos": "Vargas",
        "correo_electronico": correo,
        "contrasenia": "clave123456",
        "telefono": "+591 71122334"
    }

    # Primer registro: OK
    resp1 = await cliente_http.post("/api/v1/clientes", json=payload)
    assert resp1.status_code == 201

    # Segundo registro con mismo correo: Conflicto 409
    resp2 = await cliente_http.post("/api/v1/clientes", json=payload)
    assert resp2.status_code == 409
    assert "ya se encuentra registrado" in resp2.json()["detail"]

@pytest.mark.asyncio
async def test_inicio_sesion_exitoso_y_fallido(cliente_http: AsyncClient):
    uid = uuid.uuid4().hex[:8]
    correo = f"lucia.{uid}@example.com"
    payload_reg = {
        "empresa_codigo": "fashionstore",
        "nombres": "Lucía",
        "apellidos": "Mendez",
        "correo_electronico": correo,
        "contrasenia": "secreto2026",
        "telefono": "+591 77889900"
    }
    await cliente_http.post("/api/v1/clientes", json=payload_reg)

    # 1. Login con contraseña incorrecta -> 401
    resp_bad_pass = await cliente_http.post("/api/v1/sesion", json={
        "correo_electronico": correo,
        "contrasenia": "clave_equivocada"
    })
    assert resp_bad_pass.status_code == 401

    # 2. Login con correo inexistente -> 401
    resp_bad_user = await cliente_http.post("/api/v1/sesion", json={
        "correo_electronico": "no_existe_999@example.com",
        "contrasenia": "secreto2026"
    })
    assert resp_bad_user.status_code == 401

    # 3. Login correcto -> 200 con Token JWT
    resp_login = await cliente_http.post("/api/v1/sesion", json={
        "correo_electronico": correo,
        "contrasenia": "secreto2026"
    })
    assert resp_login.status_code == 200
    datos_login = resp_login.json()
    assert "access_token" in datos_login
    assert datos_login["token_type"] == "bearer"
    assert datos_login["usuario"]["correo_electronico"] == correo
    assert datos_login["usuario"]["rol"] in ["CLIENTE", "Cliente"]
