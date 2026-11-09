"""Fixtures compartidas del backend (Ciclos 1 y 2).

Protección Ciclo 2: las pruebas crean usuarios, sucursales, productos,
reservas y ventas, por lo que son destructivas. Solo pueden ejecutarse
contra una base cuyo nombre termine en ``_test`` (p. ej.
``fashionstore_test``). Ver ``BASE_DE_PRUEBAS.md`` para crearla.

Mecanismo real: los alias ``TEST_*`` se copian a las variables que la
aplicación consume (``DATABASE_URL`` / ``POSTGRES_*``) ANTES de importar
cualquier módulo que inicialice configuración, engine, sesiones o la app
FastAPI. La validación inspecciona la URL efectiva que usará SQLAlchemy
(``settings.async_database_url``), no el valor de una variable auxiliar.
"""
import os
from typing import AsyncGenerator
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Mapeo explícito TEST_* -> variables reales ANTES de importar configuración.
# La aplicación solo consume DATABASE_URL o POSTGRES_* (ver
# backend/app/core/config.py y backend/app/core/database.py). Sin este mapeo
# previo, el guard podría ver "fashionstore_test" en una variable auxiliar
# mientras FastAPI seguía conectado a "fashionstore_db". Para no mantener dos
# fuentes de verdad, los alias se aplican una sola vez aquí y todo lo demás
# lee la configuración efectiva.
# ---------------------------------------------------------------------------
if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "")
if os.getenv("TEST_POSTGRES_DB"):
    os.environ["POSTGRES_DB"] = os.getenv("TEST_POSTGRES_DB", "")
if os.getenv("TEST_POSTGRES_SERVER"):
    os.environ["POSTGRES_SERVER"] = os.getenv("TEST_POSTGRES_SERVER", "")
if os.getenv("TEST_POSTGRES_PORT"):
    os.environ["POSTGRES_PORT"] = os.getenv("TEST_POSTGRES_PORT", "")
if os.getenv("TEST_POSTGRES_USER"):
    os.environ["POSTGRES_USER"] = os.getenv("TEST_POSTGRES_USER", "")
if os.getenv("TEST_POSTGRES_PASSWORD"):
    os.environ["POSTGRES_PASSWORD"] = os.getenv("TEST_POSTGRES_PASSWORD", "")

import pytest  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402

import app  # noqa: E402,F401  Inicializa alias de módulo para ejecuciones aisladas
from backend.app.core.config import settings  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _ia_determinista_en_pruebas(monkeypatch):
    """Evita que una clave Gemini del entorno active llamadas externas en la suite."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")


def _nombre_base_desde_url(url: str) -> str:
    """Extrae el nombre de la base desde una URL SQLAlchemy.

    Funciona tanto con ``DATABASE_URL`` (p. ej.
    ``postgresql://.../fashionstore_test?ssl=require``) como con la URL
    compuesta desde ``POSTGRES_*``. Nunca incluye credenciales.
    """
    sin_query = (url or "").split("?")[0].rstrip("/")
    try:
        ruta = urlsplit(sin_query).path.rstrip("/").rsplit("/", 1)[-1]
        if ruta:
            return ruta
    except Exception:
        pass
    return sin_query.rsplit("/", 1)[-1]


def nombre_base_efectiva() -> str:
    """Nombre de la base a la que REALMENTE se conectará SQLAlchemy.

    Lee ``settings.async_database_url``, que ya resolvió la prioridad real
    de la aplicación (``DATABASE_URL`` si existe, si no composición
    ``POSTGRES_*``). Es la única evidencia válida para permitir la suite.
    """
    return _nombre_base_desde_url(settings.async_database_url)


def es_base_de_pruebas(nombre: str) -> bool:
    nombre = (nombre or "").strip()
    return nombre.endswith("_test") and nombre != "fashionstore_manual_test"


@pytest.fixture(scope="session", autouse=True)
def _proteger_base_productiva():
    """Rechaza la suite si la URL EFECTIVA no apunta a una base de pruebas.

    Inspecciona ``settings.async_database_url`` (la misma que usa el engine
    de SQLAlchemy) y aborta antes de crear, eliminar o modificar datos si la
    base efectiva no termina en ``_test``. Evita truncar o contaminar
    ``fashionstore_db``: las pruebas del Ciclo 2 crean usuarios, sucursales,
    productos, reservas y ventas.
    """
    nombre = nombre_base_efectiva()
    if not es_base_de_pruebas(nombre):
        pytest.fail(
            "Protección Ciclo 2: la suite crea datos destructivos y la base "
            f"EFECTIVA es '{nombre}' (URL real de SQLAlchemy). "
            "fashionstore_manual_test contiene la demo interactiva y no puede limpiarse. Configure una "
            "base separada cuyo nombre termine en '_test' (ver "
            "tests/BASE_DE_PRUEBAS.md) con POSTGRES_DB=fashionstore_test o "
            "DATABASE_URL=.../fashionstore_test (alias TEST_DATABASE_URL / "
            "TEST_POSTGRES_DB se copian a las reales antes del import). "
            "Nunca ejecute pytest contra fashionstore_db.",
            pytrace=False,
        )


@pytest.fixture(scope="session", autouse=True)
def _base_determinista(_proteger_base_productiva):
    """Limpieza determinista una vez por suite (solo base ``*_test``).

    Trunca los datos de negocio de ejecuciones anteriores y recarga la
    semilla mínima antes del primer test, para que paginación, búsquedas y
    conteos (CU05/CU06) sean deterministas. Depende de
    ``_proteger_base_productiva`` para garantizar el orden: primero se
    rechaza cualquier base que no termine en ``_test``.
    """
    import asyncio

    from tests.limpieza_base import limpiar_datos_negocio

    asyncio.run(limpiar_datos_negocio())
    yield


@pytest.fixture
async def cliente_http() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # auto-login como admin para tests que requieren RBAC
        try:
            resp = await client.post(
                "/api/v1/sesion",
                json={
                    "correo_electronico": os.getenv(
                        "TEST_ADMIN_EMAIL", "admin@fashionstore.com"
                    ),
                    "contrasenia": os.getenv(
                        "TEST_ADMIN_PASSWORD", "Fashion123!"
                    ),
                },
            )
            if resp.status_code == 200:
                token = resp.json().get("access_token")
                if token:
                    client.headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass
        yield client
