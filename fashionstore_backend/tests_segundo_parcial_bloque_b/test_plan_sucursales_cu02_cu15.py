"""Pruebas funcionales E1-B2: CU02 (Suscripción y capacidades) y CU15 (Sucursales y tarifas)."""
import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select, func

from backend.app.core.reloj import utcnow
from backend.app.core.modules.identidad_empresas.models import Plan, Suscripcion
from backend.app.core.modules.organizacion.models import Ciudad, Sucursal
from backend.app.core.modules.reservas_traslados.models import Reserva


@pytest.mark.asyncio
async def test_cu02_asignar_suscripcion_por_plataforma_exitoso(http, escenario, fabrica_sesiones):
    """CU02: Administrador de plataforma asigna suscripción profesional con capacidades."""
    http.usar(escenario.usuario_global_sin_empresa)

    async with fabrica_sesiones() as db:
        plan_basico = (await db.execute(select(Plan).where(Plan.codigo == "BASICO"))).scalars().first()
        assert plan_basico is not None

    inicio = utcnow()
    vence = inicio + timedelta(days=30)
    key = uuid.uuid4()

    payload = {
        "plan_id": str(plan_basico.id),
        "inicio_en": inicio.isoformat(),
        "vence_en": vence.isoformat(),
        "motivo": "Alta de plan basico para pruebas",
    }

    resp = await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_b_id}/suscripciones",
        headers={"Idempotency-Key": str(key)},
        json=payload,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["plan_codigo"] == "BASICO"
    assert data["limite_sucursales"] == 2
    assert "OFFLINE" in data["capacidades"]
    assert data["estado_efectivo"] == "VIGENTE"
    assert data["version"] >= 1


@pytest.mark.asyncio
async def test_cu02_asignar_suscripcion_idempotencia(http, escenario, fabrica_sesiones):
    """CU02: Reintento con misma clave devuelve 201 original; con payload distinto devuelve 409."""
    http.usar(escenario.usuario_global_sin_empresa)

    async with fabrica_sesiones() as db:
        plan = (await db.execute(select(Plan).where(Plan.codigo == "BASICO"))).scalars().first()

    inicio = utcnow()
    vence = inicio + timedelta(days=60)
    key = uuid.uuid4()

    payload = {
        "plan_id": str(plan.id),
        "inicio_en": inicio.isoformat(),
        "vence_en": vence.isoformat(),
        "motivo": "Asignacion para prueba de idempotencia",
    }

    # 1. Petición inicial
    resp1 = await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_b_id}/suscripciones",
        headers={"Idempotency-Key": str(key)},
        json=payload,
    )
    assert resp1.status_code == 201, resp1.text

    # 2. Replay idéntico
    resp2 = await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_b_id}/suscripciones",
        headers={"Idempotency-Key": str(key)},
        json=payload,
    )
    assert resp2.status_code == 201
    assert resp2.json()["suscripcion_id"] == resp1.json()["suscripcion_id"]

    # 3. Mismo key, distinto payload -> 409 Conflicto
    payload_conflicto = dict(payload, motivo="Motivo cambiado para causar conflicto")
    resp3 = await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_b_id}/suscripciones",
        headers={"Idempotency-Key": str(key)},
        json=payload_conflicto,
    )
    assert resp3.status_code == 409


@pytest.mark.asyncio
async def test_cu02_empresa_admin_recibe_403_al_asignar_suscripcion(http, escenario):
    """CU02: Administrador empresarial no puede asignar suscripciones (solo plataforma)."""
    http.usar(escenario.usuario_admin_a)

    inicio = utcnow()
    vence = inicio + timedelta(days=30)
    key = uuid.uuid4()

    resp = await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_a_id}/suscripciones",
        headers={"Idempotency-Key": str(key)},
        json={
            "plan_id": str(uuid.uuid4()),
            "inicio_en": inicio.isoformat(),
            "vence_en": vence.isoformat(),
            "motivo": "Intento no autorizado",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cu02_fechas_incoherentes_devuelve_422(http, escenario, fabrica_sesiones):
    """CU02: vence_en menor o igual a inicio_en devuelve HTTP 422."""
    http.usar(escenario.usuario_global_sin_empresa)

    async with fabrica_sesiones() as db:
        plan = (await db.execute(select(Plan).where(Plan.codigo == "BASICO"))).scalars().first()

    inicio = utcnow()
    vence = inicio - timedelta(days=1)
    key = uuid.uuid4()

    resp = await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_b_id}/suscripciones",
        headers={"Idempotency-Key": str(key)},
        json={
            "plan_id": str(plan.id),
            "inicio_en": inicio.isoformat(),
            "vence_en": vence.isoformat(),
            "motivo": "Fechas invalidas",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_cu02_consultar_mi_plan_y_aislamiento(http, escenario):
    """CU02: Empresa consulta su propio plan; no puede consultar el de otra empresa."""
    http.usar(escenario.usuario_admin_a)

    resp = await http.cliente.get("/api/v1/empresas/mi-plan")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["empresa_id"] == str(escenario.empresa_a_id)
    assert "limite_sucursales" in data

    # No puede consultar historial de empresa B
    resp_b = await http.cliente.get(f"/api/v1/empresas/{escenario.empresa_b_id}/suscripciones")
    assert resp_b.status_code == 403


@pytest.mark.asyncio
async def test_cu02_reduccion_plan_incompatible_rechazada_con_409(http, escenario, fabrica_sesiones):
    """CU02: Intentar reducir a un plan con menor límite que las sucursales activas devuelve 409."""
    http.usar(escenario.usuario_global_sin_empresa)

    # Empresa A tiene Profesional (10 sucursales). Vamos a crearle 3 sucursales activas en la BD
    async with fabrica_sesiones() as db:
        ciudad = (await db.execute(select(Ciudad))).scalars().first()
        plan_basico = (await db.execute(select(Plan).where(Plan.codigo == "BASICO"))).scalars().first()
        # Asegurar 3 sucursales activas
        for i in range(3):
            db.add(
                Sucursal(
                    empresa_id=escenario.empresa_a_id,
                    ciudad_id=ciudad.id,
                    nombre=f"Sucursal Reduccion {i}_{uuid.uuid4().hex[:6]}",
                    direccion=f"Calle Reduccion {i}",
                    activa=True,
                    revision=1,
                )
            )
        await db.commit()

    inicio = utcnow()
    vence = inicio + timedelta(days=30)
    key = uuid.uuid4()

    # Intentar pasar a BÁSICO (admite máximo 2 sucursales)
    resp = await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_a_id}/suscripciones",
        headers={"Idempotency-Key": str(key)},
        json={
            "plan_id": str(plan_basico.id),
            "inicio_en": inicio.isoformat(),
            "vence_en": vence.isoformat(),
            "motivo": "Reduccion a basico incompatible",
        },
    )
    assert resp.status_code == 409
    assert "Reducción incompatible" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cu15_ciudades_solo_plataforma(http, escenario):
    """CU15: Empresa no puede crear ni modificar ciudades globales (recibe 403)."""
    # 1. Empresa admin intenta crear ciudad -> 403
    http.usar(escenario.usuario_admin_a)
    resp1 = await http.cliente.post(
        "/api/v1/ciudades",
        json={"nombre": f"Ciudad Empresa {uuid.uuid4().hex[:6]}"},
    )
    assert resp1.status_code == 403

    # 2. Plataforma admin crea ciudad -> 201
    http.usar(escenario.usuario_global_sin_empresa)
    nombre_ciudad = f"Ciudad Plataforma {uuid.uuid4().hex[:6]}"
    resp2 = await http.cliente.post(
        "/api/v1/ciudades",
        json={"nombre": nombre_ciudad},
    )
    assert resp2.status_code == 201
    ciudad_id = resp2.json()["id"]

    # 3. Empresa admin intenta modificar la ciudad -> 403
    http.usar(escenario.usuario_admin_a)
    resp3 = await http.cliente.patch(
        f"/api/v1/ciudades/{ciudad_id}",
        json={"nombre": "Nuevo Nombre Prohibido"},
    )
    assert resp3.status_code == 403

    # 4. Plataforma admin modifica ciudad -> 200
    http.usar(escenario.usuario_global_sin_empresa)
    resp4 = await http.cliente.patch(
        f"/api/v1/ciudades/{ciudad_id}",
        json={"nombre": f"{nombre_ciudad} Editada"},
    )
    assert resp4.status_code == 200
    assert resp4.json()["nombre"] == f"{nombre_ciudad} Editada"


@pytest.mark.asyncio
async def test_cu15_limite_sucursales_activas_plan_basico(http, escenario, fabrica_sesiones):
    """CU15: En plan Básico (máximo 2 activas), crear la tercera sucursal devuelve 409."""
    # Asignamos Básico a Empresa B (que no tiene sucursales todavía)
    http.usar(escenario.usuario_global_sin_empresa)
    async with fabrica_sesiones() as db:
        plan_basico = (await db.execute(select(Plan).where(Plan.codigo == "BASICO"))).scalars().first()
        ciudad = (await db.execute(select(Ciudad))).scalars().first()

    inicio = utcnow()
    vence = inicio + timedelta(days=30)
    await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_b_id}/suscripciones",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "plan_id": str(plan_basico.id),
            "inicio_en": inicio.isoformat(),
            "vence_en": vence.isoformat(),
            "motivo": "Asignar basico a B",
        },
    )

    # Creamos un usuario admin para Empresa B
    async with fabrica_sesiones() as db:
        admin_b = (
            await db.execute(
                select(escenario.usuario_b.__class__).where(
                    escenario.usuario_b.__class__.empresa_id == escenario.empresa_b_id,
                )
            )
        ).scalars().first()
        # Asignarle rol ADMINISTRADOR
        rol_adm = (await db.execute(select(escenario.usuario_admin_a.rol.__class__).where(escenario.usuario_admin_a.rol.__class__.nombre == "ADMINISTRADOR"))).scalars().first()
        admin_b.rol_id = rol_adm.id
        admin_b.rol = rol_adm
        await db.commit()

    http.usar(admin_b)

    # Empresa B ya cuenta con 1 sucursal activa en el escenario.
    # Con plan Básico (máximo 2 activas):
    # Crear sucursal 1 adicional alcanza el límite (2 activas) -> 201
    s1 = await http.cliente.post(
        "/api/v1/sucursales",
        json={
            "ciudad_id": str(ciudad.id),
            "nombre": f"Sucursal B1 {uuid.uuid4().hex[:6]}",
            "direccion": "Direccion 1",
            "tarifa_base_delivery": "10.00",
            "incremento_anillo_delivery": "2.00",
        },
    )
    assert s1.status_code == 201, s1.text

    # Intentar crear una sucursal adicional excede el límite (serían 3 activas) -> 409
    s2 = await http.cliente.post(
        "/api/v1/sucursales",
        json={
            "ciudad_id": str(ciudad.id),
            "nombre": f"Sucursal B2 {uuid.uuid4().hex[:6]}",
            "direccion": "Direccion 2",
            "tarifa_base_delivery": "10.00",
            "incremento_anillo_delivery": "2.00",
        },
    )
    assert s2.status_code == 409
    assert "Límite de sucursales activas alcanzado" in s2.json()["detail"]


@pytest.mark.asyncio
async def test_cu15_actualizar_sucursal_concurrencia_optimista(http, escenario):
    """CU15: Dos ediciones concurrentes de la misma sucursal con la misma revisión; una gana (200) y la otra recibe 409."""
    http.usar(escenario.usuario_admin_a)

    # Obtenemos la sucursal actual de Empresa A
    resp_get = await http.cliente.get(f"/api/v1/sucursales/{escenario.sucursal_a_id}")
    assert resp_get.status_code == 200
    rev_actual = resp_get.json()["revision"]

    # Lanzamos dos peticiones concurrentes con la misma revision
    tarea1 = http.cliente.patch(
        f"/api/v1/sucursales/{escenario.sucursal_a_id}",
        json={"nombre": f"Nombre Concurrente 1 {uuid.uuid4().hex[:4]}", "revision": rev_actual},
    )
    tarea2 = http.cliente.patch(
        f"/api/v1/sucursales/{escenario.sucursal_a_id}",
        json={"nombre": f"Nombre Concurrente 2 {uuid.uuid4().hex[:4]}", "revision": rev_actual},
    )

    resps = await asyncio.gather(tarea1, tarea2)
    statuses = [r.status_code for r in resps]

    assert 200 in statuses, f"Ninguna petición obtuvo 200: {statuses}"
    assert 409 in statuses, f"No se detectó colisión 409: {statuses}"


@pytest.mark.asyncio
async def test_cu15_desactivar_con_reservas_pendientes_devuelve_409(http, escenario, fabrica_sesiones):
    """CU15: Desactivar una sucursal con reservas activas pendientes es rechazado con 409."""
    http.usar(escenario.usuario_admin_a)

    # 1. Crear una reserva activa en sucursal_a
    async with fabrica_sesiones() as db:
        reserva = Reserva(
            empresa_id=escenario.empresa_a_id,
            cliente_id=escenario.usuario_a.id,
            sucursal_destino_id=escenario.sucursal_a_id,
            codigo=f"FS-{uuid.uuid4().hex[:6].upper()}",
            estado="PENDIENTE",
            vence_en=utcnow() + timedelta(hours=24),
        )
        db.add(reserva)
        await db.commit()

    # 2. Consultar sucursal para obtener su revisión actual
    resp_get = await http.cliente.get(f"/api/v1/sucursales/{escenario.sucursal_a_id}")
    rev = resp_get.json()["revision"]

    # 3. Intentar desactivar
    resp_desactivar = await http.cliente.patch(
        f"/api/v1/sucursales/{escenario.sucursal_a_id}",
        json={"activa": False, "revision": rev},
    )
    assert resp_desactivar.status_code == 409
    assert "compromisos pendientes" in resp_desactivar.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cu02_no_delete_al_asignar_suscripcion_solapada_preserva_historial(http, escenario, fabrica_sesiones):
    """CU02: Asignar suscripción solapada no ejecuta DELETE destructivo; conserva historial y versiones."""
    http.usar(escenario.usuario_global_sin_empresa)

    async with fabrica_sesiones() as db:
        plan_basico = (await db.execute(select(Plan).where(Plan.codigo == "BASICO"))).scalars().first()
        plan_pro = (await db.execute(select(Plan).where(Plan.codigo == "PROFESIONAL"))).scalars().first()

    ahora = utcnow()
    # 1. Asignar suscripción futura 1: dentro de 10 días por 30 días
    futura_inicio = ahora + timedelta(days=10)
    futura_vence = futura_inicio + timedelta(days=30)
    resp1 = await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_b_id}/suscripciones",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "plan_id": str(plan_basico.id),
            "inicio_en": futura_inicio.isoformat(),
            "vence_en": futura_vence.isoformat(),
            "motivo": "Suscripción futura programada",
        },
    )
    assert resp1.status_code == 201, resp1.text
    sub1_id = uuid.UUID(resp1.json()["suscripcion_id"])

    # Contar suscripciones antes de la nueva asignación solapada
    async with fabrica_sesiones() as db:
        q_count = select(func.count(Suscripcion.id)).where(Suscripcion.empresa_id == escenario.empresa_b_id)
        count_antes = (await db.execute(q_count)).scalar() or 0

    # 2. Asignar nueva suscripción que se solapa con la futura (inicia ahora y dura 20 días, solapando el inicio de sub1)
    nueva_inicio = ahora
    nueva_vence = ahora + timedelta(days=20)
    resp2 = await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_b_id}/suscripciones",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "plan_id": str(plan_pro.id),
            "inicio_en": nueva_inicio.isoformat(),
            "vence_en": nueva_vence.isoformat(),
            "motivo": "Nueva suscripción solapada",
        },
    )
    assert resp2.status_code == 201, resp2.text
    sub2_id = uuid.UUID(resp2.json()["suscripcion_id"])

    # 3. Comprobar que NO SE BORRÓ ningún registro: el conteo en BD aumentó en 1 exactamente
    async with fabrica_sesiones() as db:
        count_despues = (await db.execute(q_count)).scalar() or 0
        assert count_despues == count_antes + 1, f"Se borraron registros: antes={count_antes}, despues={count_despues}"

        # 4. Verificar que sub1 sigue existiendo en base de datos y su vigencia fue reubicada sin solaparse
        sub1_db = await db.get(Suscripcion, sub1_id)
        assert sub1_db is not None, "La suscripción previa fue eliminada destructivamente"
        sub2_db = await db.get(Suscripcion, sub2_id)
        assert sub2_db is not None

        # sub1 ahora inicia después o exactamente cuando termina sub2
        assert sub1_db.inicia_en >= sub2_db.vence_en
        # La duración de sub1 (30 días) se preservó intacta
        assert sub1_db.vence_en - sub1_db.inicia_en == timedelta(days=30)


@pytest.mark.asyncio
async def test_cu15_concurrencia_crear_sucursal_limite_plan(http, escenario, fabrica_sesiones):
    """CU15: Dos creaciones concurrentes para alcanzar el límite del plan; una gana y la otra recibe 409."""
    # Asignamos Básico a Empresa B
    http.usar(escenario.usuario_global_sin_empresa)
    async with fabrica_sesiones() as db:
        plan_basico = (await db.execute(select(Plan).where(Plan.codigo == "BASICO"))).scalars().first()
        ciudad = (await db.execute(select(Ciudad))).scalars().first()

    inicio = utcnow()
    vence = inicio + timedelta(days=30)
    await http.cliente.post(
        f"/api/v1/empresas/{escenario.empresa_b_id}/suscripciones",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "plan_id": str(plan_basico.id),
            "inicio_en": inicio.isoformat(),
            "vence_en": vence.isoformat(),
            "motivo": "Asignar basico a B para prueba concurrente",
        },
    )

    # Creamos un usuario admin para Empresa B
    async with fabrica_sesiones() as db:
        admin_b = (
            await db.execute(
                select(escenario.usuario_b.__class__).where(
                    escenario.usuario_b.__class__.empresa_id == escenario.empresa_b_id,
                )
            )
        ).scalars().first()
        rol_adm = (await db.execute(select(escenario.usuario_admin_a.rol.__class__).where(escenario.usuario_admin_a.rol.__class__.nombre == "ADMINISTRADOR"))).scalars().first()
        admin_b.rol_id = rol_adm.id
        admin_b.rol = rol_adm
        await db.commit()

    http.usar(admin_b)

    # Empresa B tiene 1 sucursal inicial (o las creadas previamente). Consultamos cuántas tiene activas
    resp_lista = await http.cliente.get("/api/v1/sucursales")
    activas_actuales = len(resp_lista.json())

    if activas_actuales < 2:
        tarea1 = http.cliente.post(
            "/api/v1/sucursales",
            json={
                "ciudad_id": str(ciudad.id),
                "nombre": f"Sucursal Concurrente 1 {uuid.uuid4().hex[:6]}",
                "direccion": "Dir Concurrente 1",
            },
        )
        tarea2 = http.cliente.post(
            "/api/v1/sucursales",
            json={
                "ciudad_id": str(ciudad.id),
                "nombre": f"Sucursal Concurrente 2 {uuid.uuid4().hex[:6]}",
                "direccion": "Dir Concurrente 2",
            },
        )
        resps = await asyncio.gather(tarea1, tarea2)
        statuses = [r.status_code for r in resps]
        assert 201 in statuses, f"Ninguna petición obtuvo 201: {statuses}"
        assert 409 in statuses, f"No se controló el límite bajo concurrencia: {statuses}"
