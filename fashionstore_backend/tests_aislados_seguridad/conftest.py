"""Suite autónoma: ORM/SQL reales en SQLite :memory:, sin engine PostgreSQL.

Requiere FASHIONSTORE_SQLITE_SECURITY_TESTS=1 y ejecutarse por separado.
No importa database.py, no inicia lifespan y prohíbe conexiones de red.
No valida DDL, concurrencia ni funciones específicas de PostgreSQL.
"""
import os
import inspect
import socket
import sys
import types
from pathlib import Path

import pytest

if os.environ.get("FASHIONSTORE_SQLITE_SECURITY_TESTS") != "1":
    pytest.skip("Suite SQLite autónoma; requiere activación explícita", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as paquete_app  # inicializa el alias backend

if "backend.app.core.database" in sys.modules:
    raise RuntimeError("Ejecute esta suite en un proceso independiente")


def prohibir_red(*args, **kwargs):
    raise AssertionError("La suite de seguridad no permite conexiones externas")


_connect_original = socket.socket.connect
_codigo_socketpair = socket.socketpair.__code__


def conectar_solo_socketpair(self, direccion):
    # asyncio en Windows necesita su par de sockets local de señalización.
    # Solo la función estándar socketpair puede realizar esa conexión.
    if inspect.currentframe().f_back.f_code is _codigo_socketpair:
        return _connect_original(self, direccion)
    return prohibir_red()


socket.socket.connect = conectar_solo_socketpair
socket.socket.connect_ex = prohibir_red
os.environ.update(STRIPE_ENABLED="false", DECART_ENABLED="false", GEMINI_API_KEY="",
                  EXPIRACION_JOB_ACTIVO="false")

from sqlalchemy import Column, MetaData, Table, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def jsonb_sqlite(tipo, compiler, **kw):
    return "JSON"


database = types.ModuleType("backend.app.core.database")
database.Base = declarative_base()


async def db_no_configurada():
    raise AssertionError("Falta override de la BD aislada; no hay conexión de respaldo")
    yield


database.get_db = db_no_configurada
database.AsyncSessionLocal = prohibir_red
sys.modules[database.__name__] = database

from backend.app.main import app
from backend.app.core.dependencias import get_usuario_actual


class SesionAislada:
    """Adapta la sesión síncrona SQLite a la interfaz async de los servicios."""
    def __init__(self, session):
        self.session = session

    async def execute(self, *args, **kwargs):
        return self.session.execute(*args, **kwargs)

    async def get(self, *args, **kwargs):
        return self.session.get(*args, **kwargs)

    async def scalar(self, *args, **kwargs):
        return self.session.scalar(*args, **kwargs)

    def add(self, obj):
        self.session.add(obj)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def refresh(self, obj):
        self.session.refresh(obj)


@pytest.fixture
def entorno():
    # Todos los esquemas son bases SQLite adjuntas EN MEMORIA. Se crean tablas
    # de columnas ORM, sin reproducir constraints/índices PostgreSQL.
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    sentencias = []
    with engine.begin() as conn:
        for schema in ("organizacion", "seguridad", "comercial", "catalogo", "inventario", "inteligencia", "plataforma"):
            conn.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS {schema}")
        metadata = MetaData()
        for original in database.Base.metadata.tables.values():
            columnas = [Column(c.name, c.type, primary_key=c.primary_key,
                               nullable=c.nullable) for c in original.columns]
            Table(original.name, metadata, *columnas, schema=original.schema)
        metadata.create_all(conn)

    @event.listens_for(engine, "before_cursor_execute")
    def registrar(conn, cursor, statement, parameters, context, executemany):
        sentencias.append(statement)

    session = Session(engine, expire_on_commit=False)
    db = SesionAislada(session)
    estado = types.SimpleNamespace(db=db, session=session, sql=sentencias, usuario=None, app=app)

    async def db_override():
        yield db

    async def usuario_override():
        return estado.usuario

    app.dependency_overrides[database.get_db] = db_override
    app.dependency_overrides[get_usuario_actual] = usuario_override
    yield estado
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()
