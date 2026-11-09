"""Create a repeatable local multitenant demo in fashionstore_manual_test.

This script reads the local PostgreSQL connection from backend/.env or the
process environment, creates a separate *_test database through the existing
test preparer, then seeds only fictional data. It never reads business rows
from fashionstore_db and refuses a non-loopback PostgreSQL host.

Run from any directory with the backend virtual environment:
    backend/venv/Scripts/python.exe backend/scripts/preparar_demo_tenants.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from dotenv import dotenv_values

BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_ROOT.parent
DB_NAME = "fashionstore_manual_test"
DEMO_SUFFIX = "@example.com"

if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


def _local_test_url() -> str:
    saved = dotenv_values(BACKEND_ROOT / ".env")

    def setting(key: str, default: str = "") -> str:
        return os.environ.get(key) or str(saved.get(key) or default)

    configured = setting("DATABASE_URL")
    if configured:
        parsed = urlsplit(configured)
        if parsed.scheme not in {"postgres", "postgresql", "postgresql+asyncpg"}:
            raise RuntimeError("DATABASE_URL debe ser una URL PostgreSQL")
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("La demo solo acepta PostgreSQL local")
        if not parsed.username or not parsed.password:
            raise RuntimeError("La URL PostgreSQL local requiere usuario y clave")
        return urlunsplit(("postgresql+asyncpg", parsed.netloc, f"/{DB_NAME}", "", ""))

    host = setting("POSTGRES_SERVER", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("La demo solo acepta PostgreSQL local")
    user = quote(setting("POSTGRES_USER", "postgres"), safe="")
    password = quote(setting("POSTGRES_PASSWORD", "postgres"), safe="")
    port = setting("POSTGRES_PORT", "5432")
    host_part = f"[{host}]" if host == "::1" else host
    return f"postgresql+asyncpg://{user}:{password}@{host_part}:{port}/{DB_NAME}"


def _prepare_database(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.path != f"/{DB_NAME}" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Destino de demostracion no autorizado")
    child_env = os.environ.copy()
    child_env.update(
        {
            "DATABASE_URL": url,
            "POSTGRES_DB": DB_NAME,
            "TEST_ADMIN_EMAIL": "admin@fashionstore.com",
            "TEST_ADMIN_PASSWORD": "Fashion123!",
        }
    )
    async def exists() -> bool:
        import asyncpg

        con = await asyncpg.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database="postgres",
        )
        try:
            return bool(await con.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", DB_NAME))
        finally:
            await con.close()

    if asyncio.run(exists()):
        print(f"Base local aislada existente: {DB_NAME}; se conserva el esquema", flush=True)
    else:
        print(f"Preparando base local aislada nueva: {DB_NAME}", flush=True)
        subprocess.run(
            [sys.executable, str(BACKEND_ROOT / "tests" / "preparar_base_pruebas.py")],
            cwd=BACKEND_ROOT,
            env=child_env,
            check=True,
        )
    os.environ.update(child_env)


async def _seed() -> None:
    from sqlalchemy import func, select, text

    from backend.app.core.database import AsyncSessionLocal, engine
    from backend.app.core.modules.catalogo.models import (
        Categoria,
        Color,
        Producto,
        Proveedor,
        Talla,
        VarianteProducto,
    )
    from backend.app.core.modules.identidad_empresas.models import (
        Cliente,
        Empleado,
        Empresa,
        Plan,
        Rol,
        Suscripcion,
        Usuario,
    )
    from backend.app.core.modules.inventario.models import LoteRecepcion
    from backend.app.core.modules.inventario.schemas import LoteRecepcionCrearDTO
    from backend.app.core.modules.inventario.services.recepcion_service import RecepcionService
    from backend.app.core.modules.organizacion.models import Ciudad, Sucursal
    from backend.app.core.reloj import utcnow
    from backend.app.core.seguridad import generar_contrasenia_hash, verificar_contrasenia

    async def role(db, name: str) -> Rol:
        value = (await db.execute(select(Rol).where(Rol.nombre == name))).scalar_one_or_none()
        if value is None:
            value = Rol(nombre=name, descripcion=f"Rol de demostracion {name}", activo=True)
            db.add(value)
            await db.flush()
        return value

    async def company(db, code: str, name: str, state: str) -> Empresa:
        value = (await db.execute(select(Empresa).where(Empresa.codigo == code))).scalar_one_or_none()
        if value is None:
            value = Empresa(
                codigo=code,
                nombre=name,
                nombre_comercial=name,
                razon_social=f"{name} SRL",
                estado=state,
            )
            db.add(value)
            await db.flush()
        elif value.estado != state:
            raise RuntimeError(f"La empresa {code} existe con estado {value.estado}; no se modifica")
        return value

    async def user(db, company_id, role_id, email: str, password: str, first: str, last: str) -> Usuario:
        q = select(Usuario).where(func.lower(Usuario.correo_electronico) == email.lower())
        q = q.where(Usuario.empresa_id.is_(None)) if company_id is None else q.where(Usuario.empresa_id == company_id)
        value = (await db.execute(q)).scalar_one_or_none()
        if value is None:
            value = Usuario(
                empresa_id=company_id,
                rol_id=role_id,
                nombres=first,
                apellidos=last,
                correo_electronico=email,
                contrasenia_hash=generar_contrasenia_hash(password),
                estado="ACTIVO",
                revision=1,
            )
            db.add(value)
            await db.flush()
        elif value.rol_id != role_id or value.estado != "ACTIVO" or not verificar_contrasenia(password, value.contrasenia_hash):
            raise RuntimeError(f"La cuenta {email} de esta empresa no coincide con la semilla; se conserva")
        return value

    async def branch(db, company_id, city_id, name: str, ring: int) -> Sucursal:
        value = (await db.execute(
            select(Sucursal).where(Sucursal.empresa_id == company_id, Sucursal.nombre == name)
        )).scalar_one_or_none()
        if value is None:
            value = Sucursal(
                empresa_id=company_id,
                ciudad_id=city_id,
                nombre=name,
                direccion=f"Av. Demo {ring}00, Santa Cruz de la Sierra",
                numero_anillo=ring,
                tarifa_base_delivery=Decimal("12.00"),
                incremento_anillo_delivery=Decimal("3.00"),
                anillo_minimo_delivery=1,
                anillo_maximo_delivery=8,
                delivery_activo=True,
                activa=True,
                adelanto_activo=False,
                valor_adelanto=Decimal("0.00"),
            )
            db.add(value)
            await db.flush()
        return value

    async def subscription(db, company_id, plan_id, superadmin_id) -> None:
        existing = (await db.execute(
            select(Suscripcion).where(Suscripcion.empresa_id == company_id).order_by(Suscripcion.version.desc()).limit(1)
        )).scalar_one_or_none()
        if existing is not None:
            if not (existing.inicia_en <= utcnow() < existing.vence_en):
                raise RuntimeError("La suscripcion demo existe pero no esta vigente; renovarla por la API")
            return
        now = utcnow()
        db.add(Suscripcion(
            empresa_id=company_id,
            plan_id=plan_id,
            version=1,
            inicia_en=now - timedelta(days=1),
            vence_en=now + timedelta(days=180),
            creada_por=superadmin_id,
            motivo="SEMILLA_DEMO_LOCAL_SIN_COBRO_STRIPE",
        ))
        await db.flush()

    async def catalog_item(db, company_id, label: str, price: str, supplier_name: str):
        async def find_or_create(model, clauses, **values):
            existing = (await db.execute(select(model).where(*clauses))).scalar_one_or_none()
            if existing is not None:
                return existing
            new = model(**values)
            db.add(new)
            await db.flush()
            return new

        category = await find_or_create(
            Categoria,
            [Categoria.empresa_id == company_id, Categoria.nombre == "Camisetas Demo"],
            empresa_id=company_id, nombre="Camisetas Demo", activo=True,
        )
        size_m = await find_or_create(
            Talla, [Talla.empresa_id == company_id, Talla.nombre == "M"],
            empresa_id=company_id, nombre="M", orden=3, activo=True,
        )
        size_l = await find_or_create(
            Talla, [Talla.empresa_id == company_id, Talla.nombre == "L"],
            empresa_id=company_id, nombre="L", orden=4, activo=True,
        )
        black = await find_or_create(
            Color, [Color.empresa_id == company_id, Color.nombre == "Negro"],
            empresa_id=company_id, nombre="Negro", codigo_hex="#000000", activo=True,
        )
        blue = await find_or_create(
            Color, [Color.empresa_id == company_id, Color.nombre == "Azul Demo"],
            empresa_id=company_id, nombre="Azul Demo", codigo_hex="#1E40AF", activo=True,
        )
        supplier = await find_or_create(
            Proveedor, [Proveedor.empresa_id == company_id, Proveedor.nit == "DEMO-NIT-001"],
            empresa_id=company_id, razon_social=supplier_name, nit="DEMO-NIT-001", activo=True,
        )
        product = await find_or_create(
            Producto, [Producto.empresa_id == company_id, Producto.nombre == label],
            empresa_id=company_id, categoria_id=category.id, proveedor_principal_id=supplier.id,
            nombre=label, descripcion="Prenda ficticia para pruebas locales de multitenencia.",
            genero="UNISEX", marca="Demo", precio_base=Decimal(price), activo=True,
        )
        variant_m = await find_or_create(
            VarianteProducto,
            [VarianteProducto.empresa_id == company_id, VarianteProducto.sku == "DEMO-CAMISETA-M-NEGRO"],
            empresa_id=company_id, producto_id=product.id, talla_id=size_m.id, color_id=black.id,
            sku="DEMO-CAMISETA-M-NEGRO", precio=Decimal(price), activa=True,
        )
        variant_l = await find_or_create(
            VarianteProducto,
            [VarianteProducto.empresa_id == company_id, VarianteProducto.sku == "DEMO-CAMISETA-L-AZUL"],
            empresa_id=company_id, producto_id=product.id, talla_id=size_l.id, color_id=blue.id,
            sku="DEMO-CAMISETA-L-AZUL", precio=Decimal(price) + Decimal("10.00"), activa=True,
        )
        if variant_m.producto_id != product.id or variant_l.producto_id != product.id:
            raise RuntimeError("SKU demo ya existe en otra prenda de la misma empresa")
        return supplier.id, variant_m.id, variant_l.id

    receipts = []
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                current = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
                if current != "0014_pago_ref_externa_unique":
                    raise RuntimeError(f"La base de demostracion debe estar en revision 0014; actual: {current}")

                role_super = await role(db, "SUPERADMIN")
                role_admin = await role(db, "ADMINISTRADOR")
                role_client = await role(db, "CLIENTE")
                role_cashier = await role(db, "CAJERO")

                plans = {p.codigo: p for p in (await db.execute(select(Plan))).scalars().all()}
                if not {"BASICO", "PROFESIONAL"}.issubset(plans):
                    raise RuntimeError("Faltan los planes BASICO/PROFESIONAL de la migracion")

                city = (await db.execute(select(Ciudad).where(Ciudad.nombre == "Santa Cruz de la Sierra"))).scalar_one_or_none()
                if city is None:
                    city = Ciudad(nombre="Santa Cruz de la Sierra", activo=True)
                    db.add(city)
                    await db.flush()

                platform = await user(
                    db, None, role_super.id, "superadmin.demo@example.com", "SuperDemo2026!", "Super", "Demo",
                )

                specs = [
                    ("fashionstore", "FashionStore", "ACTIVA", "PROFESIONAL", "Sucursal Pruebas", 1,
                     "Camiseta FashionStore Demo", "120.00", "65.00", 6, 2),
                    ("demo-andes", "Boutique Andes Demo", "ACTIVA", "PROFESIONAL", "Centro Andes", 2,
                     "Camiseta Andes Demo", "135.00", "70.00", 8, 1),
                    ("demo-oriente", "Boutique Oriente Demo", "ACTIVA", "BASICO", "Centro Oriente", 3,
                     "Camiseta Oriente Demo", "150.00", "80.00", 5, 2),
                    ("demo-pendiente", "Boutique Pendiente Demo", "PENDIENTE_PLAN", None, None, None,
                     None, None, None, 0, 0),
                ]

                for code, name, state, plan_code, branch_name, ring, product_name, price, cost, qty_m, qty_l in specs:
                    tenant = await company(db, code, name, state)
                    if plan_code:
                        await subscription(db, tenant.id, plans[plan_code].id, platform.id)

                    admin_email = f"admin.{code.replace('demo-', '')}{DEMO_SUFFIX}" if code != "fashionstore" else "admin@fashionstore.com"
                    admin_password = {
                        "fashionstore": "Fashion123!",
                        "demo-andes": "AndesDemo2026!",
                        "demo-oriente": "OrienteDemo2026!",
                        "demo-pendiente": "Pendiente2026!",
                    }[code]
                    admin = await user(db, tenant.id, role_admin.id, admin_email, admin_password, "Admin", code)

                    if branch_name is None:
                        continue
                    store = await branch(db, tenant.id, city.id, branch_name, ring)
                    if (await db.get(Empleado, admin.id)) is None:
                        db.add(Empleado(usuario_id=admin.id, sucursal_id=store.id, cargo="Administrador demo", activo=True))
                    if code in {"demo-andes", "demo-oriente"}:
                        cashier = await user(
                            db, tenant.id, role_cashier.id, f"cajero.{code.replace('demo-', '')}{DEMO_SUFFIX}",
                            f"Caja{code.replace('demo-', '').title()}2026!", "Cajero", code,
                        )
                        if (await db.get(Empleado, cashier.id)) is None:
                            db.add(Empleado(usuario_id=cashier.id, sucursal_id=store.id, cargo="Cajero demo", activo=True))
                        for email, password in (
                            (f"cliente.{code.replace('demo-', '')}{DEMO_SUFFIX}", f"Cliente{code.replace('demo-', '').title()}2026!"),
                            ("cliente.compartido@example.com", "ClienteDemo2026!"),
                        ):
                            customer = await user(db, tenant.id, role_client.id, email, password, "Cliente", code)
                            if (await db.get(Cliente, customer.id)) is None:
                                db.add(Cliente(usuario_id=customer.id, direccion_referencia=f"Zona {code}", preferencias={}))

                    supplier_id, variant_m_id, variant_l_id = await catalog_item(
                        db, tenant.id, product_name, price, f"Proveedor {name}",
                    )
                    receipts.append((code, tenant.id, store.id, supplier_id, admin.id,
                                     variant_m_id, variant_l_id, cost, qty_m, qty_l))

                    if code == "demo-andes":
                        second = await branch(db, tenant.id, city.id, "Norte Andes", 4)
                        receipts.append((code + "-norte", tenant.id, second.id, supplier_id, admin.id,
                                         variant_m_id, variant_l_id, cost, 3, 0))

        for code, tenant_id, store_id, supplier_id, admin_id, variant_m_id, variant_l_id, cost, qty_m, qty_l in receipts:
            document = f"DEMO-RECEPCION-{code.upper()}"
            async with AsyncSessionLocal() as db:
                existing = (await db.execute(select(LoteRecepcion).where(
                    LoteRecepcion.empresa_id == tenant_id,
                    LoteRecepcion.sucursal_id == store_id,
                    LoteRecepcion.numero_documento == document,
                ))).scalar_one_or_none()
                if existing is not None:
                    continue
                details = [{"variante_id": variant_m_id, "cantidad": qty_m, "costo_unitario": Decimal(cost)}]
                if qty_l > 0:
                    details.append({"variante_id": variant_l_id, "cantidad": qty_l, "costo_unitario": Decimal(cost) + Decimal("5.00")})
                dto = LoteRecepcionCrearDTO(
                    proveedor_id=supplier_id,
                    sucursal_id=store_id,
                    recibido_por_id=admin_id,
                    numero_documento=document,
                    observacion="Recepcion ficticia de semilla local; conserva inventario y Kardex",
                    detalles=details,
                )
                await RecepcionService(db).registrarLote(dto)

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(Empresa.codigo, Empresa.estado).where(
                Empresa.codigo.in_(["fashionstore", "demo-andes", "demo-oriente", "demo-pendiente"])
            ).order_by(Empresa.codigo))).all()
            print("Empresas demo: " + ", ".join(f"{code} ({state})" for code, state in rows))
            print("Lotes demo: " + str((await db.execute(select(func.count(LoteRecepcion.id)).where(
                LoteRecepcion.numero_documento.like("DEMO-RECEPCION-%")
            ))).scalar_one()))
            print("La semilla de planes es ficticia y no representa un pago Stripe.")
    finally:
        await engine.dispose()


def main() -> None:
    target = _local_test_url()
    _prepare_database(target)
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
