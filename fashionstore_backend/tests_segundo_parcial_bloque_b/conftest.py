"""Configuración de la suite aislada del Bloque B (CU03/CU04/CU16/CU18).

Reglas de seguridad:
- Solo se ejecuta contra una base cuyo nombre termine en ``_test``.
- La URL se toma de ``FASHIONSTORE_TEST_DATABASE_URL`` (sin credenciales en Git).
- Los datos se crean con identificadores únicos y se confirman; no se borra
  información de una base compartida ni se ejecuta limpieza manual.
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

URL_PRUEBAS = os.getenv("FASHIONSTORE_TEST_DATABASE_URL", "")
if not URL_PRUEBAS:
    pytest.skip(
        "Defina FASHIONSTORE_TEST_DATABASE_URL apuntando a una base *_test",
        allow_module_level=True,
    )
if not urlsplit(URL_PRUEBAS).path.strip("/").endswith("_test"):
    raise RuntimeError("La suite solo puede ejecutarse contra una base *_test")

from backend.app.core.database import get_db  # noqa: E402
from backend.app.core.dependencias import get_usuario_actual  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.core.modules.catalogo.models import (  # noqa: E402
    Categoria,
    Color,
    Producto,
    Talla,
    VarianteProducto,
)
from backend.app.core.modules.identidad_empresas.models import (  # noqa: E402
    Cliente,
    Empresa,
    Plan,
    Rol,
    Suscripcion,
    Usuario,
)
from backend.app.core.modules.inventario.models import InventarioSucursal  # noqa: E402
from backend.app.core.modules.organizacion.models import Ciudad, Sucursal  # noqa: E402

T0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)


class RelojControlable:
    """Reloj determinista con avance explícito para C34, 24 h y 72 h."""

    def __init__(self, momento: datetime):
        self._momento = momento

    def fijar(self, momento: datetime) -> None:
        self._momento = momento

    def avanzar(self, delta: timedelta) -> datetime:
        self._momento = self._momento + delta
        return self._momento

    def ahora(self) -> datetime:
        return self._momento


@dataclass
class Escenario:
    empresa_a_id: uuid.UUID
    empresa_b_id: uuid.UUID
    codigo_a: str
    codigo_b: str
    sucursal_a_id: uuid.UUID
    sucursal_b_id: uuid.UUID
    categoria_a_id: uuid.UUID
    producto_a_id: uuid.UUID
    variante_a_id: uuid.UUID
    variante_ultima_id: uuid.UUID
    variante_sin_stock_id: uuid.UUID
    usuario_a: Usuario
    usuario_b: Usuario
    # El trigger de 0006 impide un ADMINISTRADOR sin empresa; el único usuario
    # global válido es SUPERADMIN. Sin empresa no debe ver datos de negocio.
    usuario_global_sin_empresa: Usuario
    usuario_admin_a: Usuario
    ids: dict = field(default_factory=dict)


@pytest_asyncio.fixture(scope="session")
async def motor():
    engine = create_async_engine(URL_PRUEBAS, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
def fabrica_sesiones(motor):
    return async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def escenario(fabrica_sesiones) -> Escenario:
    sufijo = uuid.uuid4().hex[:8]
    async with fabrica_sesiones() as db:
        rol_cliente = (
            await db.execute(select(Rol).where(Rol.nombre == "CLIENTE"))
        ).scalars().first()
        rol_admin = (
            await db.execute(select(Rol).where(Rol.nombre == "ADMINISTRADOR"))
        ).scalars().first()
        rol_super = (
            await db.execute(select(Rol).where(Rol.nombre == "SUPERADMIN"))
        ).scalars().first()
        plan = (
            await db.execute(select(Plan).where(Plan.codigo == "PROFESIONAL"))
        ).scalars().first()
        ciudad_id = (await db.execute(select(Ciudad.id))).scalars().first()
        assert all([rol_cliente, rol_admin, rol_super, plan, ciudad_id])

        empresa_a_id = uuid.uuid4()
        empresa_b_id = uuid.uuid4()
        codigo_a = f"test_a_{sufijo}"
        codigo_b = f"test_b_{sufijo}"
        db.add_all(
            [
                Empresa(
                    id=empresa_a_id,
                    codigo=codigo_a,
                    nombre=f"Empresa A {sufijo}",
                    estado="ACTIVA",
                    catalogo_version=1,
                    catalogo_actualizado_en=T0,
                    plazo_cambios_dias=15,
                    creada_en=T0,
                    actualizada_en=T0,
                ),
                Empresa(
                    id=empresa_b_id,
                    codigo=codigo_b,
                    nombre=f"Empresa B {sufijo}",
                    estado="ACTIVA",
                    catalogo_version=1,
                    catalogo_actualizado_en=T0,
                    plazo_cambios_dias=15,
                    creada_en=T0,
                    actualizada_en=T0,
                ),
            ]
        )
        await db.flush()

        superadmin = Usuario(
            id=uuid.uuid4(),
            empresa_id=None,
            rol_id=rol_super.id,
            rol=rol_super,
            nombres="Super",
            apellidos=f"Test {sufijo}",
            correo_electronico=f"super_{sufijo}@plataforma.test",
            contrasenia_hash="no-usar",
            estado="ACTIVO",
        )
        db.add(superadmin)
        await db.flush()
        for empresa_id in (empresa_a_id, empresa_b_id):
            db.add(
                Suscripcion(
                    id=uuid.uuid4(),
                    empresa_id=empresa_id,
                    plan_id=plan.id,
                    version=1,
                    inicia_en=T0 - timedelta(days=1),
                    vence_en=T0 + timedelta(days=365),
                    creada_en=T0,
                    creada_por=superadmin.id,
                    motivo="Escenario de pruebas Bloque B",
                )
            )

        sucursal_a_id = uuid.uuid4()
        sucursal_b_id = uuid.uuid4()
        db.add_all(
            [
                Sucursal(
                    id=sucursal_a_id,
                    empresa_id=empresa_a_id,
                    ciudad_id=ciudad_id,
                    nombre=f"Sucursal A {sufijo}",
                    direccion="Calle A 100",
                    activa=True,
                    adelanto_activo=True,
                    modalidad_adelanto="MONTO_FIJO",
                    valor_adelanto=Decimal("50.00"),
                ),
                Sucursal(
                    id=sucursal_b_id,
                    empresa_id=empresa_b_id,
                    ciudad_id=ciudad_id,
                    nombre=f"Sucursal B {sufijo}",
                    direccion="Calle B 200",
                    activa=True,
                    adelanto_activo=True,
                    modalidad_adelanto="MONTO_FIJO",
                    valor_adelanto=Decimal("50.00"),
                ),
            ]
        )
        await db.flush()

        usuario_a = Usuario(
            id=uuid.uuid4(),
            empresa_id=empresa_a_id,
            rol_id=rol_cliente.id,
            rol=rol_cliente,
            nombres="Cliente",
            apellidos=f"A {sufijo}",
            correo_electronico=f"cliente_a_{sufijo}@test.local",
            contrasenia_hash="no-usar",
            estado="ACTIVO",
        )
        usuario_b = Usuario(
            id=uuid.uuid4(),
            empresa_id=empresa_b_id,
            rol_id=rol_cliente.id,
            rol=rol_cliente,
            nombres="Cliente",
            apellidos=f"B {sufijo}",
            correo_electronico=f"cliente_b_{sufijo}@test.local",
            contrasenia_hash="no-usar",
            estado="ACTIVO",
        )
        usuario_sin_empresa = Usuario(
            id=uuid.uuid4(),
            empresa_id=None,
            rol_id=rol_super.id,
            rol=rol_super,
            nombres="Super",
            apellidos=f"Sin empresa {sufijo}",
            correo_electronico=f"admin_sin_empresa_{sufijo}@test.local",
            contrasenia_hash="no-usar",
            estado="ACTIVO",
        )
        usuario_admin_a = Usuario(
            id=uuid.uuid4(),
            empresa_id=empresa_a_id,
            rol_id=rol_admin.id,
            rol=rol_admin,
            nombres="Admin",
            apellidos=f"A {sufijo}",
            correo_electronico=f"admin_a_{sufijo}@test.local",
            contrasenia_hash="no-usar",
            estado="ACTIVO",
        )
        db.add_all([usuario_a, usuario_b, usuario_sin_empresa, usuario_admin_a])
        await db.flush()
        db.add_all(
            [
                Cliente(
                    usuario_id=usuario_a.id,
                    direccion_referencia="Zona A",
                ),
                Cliente(
                    usuario_id=usuario_b.id,
                    direccion_referencia="Zona B",
                ),
            ]
        )

        categoria_a_id = uuid.uuid4()
        talla_id = uuid.uuid4()
        color_id = uuid.uuid4()
        color_ultima_id = uuid.uuid4()
        color_sin_stock_id = uuid.uuid4()
        db.add_all(
            [
                Categoria(
                    id=categoria_a_id,
                    empresa_id=empresa_a_id,
                    nombre=f"Categoria {sufijo}",
                    activo=True,
                ),
                Talla(
                    id=talla_id,
                    empresa_id=empresa_a_id,
                    nombre="M",
                    orden=1,
                    activo=True,
                ),
                Color(
                    id=color_id,
                    empresa_id=empresa_a_id,
                    nombre="Negro",
                    codigo_hex="#000000",
                    activo=True,
                ),
                Color(
                    id=color_ultima_id,
                    empresa_id=empresa_a_id,
                    nombre="Blanco",
                    codigo_hex="#FFFFFF",
                    activo=True,
                ),
                Color(
                    id=color_sin_stock_id,
                    empresa_id=empresa_a_id,
                    nombre="Azul",
                    codigo_hex="#0000FF",
                    activo=True,
                ),
            ]
        )
        producto_a_id = uuid.uuid4()
        db.add(
            Producto(
                id=producto_a_id,
                empresa_id=empresa_a_id,
                categoria_id=categoria_a_id,
                nombre=f"Producto A {sufijo}",
                precio_base=Decimal("100.00"),
                activo=True,
            )
        )
        await db.flush()

        variante_a_id = uuid.uuid4()
        variante_ultima_id = uuid.uuid4()
        variante_sin_stock_id = uuid.uuid4()
        db.add_all(
            [
                VarianteProducto(
                    id=variante_a_id,
                    empresa_id=empresa_a_id,
                    producto_id=producto_a_id,
                    talla_id=talla_id,
                    color_id=color_id,
                    sku=f"SKU-A-{sufijo}",
                    precio=Decimal("100.00"),
                    costo_promedio=Decimal("40.00"),
                    costo_ultimo=Decimal("42.00"),
                    activa=True,
                ),
                VarianteProducto(
                    id=variante_ultima_id,
                    empresa_id=empresa_a_id,
                    producto_id=producto_a_id,
                    talla_id=talla_id,
                    color_id=color_ultima_id,
                    sku=f"SKU-ULTIMA-{sufijo}",
                    precio=Decimal("100.00"),
                    costo_promedio=Decimal("40.00"),
                    costo_ultimo=Decimal("42.00"),
                    activa=True,
                ),
                VarianteProducto(
                    id=variante_sin_stock_id,
                    empresa_id=empresa_a_id,
                    producto_id=producto_a_id,
                    talla_id=talla_id,
                    color_id=color_sin_stock_id,
                    sku=f"SKU-CERO-{sufijo}",
                    precio=Decimal("100.00"),
                    costo_promedio=Decimal("40.00"),
                    costo_ultimo=Decimal("42.00"),
                    activa=True,
                ),
            ]
        )
        await db.flush()
        db.add_all(
            [
                InventarioSucursal(
                    id=uuid.uuid4(),
                    sucursal_id=sucursal_a_id,
                    variante_id=variante_a_id,
                    disponible=5,
                    reservado=0,
                    comprometido_traslado=0,
                    en_transito=0,
                ),
                InventarioSucursal(
                    id=uuid.uuid4(),
                    sucursal_id=sucursal_a_id,
                    variante_id=variante_ultima_id,
                    disponible=1,
                    reservado=0,
                    comprometido_traslado=0,
                    en_transito=0,
                ),
                InventarioSucursal(
                    id=uuid.uuid4(),
                    sucursal_id=sucursal_a_id,
                    variante_id=variante_sin_stock_id,
                    disponible=0,
                    reservado=0,
                    comprometido_traslado=0,
                    en_transito=0,
                ),
            ]
        )
        await db.commit()

        return Escenario(
            empresa_a_id=empresa_a_id,
            empresa_b_id=empresa_b_id,
            codigo_a=codigo_a,
            codigo_b=codigo_b,
            sucursal_a_id=sucursal_a_id,
            sucursal_b_id=sucursal_b_id,
            categoria_a_id=categoria_a_id,
            producto_a_id=producto_a_id,
            variante_a_id=variante_a_id,
            variante_ultima_id=variante_ultima_id,
            variante_sin_stock_id=variante_sin_stock_id,
            usuario_a=usuario_a,
            usuario_b=usuario_b,
            usuario_global_sin_empresa=usuario_sin_empresa,
            usuario_admin_a=usuario_admin_a,
            ids={
                "ciudad": ciudad_id,
                "talla": talla_id,
                "color": color_id,
                "superadmin": superadmin.id,
            },
        )


@dataclass
class ClienteHttp:
    cliente: AsyncClient
    usuario_actual: dict

    def usar(self, usuario) -> None:
        self.usuario_actual["usuario"] = usuario


@pytest_asyncio.fixture
async def http(escenario, fabrica_sesiones):
    usuario_actual = {"usuario": escenario.usuario_a}

    async def _get_db():
        async with fabrica_sesiones() as sesion:
            try:
                yield sesion
            finally:
                await sesion.close()

    def _get_usuario():
        return usuario_actual["usuario"]

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_usuario_actual] = _get_usuario
    transporte = ASGITransport(app=app)
    async with AsyncClient(transport=transporte, base_url="http://pruebas") as cliente:
        yield ClienteHttp(cliente=cliente, usuario_actual=usuario_actual)
    app.dependency_overrides.clear()


def usuario_simple(usuario: Usuario):
    """Copia desacoplada con los atributos que consumen los servicios."""
    return SimpleNamespace(
        id=usuario.id,
        empresa_id=usuario.empresa_id,
        rol=SimpleNamespace(nombre=usuario.rol.nombre),
        empleado=None,
        cliente=None,
    )
