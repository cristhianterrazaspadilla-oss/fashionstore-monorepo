"""CU17 — Probador Decart Lucy 2.5: compatibilidad, autorización e higiene."""
import logging
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from backend.app.core.modules.experiencia_cliente.integraciones import decart_client
from backend.app.core import rate_limit
from backend.app.core.config import settings
from tests.helpers_ciclo2 import crear_cliente, sucursal_semilla
from tests.helpers_ciclo3 import (
    clave, crear_variante_probador, desinstalar_decart_falso, instalar_decart_falso,
    instalar_validador_falso,
)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    monkeypatch.setattr(settings, "DECART_ENABLED", True)
    monkeypatch.setattr(settings, "DECART_API_KEY", "dk_test_falsa")
    monkeypatch.setattr(settings, "DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    monkeypatch.setenv("DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    rate_limit.reiniciar_limites()
    capturas = instalar_decart_falso("tok-corto-prueba")
    from tests.helpers_ciclo3 import desinstalar_validador_falso, instalar_validador_falso

    instalar_validador_falso("ok")
    yield capturas
    desinstalar_decart_falso()
    desinstalar_validador_falso()
    rate_limit.reiniciar_limites()


async def test_recurso_prueba_virtual_y_reglas(cliente_http: AsyncClient):
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_probador(admin, suc, 3, tag="pv")
    async with await crear_cliente("pv") as cli:
        r = await cli.client.get(f"/api/v1/variantes/{var['variante_id']}/prueba-virtual")
        assert r.status_code == 200, r.text
        dto = r.json()
        assert dto["compatible"] is True and dto["modelo"] == "lucy-2.5", dto
        assert dto["proveedor"] == "DECART"
        assert dto["imagen_prenda_url"].startswith("https://"), dto
        assert "No garantiza talla" in dto["aviso_orientativo"] or "orientativa" in dto["aviso_orientativo"]
        # Variante inexistente -> 404.
        assert (await cli.client.get(
            f"/api/v1/variantes/{uuid.uuid4()}/prueba-virtual")).status_code == 404


async def test_variante_probador_no_se_comparte_entre_empresas(cliente_http: AsyncClient):
    """La cuenta Decart es global, pero el recurso sigue aislado por empresa."""
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.core.modules.experiencia_cliente.services.probador_service import ProbadorService
    from fastapi import HTTPException

    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_probador(cliente_http, suc, 0, tag="tenant")
    async with AsyncSessionLocal() as db:
        # Simula una sesión cliente de otro tenant sin crear datos ni persistir cambios.
        with pytest.raises(HTTPException) as error:
            await ProbadorService(db)._variante_compatible(
                uuid.UUID(var["variante_id"]), uuid.uuid4()
            )
    assert error.value.status_code == 404


async def test_autorizacion_token_modelo_ttl_duracion_e_idempotencia(
    cliente_http: AsyncClient, _limpio,
):
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_probador(admin, suc, 3, tag="au")
    async with await crear_cliente("au") as cli:
        k = clave()
        antes = datetime.now(timezone.utc)
        r = await cli.client.post(
            "/api/v1/probador/autorizaciones",
            json={"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"},
            headers={"Idempotency-Key": k})
        assert r.status_code == 201, r.text
        dto = r.json()
        assert dto["client_token"] == "tok-corto-prueba", dto
        assert dto["modelo"] == "lucy-2.5" and dto["max_session_duration_seconds"] == 120, dto
        expira = datetime.fromisoformat(dto["expires_at"])
        assert 50 <= (expira - antes).total_seconds() <= 70, dto
        # Contrato del SDK: expires_in=60, allowedModels, maxSessionDuration=120, sin allowedOrigins.
        params = _limpio["parametros"]
        assert params["expires_in"] == 60, params
        assert params["allowed_models"] == ["lucy-2.5"], params
        assert params["constraints"] == {"realtime": {"maxSessionDuration": 120}}, params
        assert "allowedOrigins" not in params, params
        # Idempotencia: misma clave + payload -> mismo token.
        r2 = await cli.client.post(
            "/api/v1/probador/autorizaciones",
            json={"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"},
            headers={"Idempotency-Key": k})
        assert r2.status_code == 201 and r2.json()["client_token"] == "tok-corto-prueba"
        # Misma clave + distinto payload -> 409.
        r3 = await cli.client.post(
            "/api/v1/probador/autorizaciones",
            json={"variante_id": str(uuid.uuid4()), "consentimiento_version": "decart-v1"},
            headers={"Idempotency-Key": k})
        assert r3.status_code == 409, r3.text
        # Consentimiento inválido -> 422.
        r4 = await cli.client.post(
            "/api/v1/probador/autorizaciones",
            json={"variante_id": var["variante_id"], "consentimiento_version": "v0"},
            headers={"Idempotency-Key": clave()})
        assert r4.status_code == 422, r4.text


async def test_deshabilitado_503_y_catalogo_sano(cliente_http: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "DECART_ENABLED", False)
    monkeypatch.setattr(settings, "DECART_API_KEY", "")
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_probador(admin, suc, 2, tag="off")
    async with await crear_cliente("off") as cli:
        r = await cli.client.post(
            "/api/v1/probador/autorizaciones",
            json={"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 503, r.text
        # Catálogo, carrito y reservas siguen funcionando.
        assert (await cli.client.get(
            f"/api/v1/variantes/{var['variante_id']}/prueba-virtual")).status_code == 200
        assert (await cli.client.get("/api/v1/carritos/mio",
                                     params={"canal": "WEB"})).status_code == 200


async def test_rate_limit_429(cliente_http: AsyncClient, monkeypatch, _limpio):
    monkeypatch.setattr(settings, "DECART_RATE_LIMIT_POR_MINUTO", 2)
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_probador(admin, suc, 2, tag="rl")
    async with await crear_cliente("rl") as cli:
        for _ in range(2):
            r = await cli.client.post(
                "/api/v1/probador/autorizaciones",
                json={"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"},
                headers={"Idempotency-Key": clave()})
            assert r.status_code == 201, r.text
        r = await cli.client.post(
            "/api/v1/probador/autorizaciones",
            json={"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 429, r.text


async def test_proveedor_indisponible_502_o_503_y_sin_secretos_en_logs(
    cliente_http: AsyncClient, monkeypatch, caplog,
):
    """Sin mock del SDK y con clave: el fallo del proveedor es 502/503 tipado."""
    from backend.app.core.modules.experiencia_cliente.integraciones import decart_client as dc

    desinstalar_decart_falso()

    async def _falla(correlation_id: str):
        raise dc.DecartError("crédito agotado")

    monkeypatch.setattr(dc, "crear_token_cliente", _falla)
    admin = cliente_http
    suc = await sucursal_semilla(admin)
    var = await crear_variante_probador(admin, suc, 2, tag="e502")
    async with await crear_cliente("e502") as cli:
        with caplog.at_level(logging.INFO):
            r = await cli.client.post(
                "/api/v1/probador/autorizaciones",
                json={"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"},
                headers={"Idempotency-Key": clave()})
        assert r.status_code in (502, 503), r.text
        # Nunca secreto ni contenido audiovisual en logs.
        volcado = "\n".join(getattr(rec, "message", "") for rec in caplog.records)
        assert "dk_test_falsa" not in volcado
        assert "tok-corto" not in volcado
        for prohibido in ("Base64", "frame", "rostro", "SDP"):
            assert prohibido not in volcado
    instalar_decart_falso("tok-corto-prueba")
