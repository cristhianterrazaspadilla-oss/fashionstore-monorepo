"""Pruebas HTTP de aceptación/rechazo para CU03/CU04/CU16/CU18."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest


def ahora() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_http_reserva_online_aceptada_idempotente_y_visita_invalida(
    escenario, http
):
    http.usar(escenario.usuario_a)
    clave = str(uuid.uuid4())
    cuerpo = {
        "sucursal_destino_id": str(escenario.sucursal_a_id),
        "fecha_visita": (ahora() + timedelta(hours=1)).isoformat(),
        "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
    }
    primera = await http.cliente.post(
        "/api/v1/reservas", json=cuerpo, headers={"Idempotency-Key": clave}
    )
    assert primera.status_code == 201, primera.text
    reserva = primera.json()
    assert reserva["empresa_id"] == str(escenario.empresa_a_id)
    assert reserva["origen_plazo_en"] is not None

    repetida = await http.cliente.post(
        "/api/v1/reservas", json=cuerpo, headers={"Idempotency-Key": clave}
    )
    assert repetida.status_code == 201
    assert repetida.json()["id"] == reserva["id"]

    alterada = {
        **cuerpo,
        "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
    }
    conflicto = await http.cliente.post(
        "/api/v1/reservas", json=alterada, headers={"Idempotency-Key": clave}
    )
    assert conflicto.status_code == 409

    invalida = {
        **cuerpo,
        "fecha_visita": (ahora() - timedelta(hours=1)).isoformat(),
    }
    respuesta_invalida = await http.cliente.post(
        "/api/v1/reservas",
        json=invalida,
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert respuesta_invalida.status_code == 422

    http.usar(escenario.usuario_b)
    ajena = await http.cliente.get(f"/api/v1/reservas/{reserva['id']}")
    assert ajena.status_code == 404


@pytest.mark.asyncio
async def test_http_sin_empresa_no_recibe_datos_de_negocio(escenario, http):
    http.usar(escenario.usuario_global_sin_empresa)
    listado = await http.cliente.get("/api/v1/reservas")
    assert listado.status_code == 400

    crear = await http.cliente.post(
        "/api/v1/reservas",
        json={
            "sucursal_destino_id": str(escenario.sucursal_a_id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert crear.status_code == 400


@pytest.mark.asyncio
async def test_http_sincronizacion_referencia_operacion_y_consulta(
    escenario, http
):
    http.usar(escenario.usuario_a)
    dispositivo = str(uuid.uuid4())
    referencia = await http.cliente.get(
        "/api/v1/sincronizacion/referencia-horaria",
        params={"dispositivo_id": dispositivo},
    )
    assert referencia.status_code == 200, referencia.text
    datos_ref = referencia.json()

    instante = ahora()
    cuerpo = {
        "version_esquema": 1,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_RESERVA",
        "creada_local_en": instante.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": dispositivo,
        "secuencia_local": 1,
        "referencia_horaria_id": datos_ref["referencia_horaria_id"],
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "visita_en": (instante + timedelta(hours=1)).isoformat(),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    aceptada = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=cuerpo)
    assert aceptada.status_code == 200, aceptada.text
    assert aceptada.json()["estado"] == "ACEPTADA"

    reintento = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=cuerpo)
    assert reintento.status_code == 200
    assert reintento.json()["recurso_id"] == aceptada.json()["recurso_id"]

    consulta = await http.cliente.get(
        f"/api/v1/sincronizacion/operaciones/{cuerpo['operacion_id']}"
    )
    assert consulta.status_code == 200
    assert consulta.json()["estado"] == "ACEPTADA"

    sin_visita = {**cuerpo, "operacion_id": str(uuid.uuid4())}
    sin_visita["datos"] = {
        "sucursal_id": str(escenario.sucursal_a_id),
        "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
    }
    sin_visita["secuencia_local"] = 2
    rechazo_pydantic = await http.cliente.post(
        "/api/v1/sincronizacion/operaciones", json=sin_visita
    )
    assert rechazo_pydantic.status_code == 422

    http.usar(escenario.usuario_b)
    ajena = await http.cliente.get(
        f"/api/v1/sincronizacion/operaciones/{cuerpo['operacion_id']}"
    )
    assert ajena.status_code == 404


@pytest.mark.asyncio
async def test_http_descarga_catalogo_exige_empresa(escenario, http):
    respuesta = await http.cliente.get(
        "/api/v1/catalogo/descarga", params={"empresa_codigo": escenario.codigo_a}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["empresa_id"] == str(escenario.empresa_a_id)
    assert cuerpo["total_productos"] == 1

    sin_contexto = await http.cliente.get("/api/v1/catalogo/descarga")
    assert sin_contexto.status_code == 400
