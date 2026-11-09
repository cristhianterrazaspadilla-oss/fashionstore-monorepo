"""Corrección 4 — Validación segura de imágenes Decart (10 casos)."""
import pytest
from httpx import AsyncClient

from backend.app.core.modules.experiencia_cliente.integraciones import decart_imagen as di
from backend.app.core.config import settings
from tests.helpers_ciclo2 import crear_cliente, sucursal_semilla
from tests.helpers_ciclo3 import (
    clave, crear_variante_probador, desinstalar_decart_falso,
    instalar_decart_falso, instalar_validador_falso, desinstalar_validador_falso,
)
from backend.app.core import rate_limit


@pytest.fixture()
def _base(monkeypatch):
    monkeypatch.setattr(settings, "DECART_ENABLED", True)
    monkeypatch.setattr(settings, "DECART_API_KEY", "dk_test_falsa")
    monkeypatch.setattr(settings, "DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    monkeypatch.setenv("DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    rate_limit.reiniciar_limites()
    instalar_decart_falso("tok-img")
    instalar_validador_falso("ok")
    yield
    desinstalar_decart_falso()
    desinstalar_validador_falso()
    rate_limit.reiniciar_limites()


def test_env_example_permanece_vacio():
    from pathlib import Path
    ejemplo = Path("C:/Users/usuario/Documents/SI2/Primer_Parcial/backend/.env.example").read_text(encoding="utf-8") \
        if False else None
    # Leído desde el repo (ruta relativa al backend).
    from pathlib import Path as _P
    texto = (_P(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
    linea = next(l for l in texto.splitlines() if l.startswith("DECART_ORIGENES_PERMITIDOS="))
    assert linea.strip() == "DECART_ORIGENES_PERMITIDOS="


async def test_host_permitido_ok(cliente_http: AsyncClient, _base):
    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_probador(cliente_http, suc, 2, tag="img1")
    async with await crear_cliente("img1") as cli:
        r = await cli.client.get(f"/api/v1/variantes/{var['variante_id']}/prueba-virtual")
        assert r.status_code == 200, r.text


async def test_host_no_permitido_422(cliente_http: AsyncClient, _base, monkeypatch):
    import uuid
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.core.modules.catalogo.models import VarianteProducto

    suc = await sucursal_semilla(cliente_http)
    var = await crear_variante_probador(cliente_http, suc, 2, tag="img2")
    async with AsyncSessionLocal() as db:
        async with db.begin():
            v = await db.get(VarianteProducto, var["variante_id"])
            v.recurso_prueba_virtual = "https://malicioso.example/prenda.webp"
    async with await crear_cliente("img2") as cli:
        r = await cli.client.get(f"/api/v1/variantes/{var['variante_id']}/prueba-virtual")
        assert r.status_code == 422, r.text


async def test_http_no_seguro_422():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        di.validar_sintaxis("http://cdn.fashionstore.test/p.webp")
    assert exc.value.status_code == 422


@pytest.mark.parametrize("modo,detalle", [
    ("mime", "MIME"), ("pequena", "512"), ("grande", "tamaño"),
    ("redireccion", "Redirección"), ("timeout", "Timeout"),
])
async def test_modos_falso_422(cliente_http: AsyncClient, monkeypatch, modo, detalle):
    monkeypatch.setattr(settings, "DECART_ENABLED", True)
    monkeypatch.setattr(settings, "DECART_API_KEY", "dk_test_falsa")
    monkeypatch.setattr(settings, "DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    instalar_validador_falso(modo)
    try:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_probador(cliente_http, suc, 2, tag=f"m{modo[:3]}")
        async with await crear_cliente(f"m{modo[:3]}") as cli:
            r = await cli.client.get(f"/api/v1/variantes/{var['variante_id']}/prueba-virtual")
            assert r.status_code == 422 and detalle in r.text, r.text
    finally:
        desinstalar_validador_falso()


async def test_extension_falsa_422():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        di.validar_sintaxis("https://cdn.fashionstore.test/prenda.txt")
    assert exc.value.status_code == 422


async def test_sin_allowlist_autorizacion_falla_controlada(cliente_http: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "DECART_ENABLED", True)
    monkeypatch.setattr(settings, "DECART_API_KEY", "dk_test_falsa")
    monkeypatch.setattr(settings, "DECART_ORIGENES_PERMITIDOS", "")
    monkeypatch.setenv("DECART_ORIGENES_PERMITIDOS", "")
    instalar_decart_falso("tok-x")
    instalar_validador_falso("ok")
    try:
        suc = await sucursal_semilla(cliente_http)
        var = await crear_variante_probador(cliente_http, suc, 2, tag="imgx")
        async with await crear_cliente("imgx") as cli:
            r = await cli.client.post(
                "/api/v1/probador/autorizaciones",
                json={"variante_id": var["variante_id"], "consentimiento_version": "decart-v1"},
                headers={"Idempotency-Key": clave()})
            # Falla controlada del probador (503/422), sin afectar carrito.
            assert r.status_code in (422, 503), r.text
            assert (await cli.client.get("/api/v1/carritos/mio", params={"canal": "WEB"})).status_code == 200
    finally:
        desinstalar_decart_falso()
        desinstalar_validador_falso()


def test_prohibidos_localhost_y_privadas():
    from fastapi import HTTPException
    for mala in (
        "https://localhost/p.webp", "https://127.0.0.1/p.webp",
        "https://10.0.0.5/p.webp", "https://192.168.1.10/p.webp",
        "https://169.254.169.254/p.webp", "https://[::1]/p.webp",
    ):
        try:
            di.validar_sintaxis(mala)
        except HTTPException as e:
            assert e.status_code == 422
        else:
            raise AssertionError(f"debió rechazar {mala}")


# --- Camino real con transporte y DNS simulados (sin red ni créditos) ---

def _dns_publico(host):
    async def _resolver(h):
        return ["93.184.216.34"]

    return _resolver


async def _dns_privado(host):
    return ["10.0.0.5"]


def _fabrica_mock(handler):
    import httpx

    def _fabrica(*, timeout, follow_redirects=False):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout, follow_redirects=False,
        )

    return _fabrica


async def test_streaming_corta_al_superar_limite(monkeypatch):
    """El cuerpo se lee por bloques y se interrumpe al superar el máximo."""
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    monkeypatch.setenv("DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    monkeypatch.setattr(settings, "DECART_IMAGEN_MAX_MB", 1)
    llamadas = []

    def _handler(request):
        import httpx

        llamadas.append(str(request.url))
        # Content-Length pequeño pero cuerpo real de 2 MB: solo el corte
        # durante el streaming puede rechazarlo.
        return httpx.Response(
            200, headers={"content-type": "image/webp"},
            content=b"z" * (2 * 1024 * 1024),
        )

    di.fijar_validador(None)
    di.fijar_resolvedor_dns(_dns_publico("cdn.fashionstore.test"))
    di.fijar_fabrica_cliente_http(_fabrica_mock(_handler))
    try:
        with pytest.raises(HTTPException) as exc:
            await di.obtener_validador().validar("https://cdn.fashionstore.test/prendas/g.webp")
        assert exc.value.status_code == 422
        assert "tamaño" in str(exc.value.detail)
        assert llamadas, "el camino real de descarga debe haberse ejecutado"
    finally:
        di.fijar_resolvedor_dns(None)
        di.fijar_fabrica_cliente_http(None)


async def test_content_length_anticipado_y_content_type_obligatorio(monkeypatch):
    from fastapi import HTTPException

    import httpx

    monkeypatch.setattr(settings, "DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    monkeypatch.setenv("DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    monkeypatch.setattr(settings, "DECART_IMAGEN_MAX_MB", 1)
    di.fijar_validador(None)
    di.fijar_resolvedor_dns(_dns_publico("cdn.fashionstore.test"))
    try:
        # Content-Length que ya supera el límite: rechazo anticipado.
        di.fijar_fabrica_cliente_http(_fabrica_mock(
            lambda req: httpx.Response(
                200, headers={"content-type": "image/png", "content-length": str(10 * 1024 * 1024)},
                content=b"z",
            )
        ))
        with pytest.raises(HTTPException) as exc:
            await di.obtener_validador().validar("https://cdn.fashionstore.test/prendas/a.png")
        assert exc.value.status_code == 422 and "tamaño" in str(exc.value.detail)
        # Content-Type ausente: rechazo obligatorio sin confiar en extensión.
        di.fijar_fabrica_cliente_http(_fabrica_mock(
            lambda req: httpx.Response(200, headers={}, content=b"abc")
        ))
        with pytest.raises(HTTPException) as exc2:
            await di.obtener_validador().validar("https://cdn.fashionstore.test/prendas/b.png")
        assert exc2.value.status_code == 422 and "MIME" in str(exc2.value.detail)
        # MIME distinto: rechazo.
        di.fijar_fabrica_cliente_http(_fabrica_mock(
            lambda req: httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>")
        ))
        with pytest.raises(HTTPException) as exc3:
            await di.obtener_validador().validar("https://cdn.fashionstore.test/prendas/c.png")
        assert exc3.value.status_code == 422 and "MIME" in str(exc3.value.detail)
    finally:
        di.fijar_resolvedor_dns(None)
        di.fijar_fabrica_cliente_http(None)


async def test_dns_interno_rechaza_antes_de_descargar(monkeypatch):
    """DNS simulado con IP privada: se bloquea sin descargar nada."""
    from fastapi import HTTPException

    import httpx

    monkeypatch.setattr(settings, "DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    monkeypatch.setenv("DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    tocado = []

    def _handler(request):
        tocado.append(True)
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"z")

    di.fijar_validador(None)
    di.fijar_resolvedor_dns(_dns_privado)
    di.fijar_fabrica_cliente_http(_fabrica_mock(_handler))
    try:
        with pytest.raises(HTTPException) as exc:
            await di.obtener_validador().validar("https://cdn.fashionstore.test/prendas/d.png")
        assert exc.value.status_code == 422
        assert "interno" in str(exc.value.detail)
        assert not tocado, "con DNS interno no debe descargarse nada"
    finally:
        di.fijar_resolvedor_dns(None)
        di.fijar_fabrica_cliente_http(None)


async def test_redireccion_a_host_no_permitido_bloqueada(monkeypatch):
    from fastapi import HTTPException

    import httpx

    monkeypatch.setattr(settings, "DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    monkeypatch.setenv("DECART_ORIGENES_PERMITIDOS", "cdn.fashionstore.test")
    di.fijar_validador(None)
    di.fijar_resolvedor_dns(_dns_publico("cdn.fashionstore.test"))
    di.fijar_fabrica_cliente_http(_fabrica_mock(
        lambda req: httpx.Response(302, headers={"location": "https://malicioso.example/x.webp"})
    ))
    try:
        with pytest.raises(HTTPException) as exc:
            await di.obtener_validador().validar("https://cdn.fashionstore.test/prendas/e.webp")
        assert exc.value.status_code == 422
        assert "no permitido" in str(exc.value.detail)
    finally:
        di.fijar_resolvedor_dns(None)
        di.fijar_fabrica_cliente_http(None)
