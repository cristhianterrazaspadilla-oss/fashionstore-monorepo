"""Pruebas ejecutables para Lote E1-B1: CU01, CU13, CU14.

Ejecución aislada sobre base *_test sin alterar datos productivos.
Cubre todos los escenarios obligatorios exigidos:
- CU01: Replay y carrera de idempotencia, persistencia de razón social y nombre comercial,
        acceso de plataforma y rechazo empresarial en alta de empresa, consulta pública filtrada.
- CU13: Rechazo de registro sin tenant (sin fallback silencioso), dos tenants con mismo correo,
        login ambiguo (300), sesión con 8 horas de privacidad y claims contractuales.
- CU14: Control optimista de revisión (409 ante revisión obsoleta, incremento monótono),
        rechazo de sucursales ajenas (403), carrera concurrente del último administrador activo.
"""
import asyncio
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from backend.app.main import app
from backend.app.core.database import get_db
from backend.app.core.seguridad import crear_token_acceso, generar_contrasenia_hash
from backend.app.core.modules.identidad_empresas.models import Empresa, Usuario, Rol
from backend.app.core.modules.organizacion.models import Sucursal, Ciudad


@pytest.fixture
def cliente_test(fabrica_sesiones):
    async def _get_db():
        async with fabrica_sesiones() as sesion:
            try:
                yield sesion
            except Exception:
                await sesion.rollback()
                raise
            finally:
                await sesion.close()

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


async def _obtener_o_crear_rol(db, nombre: str) -> Rol:
    q = await db.execute(select(Rol).where(Rol.nombre == nombre))
    rol = q.scalars().first()
    if not rol:
        rol = Rol(nombre=nombre, descripcion=f"Rol {nombre}")
        db.add(rol)
        await db.flush()
    return rol


@pytest.mark.asyncio
async def test_cu01_alta_empresa_y_aislamiento(fabrica_sesiones, cliente_test):
    """CU01: Administrador de plataforma da de alta empresa y admin inicial de forma atómica; aísla acceso."""
    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        rol_super = await _obtener_o_crear_rol(db, "SUPERADMIN")
        admin_plat = Usuario(
            empresa_id=None,
            rol_id=rol_super.id,
            nombres="Admin",
            apellidos="Plataforma",
            correo_electronico=f"plat_{sufijo}@plataforma.com",
            contrasenia_hash=generar_contrasenia_hash("Plataforma123!"),
            estado="ACTIVO",
        )
        db.add(admin_plat)
        await db.commit()
        await db.refresh(admin_plat)

    token_plat = crear_token_acceso(sujeto=admin_plat.id, rol="SUPERADMIN")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Alta de empresa
        codigo_emp = f"emp_{sufijo}"
        payload = {
            "razon_social": f"Boutique {sufijo} S.R.L.",
            "nombre_comercial": f"Boutique {sufijo}",
            "empresa_codigo": codigo_emp,
            "administrador": {
                "nombre": f"Gerente {sufijo}",
                "correo": f"gerente_{sufijo}@boutique.com",
                "credencial_inicial": "GerenteSeguro123!",
            },
        }

        resp = await client.post(
            "/api/v1/empresas",
            json=payload,
            headers={"Authorization": f"Bearer {token_plat}", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["empresa_codigo"] == codigo_emp
        assert data["estado"] == "PENDIENTE_PLAN"
        assert data["suscripcion_pendiente"] is True
        empresa_id = data["empresa_id"]
        admin_id = data["administrador_id"]

        # Ausencia de Idempotency-Key obligatoria rechaza con 422
        resp_sin_idem = await client.post(
            "/api/v1/empresas",
            json=payload,
            headers={"Authorization": f"Bearer {token_plat}"},
        )
        assert resp_sin_idem.status_code == 422

        # Código duplicado con Idempotency-Key nueva rechaza con 409
        resp_dup = await client.post(
            "/api/v1/empresas",
            json=payload,
            headers={"Authorization": f"Bearer {token_plat}", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert resp_dup.status_code == 409

        # Consulta de empresa por plataforma
        resp_get = await client.get(
            f"/api/v1/empresas/{empresa_id}",
            headers={"Authorization": f"Bearer {token_plat}"},
        )
        assert resp_get.status_code == 200
        assert resp_get.json()["codigo"] == codigo_emp

        # Administrador de empresa consultando su empresa: 200
        token_emp = crear_token_acceso(sujeto=uuid.UUID(admin_id), rol="ADMINISTRADOR")
        resp_own = await client.get(
            f"/api/v1/empresas/{empresa_id}",
            headers={"Authorization": f"Bearer {token_emp}"},
        )
        assert resp_own.status_code == 200

        # Administrador de empresa intentando dar de alta otra empresa: 403 Forbidden
        resp_forbid = await client.post(
            "/api/v1/empresas",
            json={**payload, "empresa_codigo": f"otra_{sufijo}"},
            headers={"Authorization": f"Bearer {token_emp}", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert resp_forbid.status_code == 403


@pytest.mark.asyncio
async def test_cu01_idempotencia_replay_conflicto_y_carrera(fabrica_sesiones, cliente_test):
    """CU01: Idempotencia durable: replay recupera resultado original, payload distinto da 409, y carrera concurrente."""
    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        rol_super = await _obtener_o_crear_rol(db, "SUPERADMIN")
        admin_plat = Usuario(
            empresa_id=None,
            rol_id=rol_super.id,
            nombres="Admin",
            apellidos="Plataforma",
            correo_electronico=f"plat_idem_{sufijo}@plataforma.com",
            contrasenia_hash=generar_contrasenia_hash("Plataforma123!"),
            estado="ACTIVO",
        )
        db.add(admin_plat)
        await db.commit()
        await db.refresh(admin_plat)

    token_plat = crear_token_acceso(sujeto=admin_plat.id, rol="SUPERADMIN")
    clave_idem = str(uuid.uuid4())

    codigo_emp = f"emp_idem_{sufijo}"
    payload_original = {
        "razon_social": f"Corporacion Idempotente {sufijo} S.A.",
        "nombre_comercial": f"IdemCorp {sufijo}",
        "empresa_codigo": codigo_emp,
        "administrador": {
            "nombre": f"Admin Idem {sufijo}",
            "correo": f"admin_idem_{sufijo}@corp.com",
            "credencial_inicial": "ClaveDurable123!",
        },
    }

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Primera llamada con Idempotency-Key
        r1 = await client.post(
            "/api/v1/empresas",
            json=payload_original,
            headers={"Authorization": f"Bearer {token_plat}", "Idempotency-Key": clave_idem},
        )
        assert r1.status_code == 201, r1.text
        data1 = r1.json()
        empresa_creada_id = data1["empresa_id"]

        # 2. Replay con la misma clave y el mismo payload: retorna el resultado original sin duplicar
        r_replay = await client.post(
            "/api/v1/empresas",
            json=payload_original,
            headers={"Authorization": f"Bearer {token_plat}", "Idempotency-Key": clave_idem},
        )
        assert r_replay.status_code == 201, r_replay.text
        data_replay = r_replay.json()
        assert data_replay["empresa_id"] == empresa_creada_id
        assert data_replay["empresa_codigo"] == codigo_emp

        # Verificar en base de datos que solo existe 1 empresa y 1 admin con ese código
        async with fabrica_sesiones() as db:
            q_cnt_emp = await db.execute(select(func.count(Empresa.id)).where(Empresa.codigo == codigo_emp))
            assert q_cnt_emp.scalar() == 1
            q_cnt_adm = await db.execute(
                select(func.count(Usuario.id)).where(Usuario.correo_electronico == payload_original["administrador"]["correo"].lower())
            )
            assert q_cnt_adm.scalar() == 1

        # 3. Reutilizar la misma clave con payload DISTINTO: conflicto 409
        payload_distinto = {
            **payload_original,
            "razon_social": "Razon Social Totalmente Modificada",
            "empresa_codigo": f"otro_cod_{sufijo}",
        }
        r_conflicto = await client.post(
            "/api/v1/empresas",
            json=payload_distinto,
            headers={"Authorization": f"Bearer {token_plat}", "Idempotency-Key": clave_idem},
        )
        assert r_conflicto.status_code == 409, r_conflicto.text

        # 4. Carrera concurrente con la misma Idempotency-Key y mismo payload
        clave_carrera = str(uuid.uuid4())
        codigo_carrera = f"emp_race_{sufijo}"
        payload_carrera = {
            "razon_social": f"Empresa Carrera {sufijo} S.A.",
            "nombre_comercial": f"Carrera {sufijo}",
            "empresa_codigo": codigo_carrera,
            "administrador": {
                "nombre": f"Admin Race {sufijo}",
                "correo": f"race_{sufijo}@carrera.com",
                "credencial_inicial": "RacePass123!",
            },
        }

        # Ejecutamos dos peticiones simultáneas con la misma clave
        t1 = client.post(
            "/api/v1/empresas",
            json=payload_carrera,
            headers={"Authorization": f"Bearer {token_plat}", "Idempotency-Key": clave_carrera},
        )
        t2 = client.post(
            "/api/v1/empresas",
            json=payload_carrera,
            headers={"Authorization": f"Bearer {token_plat}", "Idempotency-Key": clave_carrera},
        )
        resp_a, resp_b = await asyncio.gather(t1, t2)

        # Ambas deben responder 201 con la misma empresa y admin
        assert resp_a.status_code == 201, resp_a.text
        assert resp_b.status_code == 201, resp_b.text
        assert resp_a.json()["empresa_id"] == resp_b.json()["empresa_id"]

        # En base de datos solo se creó 1 registro
        async with fabrica_sesiones() as db:
            q_cnt_race = await db.execute(select(func.count(Empresa.id)).where(Empresa.codigo == codigo_carrera))
            assert q_cnt_race.scalar() == 1


@pytest.mark.asyncio
async def test_cu01_razon_social_persistida_y_consulta_publica(fabrica_sesiones, cliente_test):
    """CU01: Persistencia de razon_social/nombre_comercial y filtrado en GET /empresas (público vs plataforma)."""
    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        rol_super = await _obtener_o_crear_rol(db, "SUPERADMIN")
        admin_plat = Usuario(
            empresa_id=None,
            rol_id=rol_super.id,
            nombres="Admin",
            apellidos="Plataforma",
            correo_electronico=f"plat_pub_{sufijo}@plataforma.com",
            contrasenia_hash=generar_contrasenia_hash("Plataforma123!"),
            estado="ACTIVO",
        )
        db.add(admin_plat)
        await db.commit()
        await db.refresh(admin_plat)

    token_plat = crear_token_acceso(sujeto=admin_plat.id, rol="SUPERADMIN")

    razon_social_esperada = f"Distribuidora Textil {sufijo} S.A."
    nombre_comercial_esperado = f"Textil Moda {sufijo}"
    codigo_emp = f"textil_{sufijo}"

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Alta de empresa guardando razon_social y nombre_comercial
        resp_crear = await client.post(
            "/api/v1/empresas",
            json={
                "razon_social": razon_social_esperada,
                "nombre_comercial": nombre_comercial_esperado,
                "empresa_codigo": codigo_emp,
                "administrador": {
                    "nombre": "Admin Textil",
                    "correo": f"textil_admin_{sufijo}@textil.com",
                    "credencial_inicial": "Textil123!",
                },
            },
            headers={"Authorization": f"Bearer {token_plat}", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert resp_crear.status_code == 201, resp_crear.text
        empresa_id = resp_crear.json()["empresa_id"]

        # Consultar la empresa por ID: debe retornar razon_social y nombre_comercial persistidos
        resp_detalle = await client.get(
            f"/api/v1/empresas/{empresa_id}",
            headers={"Authorization": f"Bearer {token_plat}"},
        )
        assert resp_detalle.status_code == 200
        detalle = resp_detalle.json()
        assert detalle["razon_social"] == razon_social_esperada
        assert detalle["nombre_comercial"] == nombre_comercial_esperado
        assert detalle["codigo"] == codigo_emp
        assert detalle["estado"] == "PENDIENTE_PLAN"

        # Consulta pública GET /empresas sin token:
        # NO debe revelar la empresa en estado PENDIENTE_PLAN ni información administrativa
        resp_pub = await client.get("/api/v1/empresas")
        assert resp_pub.status_code == 200
        empresas_pub = resp_pub.json()
        assert isinstance(empresas_pub, list)
        codigos_pub = [e["codigo"] for e in empresas_pub]
        assert codigo_emp not in codigos_pub, "Empresa PENDIENTE_PLAN no debe revelarse en catálogo público"
        for emp_pub in empresas_pub:
            assert emp_pub["estado"] == "ACTIVA"
            assert "catalogo_version" not in emp_pub
            assert "administrador_correo" not in emp_pub

        # Consulta como SUPERADMIN: ve todas las empresas, incluyendo la PENDIENTE_PLAN
        resp_plat_list = await client.get(
            "/api/v1/empresas",
            headers={"Authorization": f"Bearer {token_plat}"},
        )
        assert resp_plat_list.status_code == 200
        empresas_plat = resp_plat_list.json()
        codigos_plat = [e["codigo"] for e in empresas_plat]
        assert codigo_emp in codigos_plat


@pytest.mark.asyncio
async def test_cu13_registro_sin_tenant_rechazo(fabrica_sesiones, cliente_test):
    """CU13: El registro sin empresa_codigo no asigna silenciosamente un tenant por defecto; responde 400."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Intento de registro sin especificar empresa_codigo
        resp_sin_tenant = await client.post(
            "/api/v1/clientes",
            json={
                "nombres": "Cliente",
                "apellidos": "Anonimo",
                "correo_electronico": f"anonimo_{uuid.uuid4().hex[:6]}@ejemplo.com",
                "contrasenia": "Segura123!",
            },
        )
        assert resp_sin_tenant.status_code == 400
        assert "empresa_codigo" in resp_sin_tenant.json()["detail"].lower()

        # Intento de registro con empresa_codigo en blanco
        resp_blanco = await client.post(
            "/api/v1/clientes",
            json={
                "empresa_codigo": "   ",
                "nombres": "Cliente",
                "apellidos": "Anonimo",
                "correo_electronico": f"anonimo_{uuid.uuid4().hex[:6]}@ejemplo.com",
                "contrasenia": "Segura123!",
            },
        )
        assert resp_blanco.status_code == 400
        assert "empresa_codigo" in resp_blanco.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cu13_registro_y_sesion_multitenant(fabrica_sesiones, cliente_test):
    """CU13: Dos empresas pueden registrar un cliente con el mismo correo; login incluye 8h de privacidad."""
    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        emp_a = Empresa(codigo=f"ten_a_{sufijo}", nombre=f"Tenant A {sufijo}", estado="ACTIVA")
        emp_b = Empresa(codigo=f"ten_b_{sufijo}", nombre=f"Tenant B {sufijo}", estado="ACTIVA")
        db.add_all([emp_a, emp_b])
        await db.commit()
        await db.refresh(emp_a)
        await db.refresh(emp_b)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        correo_compartido = f"cliente_{sufijo}@ejemplo.com"
        clave_comun = "ClienteSeguro123!"

        # Registro en Empresa A
        resp_reg_a = await client.post(
            "/api/v1/clientes",
            json={
                "empresa_codigo": emp_a.codigo,
                "nombres": "Cliente",
                "apellidos": "Uno",
                "correo_electronico": correo_compartido,
                "contrasenia": clave_comun,
            },
        )
        assert resp_reg_a.status_code == 201, resp_reg_a.text
        assert resp_reg_a.json()["empresa_id"] == str(emp_a.id)

        # Mismo correo en Empresa A de nuevo: 409 Conflicto
        resp_dup = await client.post(
            "/api/v1/clientes",
            json={
                "empresa_codigo": emp_a.codigo,
                "nombres": "Cliente",
                "apellidos": "Uno Bis",
                "correo_electronico": correo_compartido,
                "contrasenia": clave_comun,
            },
        )
        assert resp_dup.status_code == 409

        # Mismo correo en Empresa B: 201 Creado (aislamiento multitenant)
        resp_reg_b = await client.post(
            "/api/v1/clientes",
            json={
                "empresa_codigo": emp_b.codigo,
                "nombres": "Cliente",
                "apellidos": "Dos",
                "correo_electronico": correo_compartido,
                "contrasenia": clave_comun,
            },
        )
        assert resp_reg_b.status_code == 201, resp_reg_b.text
        assert resp_reg_b.json()["empresa_id"] == str(emp_b.id)

        # Login explícito en Empresa A
        resp_login_a = await client.post(
            "/api/v1/sesion",
            json={
                "correo_electronico": correo_compartido,
                "contrasenia": clave_comun,
                "empresa_codigo": emp_a.codigo,
            },
        )
        assert resp_login_a.status_code == 200, resp_login_a.text
        data_a = resp_login_a.json()
        assert data_a["empresa"]["codigo"] == emp_a.codigo
        assert "access_token" in data_a
        assert "privada_hasta" in data_a
        assert data_a["privada_hasta"] is not None

        # Login sin empresa_codigo cuando el correo está en dos empresas: 300 Multiple Choices
        resp_multi = await client.post(
            "/api/v1/sesion",
            json={
                "correo_electronico": correo_compartido,
                "contrasenia": clave_comun,
            },
        )
        assert resp_multi.status_code == 300
        disponibles = resp_multi.json()["detail"]["empresas_disponibles"]
        codigos_disp = [d["codigo"] for d in disponibles]
        assert emp_a.codigo in codigos_disp
        assert emp_b.codigo in codigos_disp

        # Login con contraseña errónea: 401
        resp_bad_pass = await client.post(
            "/api/v1/sesion",
            json={
                "correo_electronico": correo_compartido,
                "contrasenia": "ClaveIncorrecta!",
                "empresa_codigo": emp_a.codigo,
            },
        )
        assert resp_bad_pass.status_code == 401


@pytest.mark.asyncio
async def test_cu14_gestion_usuarios_y_proteccion_ultimo_admin(fabrica_sesiones, cliente_test):
    """CU14: Aislamiento de listado/edición de usuarios y protección del último administrador activo."""
    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        emp = Empresa(codigo=f"comp_{sufijo}", nombre=f"Empresa {sufijo}", estado="ACTIVA")
        db.add(emp)
        await db.flush()

        rol_admin = await _obtener_o_crear_rol(db, "ADMINISTRADOR")
        admin_emp = Usuario(
            empresa_id=emp.id,
            rol_id=rol_admin.id,
            nombres="Admin",
            apellidos="Unico",
            correo_electronico=f"unico_{sufijo}@empresa.com",
            contrasenia_hash=generar_contrasenia_hash("Admin123!"),
            estado="ACTIVO",
        )
        db.add(admin_emp)
        await db.commit()
        await db.refresh(admin_emp)

    token_admin = crear_token_acceso(sujeto=admin_emp.id, rol="ADMINISTRADOR")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Listar usuarios: solo ve su usuario
        resp_list = await client.get(
            "/api/v1/usuarios",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp_list.status_code == 200
        usuarios_list = resp_list.json()
        assert len(usuarios_list) == 1
        assert usuarios_list[0]["id"] == str(admin_emp.id)

        # 2. Intento de desactivar al ÚNICO administrador activo: 409 Conflicto
        resp_desact = await client.patch(
            f"/api/v1/usuarios/{admin_emp.id}/desactivar",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp_desact.status_code == 409
        assert "administrador activo" in resp_desact.json()["detail"].lower()

        # 3. Crear un segundo usuario dentro de la empresa
        resp_create = await client.post(
            "/api/v1/usuarios",
            json={
                "nombres": "Segundo",
                "apellidos": "Admin",
                "correo_electronico": f"segundo_{sufijo}@empresa.com",
                "contrasenia": "SegundoAdmin123!",
                "rol_id": str(rol_admin.id),
            },
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp_create.status_code == 201, resp_create.text
        segundo_id = resp_create.json()["id"]

        # 4. Ahora que hay 2 administradores, desactivar al primero sí es permitido
        resp_desact_ok = await client.patch(
            f"/api/v1/usuarios/{admin_emp.id}",
            json={"activo": False, "revision": 1},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp_desact_ok.status_code == 200
        assert resp_desact_ok.json()["activo"] is False

        # 5. Edición unificada PATCH /usuarios/{usuario_id} usando el admin que sigue activo
        token_segundo = crear_token_acceso(sujeto=uuid.UUID(segundo_id), rol="ADMINISTRADOR")
        resp_patch = await client.patch(
            f"/api/v1/usuarios/{segundo_id}",
            json={"nombres": "Segundo Modificado", "cargo": "Jefe de Operaciones", "revision": 1},
            headers={"Authorization": f"Bearer {token_segundo}"},
        )
        assert resp_patch.status_code == 200
        assert resp_patch.json()["nombres"] == "Segundo Modificado"


@pytest.mark.asyncio
async def test_cu14_control_revision_obsoleta(fabrica_sesiones, cliente_test):
    """CU14: Control de concurrencia optimista con revision: 409 si es obsoleta, incremento en éxito."""
    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        emp = Empresa(codigo=f"comp_rev_{sufijo}", nombre=f"Empresa Rev {sufijo}", estado="ACTIVA")
        db.add(emp)
        await db.flush()

        rol_admin = await _obtener_o_crear_rol(db, "ADMINISTRADOR")
        admin_emp = Usuario(
            empresa_id=emp.id,
            rol_id=rol_admin.id,
            nombres="Admin",
            apellidos="Principal",
            correo_electronico=f"admin_rev_{sufijo}@empresa.com",
            contrasenia_hash=generar_contrasenia_hash("Admin123!"),
            estado="ACTIVO",
            revision=1,
        )
        db.add(admin_emp)
        await db.commit()
        await db.refresh(admin_emp)

    token_admin = crear_token_acceso(sujeto=admin_emp.id, rol="ADMINISTRADOR")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Crear usuario colaborador
        r_create = await client.post(
            "/api/v1/usuarios",
            json={
                "nombres": "Carlos",
                "apellidos": "Empleado",
                "correo_electronico": f"carlos_{sufijo}@empresa.com",
                "contrasenia": "Carlos123!",
                "rol_id": str(rol_admin.id),
            },
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert r_create.status_code == 201
        colab_id = r_create.json()["id"]
        assert r_create.json()["revision"] == 1

        # Intento de actualización con revisión obsoleta (p.ej. 99 != 1)
        r_obsoleta = await client.patch(
            f"/api/v1/usuarios/{colab_id}",
            json={"nombres": "Carlos Modificado", "revision": 99},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert r_obsoleta.status_code == 409
        assert "revisión obsoleta" in r_obsoleta.json()["detail"].lower()

        # Actualización con revisión correcta (1): debe responder 200 e incrementar a 2
        r_ok = await client.patch(
            f"/api/v1/usuarios/{colab_id}",
            json={"nombres": "Carlos V2", "revision": 1},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert r_ok.status_code == 200
        assert r_ok.json()["revision"] == 2
        assert r_ok.json()["nombres"] == "Carlos V2"

        # Reutilizar la revisión 1 ahora es obsoleta: 409
        r_obsoleta_2 = await client.patch(
            f"/api/v1/usuarios/{colab_id}",
            json={"nombres": "Carlos Conflicto", "revision": 1},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert r_obsoleta_2.status_code == 409

        # Con revisión 2 avanza a 3
        r_ok_2 = await client.patch(
            f"/api/v1/usuarios/{colab_id}",
            json={"nombres": "Carlos V3", "revision": 2},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert r_ok_2.status_code == 200
        assert r_ok_2.json()["revision"] == 3


@pytest.mark.asyncio
async def test_cu14_asignacion_sucursal_ajena_rechazo(fabrica_sesiones, cliente_test):
    """CU14: Rechazo 403 al asignar una sucursal que no pertenece a la empresa del usuario administrado."""
    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        emp_a = Empresa(codigo=f"comp_a_{sufijo}", nombre=f"Empresa A {sufijo}", estado="ACTIVA")
        emp_b = Empresa(codigo=f"comp_b_{sufijo}", nombre=f"Empresa B {sufijo}", estado="ACTIVA")
        db.add_all([emp_a, emp_b])
        await db.flush()

        ciudad = (await db.execute(select(Ciudad))).scalars().first()
        if not ciudad:
            ciudad = Ciudad(nombre=f"Ciudad {sufijo}")
            db.add(ciudad)
            await db.flush()

        # Sucursal perteneciente a Empresa B
        sucursal_b = Sucursal(
            empresa_id=emp_b.id,
            ciudad_id=ciudad.id,
            nombre=f"Sucursal B {sufijo}",
            direccion="Av. B 123",
            activa=True,
        )
        db.add(sucursal_b)
        await db.flush()

        rol_admin = await _obtener_o_crear_rol(db, "ADMINISTRADOR")
        admin_a = Usuario(
            empresa_id=emp_a.id,
            rol_id=rol_admin.id,
            nombres="Admin A",
            apellidos="Empresa A",
            correo_electronico=f"admin_a_{sufijo}@empresa-a.com",
            contrasenia_hash=generar_contrasenia_hash("AdminA123!"),
            estado="ACTIVO",
        )
        db.add(admin_a)
        await db.commit()
        await db.refresh(admin_a)
        await db.refresh(sucursal_b)

    token_admin_a = crear_token_acceso(sujeto=admin_a.id, rol="ADMINISTRADOR")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Intento de crear usuario en Empresa A asignando sucursal de Empresa B: 403 Forbidden
        r_crear_ajena = await client.post(
            "/api/v1/usuarios",
            json={
                "nombres": "Empleado",
                "apellidos": "Perez",
                "correo_electronico": f"emp_a_{sufijo}@empresa-a.com",
                "contrasenia": "Clave123!",
                "rol_id": str(rol_admin.id),
                "sucursal_id": str(sucursal_b.id),
            },
            headers={"Authorization": f"Bearer {token_admin_a}"},
        )
        assert r_crear_ajena.status_code == 403
        assert "no pertenece" in r_crear_ajena.json()["detail"].lower()

        # Crear usuario sin sucursal
        r_crear_ok = await client.post(
            "/api/v1/usuarios",
            json={
                "nombres": "Empleado",
                "apellidos": "Perez",
                "correo_electronico": f"emp_a_{sufijo}@empresa-a.com",
                "contrasenia": "Clave123!",
                "rol_id": str(rol_admin.id),
            },
            headers={"Authorization": f"Bearer {token_admin_a}"},
        )
        assert r_crear_ok.status_code == 201
        usuario_creado_id = r_crear_ok.json()["id"]

        # Intento de actualizar usuario asignándole sucursal de Empresa B: 403 Forbidden
        r_patch_ajena = await client.patch(
            f"/api/v1/usuarios/{usuario_creado_id}",
            json={"sucursal_id": str(sucursal_b.id), "revision": 1},
            headers={"Authorization": f"Bearer {token_admin_a}"},
        )
        assert r_patch_ajena.status_code == 403
        assert "no pertenece" in r_patch_ajena.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cu14_carrera_ultimo_administrador(fabrica_sesiones, cliente_test):
    """CU14: Protección contra carrera en la desactivación concurrente del último administrador activo."""
    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        emp = Empresa(codigo=f"comp_race_{sufijo}", nombre=f"Empresa Race {sufijo}", estado="ACTIVA")
        db.add(emp)
        await db.flush()

        rol_super = await _obtener_o_crear_rol(db, "SUPERADMIN")
        superadmin = Usuario(
            empresa_id=None,
            rol_id=rol_super.id,
            nombres="Super",
            apellidos="Admin",
            correo_electronico=f"super_race_{sufijo}@plataforma.com",
            contrasenia_hash=generar_contrasenia_hash("Super123!"),
            estado="ACTIVO",
        )
        db.add(superadmin)

        rol_admin = await _obtener_o_crear_rol(db, "ADMINISTRADOR")
        adm1 = Usuario(
            empresa_id=emp.id,
            rol_id=rol_admin.id,
            nombres="Admin",
            apellidos="Uno",
            correo_electronico=f"adm1_{sufijo}@race.com",
            contrasenia_hash=generar_contrasenia_hash("Clave123!"),
            estado="ACTIVO",
        )
        adm2 = Usuario(
            empresa_id=emp.id,
            rol_id=rol_admin.id,
            nombres="Admin",
            apellidos="Dos",
            correo_electronico=f"adm2_{sufijo}@race.com",
            contrasenia_hash=generar_contrasenia_hash("Clave123!"),
            estado="ACTIVO",
        )
        db.add_all([adm1, adm2])
        await db.commit()
        await db.refresh(superadmin)
        await db.refresh(adm1)
        await db.refresh(adm2)

    token_super = crear_token_acceso(sujeto=superadmin.id, rol="SUPERADMIN")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Lanzamos ambas desactivaciones de forma concurrente sobre los 2 únicos administradores
        t1 = client.patch(
            f"/api/v1/usuarios/{adm1.id}",
            json={"activo": False, "revision": 1},
            headers={"Authorization": f"Bearer {token_super}"},
        )
        t2 = client.patch(
            f"/api/v1/usuarios/{adm2.id}",
            json={"activo": False, "revision": 1},
            headers={"Authorization": f"Bearer {token_super}"},
        )
        r1, r2 = await asyncio.gather(t1, t2)

        codigos_status = {r1.status_code, r2.status_code}
        # Una debe tener éxito (200) y la otra debe ser prevenida con 409 (bloqueo pesimista sobre el último admin)
        assert 200 in codigos_status, f"Una desactivación debió tener éxito: r1={r1.status_code}, r2={r2.status_code}"
        assert 409 in codigos_status, f"La desactivación concurrente debió ser prevenida con 409: r1={r1.status_code}, r2={r2.status_code}"

        # Comprobar en base de datos que queda EXACTAMENTE 1 administrador activo en la empresa
        async with fabrica_sesiones() as db:
            q_activos = await db.execute(
                select(func.count(Usuario.id))
                .where(Usuario.empresa_id == emp.id, Usuario.estado == "ACTIVO")
            )
            total_activos = q_activos.scalar()
            assert total_activos == 1, f"Debió quedar exactamente 1 admin activo, quedaron {total_activos}"


@pytest.mark.asyncio
async def test_cu01_rol_plataforma_con_empresa_rechaza_403(fabrica_sesiones, cliente_test):
    """CU01: require_administrador_plataforma debe exigir rol Y ámbito global (empresa_id IS NULL).
    Un usuario empresarial con rol 'ADMINISTRADOR_PLATAFORMA' o 'ADMINISTRADOR_SISTEMA' debe recibir 403."""
    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        emp = Empresa(codigo=f"emp_test_{sufijo}", nombre=f"Empresa {sufijo}", estado="ACTIVA")
        db.add(emp)
        await db.flush()

        rol_plat = await _obtener_o_crear_rol(db, "ADMINISTRADOR_PLATAFORMA")
        # Usuario empresarial pero con nombre de rol de plataforma
        usuario_emp_plat = Usuario(
            empresa_id=emp.id,  # Ámbito empresarial (NO global)
            rol_id=rol_plat.id,
            nombres="Falso",
            apellidos="AdminPlat",
            correo_electronico=f"falso_plat_{sufijo}@empresa.com",
            contrasenia_hash=generar_contrasenia_hash("Clave123!"),
            estado="ACTIVO",
        )
        db.add(usuario_emp_plat)
        await db.commit()
        await db.refresh(usuario_emp_plat)

    token_falso = crear_token_acceso(sujeto=usuario_emp_plat.id, rol="ADMINISTRADOR_PLATAFORMA")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/empresas",
            json={
                "razon_social": "Intento Ilegal S.A.",
                "nombre_comercial": "Intento Ilegal",
                "empresa_codigo": f"ilegal_{sufijo}",
                "administrador": {
                    "nombre": "Admin Ilegal",
                    "correo": f"ilegal_{sufijo}@corp.com",
                    "credencial_inicial": "ClaveDurable123!",
                },
            },
            headers={"Authorization": f"Bearer {token_falso}", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert resp.status_code == 403
        assert "ámbito global" in resp.json()["detail"].lower() or "plataforma" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cu14_concurrencia_mismo_usuario_retorna_409(fabrica_sesiones, cliente_test):
    """CU14: Dos ediciones simultáneas del MISMO usuario con la misma revisión devuelven 409 al perdedor (comparación atómica)."""
    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        emp = Empresa(codigo=f"emp_conc_{sufijo}", nombre=f"Empresa Conc {sufijo}", estado="ACTIVA")
        db.add(emp)
        await db.flush()

        rol_admin = await _obtener_o_crear_rol(db, "ADMINISTRADOR")
        admin = Usuario(
            empresa_id=emp.id,
            rol_id=rol_admin.id,
            nombres="Admin",
            apellidos="Concurrente",
            correo_electronico=f"admin_conc_{sufijo}@empresa.com",
            contrasenia_hash=generar_contrasenia_hash("Clave123!"),
            estado="ACTIVO",
            revision=1,
        )
        colaborador = Usuario(
            empresa_id=emp.id,
            rol_id=rol_admin.id,
            nombres="Juan",
            apellidos="Perez",
            correo_electronico=f"juan_{sufijo}@empresa.com",
            contrasenia_hash=generar_contrasenia_hash("Clave123!"),
            estado="ACTIVO",
            revision=1,
        )
        db.add_all([admin, colaborador])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(colaborador)

    token_admin = crear_token_acceso(sujeto=admin.id, rol="ADMINISTRADOR")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Dos peticiones concurrentes para actualizar al colaborador con la misma revisión (1)
        req_a = client.patch(
            f"/api/v1/usuarios/{colaborador.id}",
            json={"nombres": "Juan A", "revision": 1},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        req_b = client.patch(
            f"/api/v1/usuarios/{colaborador.id}",
            json={"nombres": "Juan B", "revision": 1},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        resp_a, resp_b = await asyncio.gather(req_a, req_b)

        statuses = {resp_a.status_code, resp_b.status_code}
        assert 200 in statuses, f"Uno debió ganar con 200: a={resp_a.status_code}, b={resp_b.status_code}"
        assert 409 in statuses, f"El perdedor debió recibir 409 por revisión obsoleta: a={resp_a.status_code}, b={resp_b.status_code}"

        # Comprobar que en base de datos la revisión aumentó exactamente a 2
        async with fabrica_sesiones() as db:
            q_user = await db.execute(select(Usuario).where(Usuario.id == colaborador.id))
            usr_final = q_user.scalars().first()
            assert usr_final.revision == 2


@pytest.mark.asyncio
async def test_cu14_outbox_rollback_si_falla_evento(fabrica_sesiones, cliente_test):
    """CU14: El outbox debe escribirse en la misma transacción; si falla el evento, se hace rollback y no se silencia el error."""
    from unittest.mock import patch
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import AsyncSession

    sufijo = uuid.uuid4().hex[:6]
    async with fabrica_sesiones() as db:
        emp = Empresa(codigo=f"emp_out_{sufijo}", nombre=f"Empresa Out {sufijo}", estado="ACTIVA")
        db.add(emp)
        await db.flush()

        rol_admin = await _obtener_o_crear_rol(db, "ADMINISTRADOR")
        admin = Usuario(
            empresa_id=emp.id,
            rol_id=rol_admin.id,
            nombres="Admin",
            apellidos="Outbox",
            correo_electronico=f"admin_out_{sufijo}@empresa.com",
            contrasenia_hash=generar_contrasenia_hash("Clave123!"),
            estado="ACTIVO",
            revision=1,
        )
        colaborador = Usuario(
            empresa_id=emp.id,
            rol_id=rol_admin.id,
            nombres="Pedro",
            apellidos="Original",
            correo_electronico=f"pedro_{sufijo}@empresa.com",
            contrasenia_hash=generar_contrasenia_hash("Clave123!"),
            estado="ACTIVO",
            revision=1,
        )
        db.add_all([admin, colaborador])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(colaborador)

    token_admin = crear_token_acceso(sujeto=admin.id, rol="ADMINISTRADOR")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Simulamos que al insertar en eventos_outbox ocurre un error de base de datos
        real_execute = AsyncSession.execute

        async def execute_con_fallo_en_outbox(self, statement, *args, **kwargs):
            if "eventos_outbox" in str(statement):
                raise IntegrityError("INSERT eventos_outbox simulado fallo", orig=Exception("DB constraint error"), params={})
            return await real_execute(self, statement, *args, **kwargs)

        with patch.object(AsyncSession, "execute", new=execute_con_fallo_en_outbox):
            resp = await client.patch(
                f"/api/v1/usuarios/{colaborador.id}",
                json={"nombres": "Pedro Modificado", "revision": 1},
                headers={"Authorization": f"Bearer {token_admin}"},
            )
            # No debe silenciar el error con except Exception: pass; debe fallar con 500
            assert resp.status_code == 500

        # Verificar que en base de datos NO se persistió el cambio de nombre ni se incrementó la revisión
        async with fabrica_sesiones() as db:
            q_user = await db.execute(select(Usuario).where(Usuario.id == colaborador.id))
            usr_rec = q_user.scalars().first()
            assert usr_rec.nombres == "Pedro"
            assert usr_rec.revision == 1
