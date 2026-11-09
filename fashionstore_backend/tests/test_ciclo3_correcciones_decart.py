"""Corrección 3 — SDK Python Decart real (contrato token.api_key, etc.)."""
import asyncio
import logging
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from backend.app.core.modules.experiencia_cliente.integraciones import decart_client as dc
from backend.app.core import rate_limit
from backend.app.core.config import settings
from tests.helpers_ciclo2 import crear_cliente, sucursal_semilla
from tests.helpers_ciclo3 import (
    clave, crear_variante_probador, desinstalar_decart_falso,
    instalar_decart_falso, instalar_validador_falso, desinstalar_validador_falso,
)


@pytest.fixture()
def _ctx(monkeypatch):
    monkeypatch.setattr(settings, "DECART_ENABLED", True)
    monkeypatch.setattr(settings, "DECART_API_KEY", "dk_test_falsa")
    monkeypatch.setattr(settings, "DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    monkeypatch.setenv("DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    rate_limit.reiniciar_limites()
    instalar_decart_falso("tok-corto-prueba")
    instalar_validador_falso("ok")
    yield
    desinstalar_decart_falso()
    desinstalar_validador_falso()
    rate_limit.reiniciar_limites()


async def test_sdk_snake_case_ttl_modelo_duracion(cliente_http: AsyncClient, _ctx, monkeypatch):
    """Fake fiel con api_key/expires_at/constraints/permissions; contrato 60/120/lucy-2.5."""
    capturas = {}

    class _SDK:
        def __init__(self):
            self.api_key = "tok-sdk-fiel"
            self.expires_at = (datetime.now(timezone.utc)).isoformat()
            self.permissions = {"models": ["lucy-2.5"]}
            self.constraints = {"realtime": {"maxSessionDuration": 120}}

    async def _falso(cid):
        capturas["p"] = dc.parametros_token(cid)
        return _SDK()

    dc.fijar_creador_falso(_falso)
    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_probador(cliente_http, suc, 2, tag="sdk")
    async with await crear_cliente("sdk") as cli:
        r = await cli.client.post(
            "/api/v1/probador/autorizaciones",
            json={"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 201, r.text
        dto = r.json()
        assert dto["client_token"] == "tok-sdk-fiel"
        assert dto["modelo"] == "lucy-2.5"
        assert dto["max_session_duration_seconds"] == 120
        assert capturas["p"]["expires_in"] == 60
        assert capturas["p"]["allowed_models"] == ["lucy-2.5"]
        assert capturas["p"]["constraints"] == {"realtime": {"maxSessionDuration": 120}}
        assert "allowedOrigins" not in capturas["p"] and "allowed_origins" not in capturas["p"]


async def test_sdk_sin_token_502(cliente_http: AsyncClient, _ctx):
    class _Vacio:
        api_key = ""
        expires_at = None
        permissions = None
        constraints = None

    async def _falso(cid):
        return _Vacio()

    dc.fijar_creador_falso(_falso)
    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_probador(cliente_http, suc, 2, tag="sdkv")
    async with await crear_cliente("sdkv") as cli:
        r = await cli.client.post(
            "/api/v1/probador/autorizaciones",
            json={"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"},
            headers={"Idempotency-Key": clave()})
        assert r.status_code == 502, r.text


async def test_sdk_timeout_503_y_rechazo_502(cliente_http: AsyncClient, _ctx, monkeypatch, caplog):
    """Timeout/indisponibilidad -> exactamente 503; rechazo válido -> exactamente 502.

    El doble recorre el mismo camino relevante que producción
    (`emitir_token` -> servicio -> endpoint): no se parchea
    `crear_token_cliente`, porque eso evitaría validar el mapeo real.
    """
    import logging

    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_probador(cliente_http, suc, 2, tag="sdkt")
    cuerpo = {"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"}

    async def _timeout(cid):
        raise asyncio.TimeoutError("timeout")

    async with await crear_cliente("sdkt") as cli:
        # Timeout del proveedor por el camino real del fake -> 503 tipado.
        dc.fijar_creador_falso(_timeout)
        try:
            with caplog.at_level(logging.INFO):
                r = await cli.client.post(
                    "/api/v1/probador/autorizaciones",
                    json=cuerpo,
                    headers={"Idempotency-Key": clave()})
            assert r.status_code == 503, r.text
            detalle = r.json().get("detail", {})
            assert detalle.get("codigo") == "DECART_NO_DISPONIBLE", r.text
            assert "dk_test_falsa" not in r.text
            assert "tok-" not in r.text
            volcado = "\n".join(getattr(rec, "message", "") for rec in caplog.records)
            assert "dk_test_falsa" not in volcado
        finally:
            instalar_decart_falso("tok-corto-prueba")
            caplog.clear()

    async def _red_caida(cid):
        raise ConnectionError("conexión rechazada por la red")

    async with await crear_cliente("sdktn") as clin:
        # Indisponibilidad de red por el mismo camino -> exactamente 503.
        dc.fijar_creador_falso(_red_caida)
        try:
            r = await clin.client.post(
                "/api/v1/probador/autorizaciones",
                json=cuerpo,
                headers={"Idempotency-Key": clave()})
            assert r.status_code == 503, r.text
            assert r.json().get("detail", {}).get("codigo") == "DECART_NO_DISPONIBLE", r.text
        finally:
            instalar_decart_falso("tok-corto-prueba")

    async def _rechazo(cid):
        raise dc.DecartError("crédito agotado")

    # Rechazo válido del proveedor por el mismo camino -> exactamente 502.
    dc.fijar_creador_falso(_rechazo)
    try:
        async with await crear_cliente("sdkr") as cli2:
            r = await cli2.client.post(
                "/api/v1/probador/autorizaciones",
                json=cuerpo,
                headers={"Idempotency-Key": clave()})
            assert r.status_code == 502, r.text
            detalle = r.json().get("detail", {})
            assert detalle.get("codigo") == "DECART_RECHAZO", r.text
            assert "dk_test_falsa" not in r.text
    finally:
        instalar_decart_falso("tok-corto-prueba")


async def test_deshabilitado_503_y_sin_secretos_en_logs(
    cliente_http: AsyncClient, monkeypatch, caplog,
):
    monkeypatch.setattr(settings, "DECART_ENABLED", False)
    monkeypatch.setattr(settings, "DECART_API_KEY", "")
    monkeypatch.setattr(settings, "DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    instalar_validador_falso("ok")
    try:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_probador(cliente_http, suc, 2, tag="sdko")
        async with await crear_cliente("sdko") as cli:
            with caplog.at_level(logging.INFO):
                r = await cli.client.post(
                    "/api/v1/probador/autorizaciones",
                    json={"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"},
                    headers={"Idempotency-Key": clave()})
            assert r.status_code == 503, r.text
            volcado = "\n".join(getattr(rec, "message", "") for rec in caplog.records)
            assert "dk_test_falsa" not in volcado
            assert "tok-corto" not in volcado
    finally:
        desinstalar_validador_falso()


def test_rest_camelcase_sin_allowed_origins():
    cuerpo = dc.parametros_rest("cid-1")
    assert cuerpo["expiresIn"] == 60
    assert cuerpo["allowedModels"] == ["lucy-2.5"]
    assert cuerpo["constraints"] == {"realtime": {"maxSessionDuration": 120}}
    assert "allowedOrigins" not in cuerpo
    sdk = dc.parametros_token("cid-1")
    assert sdk["expires_in"] == 60 and sdk["allowed_models"] == ["lucy-2.5"]
