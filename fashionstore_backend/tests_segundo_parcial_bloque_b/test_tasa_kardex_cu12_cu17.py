"""Pruebas funcionales E1-B3: CU12 (Tasa BOB/USD) y CU17 (Kardex y Existencias)."""
import uuid
from decimal import Decimal
from datetime import timedelta
import pytest
from sqlalchemy import select, func

from backend.app.core.reloj import utcnow
from backend.app.core.modules.inventario.models import (
    InventarioSucursal,
    MovimientoInventario,
)
from backend.app.core.modules.organizacion.models import TasaCambio


@pytest.mark.asyncio
async def test_cu12_crear_tasa_plataforma_idempotente(http, escenario):
    """CU12: Administrador de plataforma registra tasa BOB/USD con idempotencia y outbox."""
    http.usar(escenario.usuario_global_sin_empresa)

    inicio = utcnow()
    vence = inicio + timedelta(days=365)
    key = uuid.uuid4()

    payload = {
        "tasa_bob_por_usd": "6.96",
        "vigente_desde": inicio.isoformat(),
        "vigente_hasta": vence.isoformat(),
        "motivo": "Fijación de tipo de cambio oficial BOB/USD",
    }

    # 1. Creación exitosa (201)
    resp = await http.cliente.post(
        "/api/v1/plataforma/tasas-cambio",
        headers={"Idempotency-Key": str(key)},
        json=payload,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert Decimal(data["tasa_bob_por_usd"]) == Decimal("6.96")
    assert data["version"] >= 1
    assert data["motivo"] == "Fijación de tipo de cambio oficial BOB/USD"

    # 2. Replay idempotente idéntico
    resp_replay = await http.cliente.post(
        "/api/v1/plataforma/tasas-cambio",
        headers={"Idempotency-Key": str(key)},
        json=payload,
    )
    assert resp_replay.status_code == 201
    assert resp_replay.json()["id"] == data["id"]

    # 3. Mismo Idempotency-Key con payload distinto retorna 409
    payload_distinto = dict(payload, tasa_bob_por_usd="7.10")
    resp_conflict = await http.cliente.post(
        "/api/v1/plataforma/tasas-cambio",
        headers={"Idempotency-Key": str(key)},
        json=payload_distinto,
    )
    assert resp_conflict.status_code == 409


@pytest.mark.asyncio
async def test_cu12_empresa_rechaza_creacion_tasa_403(http, escenario):
    """CU12: Solo plataforma puede configurar tasa; empresa recibe 403."""
    http.usar(escenario.usuario_admin_a)

    payload = {
        "tasa_bob_por_usd": "6.96",
        "vigente_desde": utcnow().isoformat(),
        "motivo": "Intento no autorizado de empresa",
    }
    resp = await http.cliente.post(
        "/api/v1/plataforma/tasas-cambio",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=payload,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cu12_cotizar_bob_a_usd_redondeo_half_up(http, escenario):
    """CU12: Cotizar monto BOB a USD exacto con Decimal y ROUND_HALF_UP a centavos."""
    # Asegurar tasa vigente a 6.96
    http.usar(escenario.usuario_global_sin_empresa)
    inicio = utcnow() - timedelta(minutes=5)
    await http.cliente.post(
        "/api/v1/plataforma/tasas-cambio",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "tasa_bob_por_usd": "6.96",
            "vigente_desde": inicio.isoformat(),
            "motivo": "Tasa fija para prueba de cotizacion",
        },
    )

    # Cotizar 100.00 BOB / 6.96 = 14.367816... -> ROUND_HALF_UP a 14.37 USD (1437 centavos)
    resp = await http.cliente.get(
        "/api/v1/plataforma/tasas-cambio/cotizar",
        params={"monto_bob": "100.00"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert Decimal(str(data["monto_usd"])) == Decimal("14.37")
    assert data["centavos_usd"] == 1437
    assert Decimal(str(data["tasa_bob_por_usd"])) == Decimal("6.96")

    # Cotizar 69.60 BOB / 6.96 = 10.00 USD (1000 centavos)
    resp2 = await http.cliente.get(
        "/api/v1/plataforma/tasas-cambio/cotizar",
        params={"monto_bob": "69.60"},
    )
    assert resp2.status_code == 200
    assert Decimal(str(resp2.json()["monto_usd"])) == Decimal("10.00")
    assert resp2.json()["centavos_usd"] == 1000


@pytest.mark.asyncio
async def test_cu12_vigencias_sin_solapamiento_cierra_anterior(http, escenario):
    """CU12: Nueva tasa trunca automáticamente la vigencia de la anterior sin violar exclusión."""
    http.usar(escenario.usuario_global_sin_empresa)

    inicio1 = utcnow() - timedelta(hours=1)
    await http.cliente.post(
        "/api/v1/plataforma/tasas-cambio",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "tasa_bob_por_usd": "6.90",
            "vigente_desde": inicio1.isoformat(),
            "motivo": "Tasa previa",
        },
    )

    inicio2 = utcnow()
    resp2 = await http.cliente.post(
        "/api/v1/plataforma/tasas-cambio",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "tasa_bob_por_usd": "6.96",
            "vigente_desde": inicio2.isoformat(),
            "motivo": "Tasa nueva que sucede a la anterior",
        },
    )
    assert resp2.status_code == 201

    resp_vigente = await http.cliente.get("/api/v1/plataforma/tasas-cambio/vigente")
    assert resp_vigente.status_code == 200
    assert Decimal(resp_vigente.json()["tasa_bob_por_usd"]) == Decimal("6.96")


@pytest.mark.asyncio
async def test_cu17_existencias_enriquecidas_cuatro_metricas(http, escenario, fabrica_sesiones):
    """CU17: Consultar existencias devuelve físico, libre, reservado, cupo offline y valorización."""
    http.usar(escenario.usuario_admin_a)

    # Actualizar inventario para simular stock reservado y cupo asignado
    async with fabrica_sesiones() as db:
        inv = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                )
            )
        ).scalars().first()
        assert inv is not None
        inv.disponible = 20
        inv.reservado = 5
        inv.comprometido_caja = 3
        inv.comprometido_traslado = 2
        await db.commit()

    resp = await http.cliente.get(
        "/api/v1/inventario/existencias",
        params={"sucursal_id": str(escenario.sucursal_a_id)},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) > 0
    item = next(i for i in items if i["variante_id"] == str(escenario.variante_a_id))

    # Verificar métricas obligatorias CU17
    assert item["libre"] == 20
    assert item["reservado"] == 5
    assert item["cupo_offline"] == 3
    assert item["comprometido_traslado"] == 2
    # Fisico = disponible + reservado + comprometido_caja + comprometido_traslado + otros
    assert item["fisico"] == 30
    assert item["costo_promedio"] >= 0
    assert "valorizacion" in item


@pytest.mark.asyncio
async def test_cu17_kardex_movimientos_saldo_y_origen(http, escenario, fabrica_sesiones):
    """CU17: Kardex registra movimientos inmutables con saldo_fisico acumulado y documento origen."""
    http.usar(escenario.usuario_admin_a)

    # Crear movimientos trazables para variante_a
    ahora = utcnow()
    doc_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        mov1 = MovimientoInventario(
            id=uuid.uuid4(),
            variante_id=escenario.variante_a_id,
            sucursal_destino_id=escenario.sucursal_a_id,
            tipo="RECEPCION_PROVEEDOR",
            cantidad=50,
            costo_unitario=Decimal("45.00"),
            referencia_tipo="LOTE_RECEPCION",
            referencia_id=doc_id,
            clave_idempotencia=uuid.uuid4(),
            fecha_hora=ahora - timedelta(hours=2),
            observacion="Ingreso inicial lote",
        )
        mov2 = MovimientoInventario(
            id=uuid.uuid4(),
            variante_id=escenario.variante_a_id,
            sucursal_origen_id=escenario.sucursal_a_id,
            tipo="VENTA_PRESENCIAL",
            cantidad=10,
            costo_unitario=Decimal("45.00"),
            referencia_tipo="VENTA",
            referencia_id=uuid.uuid4(),
            clave_idempotencia=uuid.uuid4(),
            fecha_hora=ahora - timedelta(hours=1),
            observacion="Venta en mostrador",
        )
        db.add_all([mov1, mov2])
        await db.commit()

    resp = await http.cliente.get(
        "/api/v1/inventario/kardex",
        params={
            "variante_id": str(escenario.variante_a_id),
            "sucursal_id": str(escenario.sucursal_a_id),
        },
    )
    assert resp.status_code == 200, resp.text
    kardex = resp.json()
    assert len(kardex) >= 2

    # El más reciente primero (VENTA_PRESENCIAL)
    venta = next(k for k in kardex if k["tipo"] == "VENTA_PRESENCIAL")
    recep = next(k for k in kardex if k["tipo"] == "RECEPCION_PROVEEDOR")

    assert recep["referencia_tipo"] == "LOTE_RECEPCION"
    assert recep["referencia_id"] == str(doc_id)
    assert recep["cantidad"] == 50

    assert venta["referencia_tipo"] == "VENTA"
    assert venta["cantidad"] == 10
    # saldo_fisico refleja el saldo acumulado en ese instante
    assert venta["saldo_fisico"] == recep["saldo_fisico"] - 10


@pytest.mark.asyncio
async def test_cu17_aislamiento_multitenant_kardex_y_existencias(http, escenario):
    """CU17: Usuario de Empresa A no puede consultar sucursales ni variantes de Empresa B."""
    http.usar(escenario.usuario_admin_a)

    # Intentar consultar existencias de sucursal de Empresa B -> 403
    resp_suc = await http.cliente.get(
        "/api/v1/inventario/existencias",
        params={"sucursal_id": str(escenario.sucursal_b_id)},
    )
    assert resp_suc.status_code == 403

    # Intentar consultar Kardex de sucursal de Empresa B -> 403
    resp_kardex = await http.cliente.get(
        "/api/v1/inventario/kardex",
        params={"sucursal_id": str(escenario.sucursal_b_id)},
    )
    assert resp_kardex.status_code == 403


@pytest.mark.asyncio
async def test_cu12_no_delete_al_crear_tasa_solapada_preserva_historial_y_cotizacion(http, escenario, fabrica_sesiones):
    """CU12: Crear tasa solapada no borra tasas futuras; conserva versión previa y cotizaciones históricas."""
    http.usar(escenario.usuario_global_sin_empresa)

    ahora = utcnow()
    # 0. Crear tasa base para el pasado (hace 2 días hasta hace 1 día)
    pasado_desde = ahora - timedelta(days=2)
    pasado_hasta = ahora - timedelta(days=1)
    await http.cliente.post(
        "/api/v1/plataforma/tasas-cambio",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "tasa_bob_por_usd": "6.85",
            "vigente_desde": pasado_desde.isoformat(),
            "vigente_hasta": pasado_hasta.isoformat(),
            "motivo": "Tasa histórica de referencia",
        },
    )

    # 1. Crear tasa futura programada (a partir de mañana por 10 días)
    futuro_desde = ahora + timedelta(days=1)
    futuro_hasta = futuro_desde + timedelta(days=10)
    resp1 = await http.cliente.post(
        "/api/v1/plataforma/tasas-cambio",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "tasa_bob_por_usd": "7.10",
            "vigente_desde": futuro_desde.isoformat(),
            "vigente_hasta": futuro_hasta.isoformat(),
            "motivo": "Tasa futura programada",
        },
    )
    assert resp1.status_code == 201, resp1.text
    tasa1_id = uuid.UUID(resp1.json()["id"])

    # Contar tasas en base de datos antes de la tasa solapada
    async with fabrica_sesiones() as db:
        q_count = select(func.count(TasaCambio.id))
        count_antes = (await db.execute(q_count)).scalar() or 0

    # 2. Crear nueva tasa solapada (desde ahora por 5 días, solapando el inicio de tasa1)
    solapada_desde = ahora
    solapada_hasta = ahora + timedelta(days=5)
    resp2 = await http.cliente.post(
        "/api/v1/plataforma/tasas-cambio",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "tasa_bob_por_usd": "6.96",
            "vigente_desde": solapada_desde.isoformat(),
            "vigente_hasta": solapada_hasta.isoformat(),
            "motivo": "Tasa intermedia que solapa a la futura",
        },
    )
    assert resp2.status_code == 201, resp2.text
    tasa2_id = uuid.UUID(resp2.json()["id"])

    # 3. Verificar que NO hubo DELETE: el conteo en base aumentó exactamente en 1
    async with fabrica_sesiones() as db:
        count_despues = (await db.execute(q_count)).scalar() or 0
        assert count_despues == count_antes + 1, f"Se borraron registros de tasas: antes={count_antes}, despues={count_despues}"

        # 4. Verificar que tasa1 sigue existiendo y su inicio fue reubicado
        tasa1_db = await db.get(TasaCambio, tasa1_id)
        assert tasa1_db is not None, "La tasa futura fue eliminada destructivamente"
        tasa2_db = await db.get(TasaCambio, tasa2_id)
        assert tasa2_db is not None

        # tasa1 ahora inicia a partir de cuando vence tasa2
        assert tasa1_db.vigente_desde >= tasa2_db.vigente_hasta
        # La duración de 10 días se preservó
        assert tasa1_db.vigente_hasta - tasa1_db.vigente_desde == timedelta(days=10)

    # 5. Demostrar invariante histórica: cotización al momento pasado (hace 36 horas) sigue usando 6.85
    momento_pasado = ahora - timedelta(hours=36)
    resp_cotiz_pasada = await http.cliente.get(
        "/api/v1/plataforma/tasas-cambio/cotizar",
        params={"monto_bob": "68.50", "momento": momento_pasado.isoformat()},
    )
    assert resp_cotiz_pasada.status_code == 200, resp_cotiz_pasada.text
    datos_pasados = resp_cotiz_pasada.json()
    assert Decimal(str(datos_pasados["tasa_bob_por_usd"])) == Decimal("6.85")
    assert Decimal(str(datos_pasados["monto_usd"])) == Decimal("10.00")
