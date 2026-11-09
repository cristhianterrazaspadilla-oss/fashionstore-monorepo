"""Pruebas funcionales E1-B5: CU06 (Turno y Cupos Offline) y CU07 (Venta Contado Offline y Conciliación)."""
import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select

from backend.app.core.reloj import utcnow
from backend.app.core.modules.catalogo.models import VarianteProducto
from backend.app.core.modules.inventario.models import (
    CupoCaja,
    InventarioSucursal,
    MovimientoInventario,
)
from backend.app.core.modules.identidad_empresas.models import Rol, Usuario
from backend.app.core.modules.ventas_pagos.models import (
    TurnoCaja,
    TurnoCajaEvento,
    Venta,
    DetalleVenta,
    Pago,
)


@pytest.mark.asyncio
async def test_cu06_habilitar_turno_exitoso_y_cupos_kardex(http, escenario, fabrica_sesiones):
    """CU06: Cajero habilita turno online con asignación de cupos exclusivos y separación de stock."""
    http.usar(escenario.usuario_admin_a)
    key = uuid.uuid4()
    dispositivo_id = uuid.uuid4()

    payload = {
        "caja_id": "CAJA-01",
        "dispositivo_id": str(dispositivo_id),
        "sucursal_id": str(escenario.sucursal_a_id),
        "cupos": [
            {"variante_id": str(escenario.variante_a_id), "cantidad": 2}
        ],
        "revision": 1,
    }

    # 1. Habilitación exitosa
    resp = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(key)},
        json=payload,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["caja_codigo"] == "CAJA-01"
    assert data["estado"] == "ABIERTO"
    assert data["revision"] == 1
    assert len(data["cupos"]) == 1
    assert data["cupos"][0]["otorgado"] == 2
    assert "snapshot" in data and len(data["snapshot"]["productos"]) > 0

    turno_id = uuid.UUID(data["turno_id"])

    async with fabrica_sesiones() as db:
        # 2. Verificar inventario en sucursal (disponible redujo 2, comprometido_caja subió 2)
        q_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv = (await db.execute(q_inv)).scalars().first()
        assert inv.disponible == 3  # Inicial era 5
        assert inv.comprometido_caja == 2

        # 3. Verificar CupoCaja
        q_cupo = select(CupoCaja).where(CupoCaja.turno_id == turno_id)
        cupos = (await db.execute(q_cupo)).scalars().all()
        assert len(cupos) == 1
        assert cupos[0].otorgado == 2
        assert cupos[0].consumido == 0
        assert cupos[0].liberado == 0
        assert cupos[0].costo_unitario_snapshot == Decimal("40.00")
        q_mov = select(MovimientoInventario).where(
            MovimientoInventario.referencia_tipo == "TURNO_CAJA",
            MovimientoInventario.referencia_id == turno_id,
            MovimientoInventario.tipo == "COMPROMISO_CAJA",
        )
        movs = (await db.execute(q_mov)).scalars().all()
        assert len(movs) == 1
        assert movs[0].cantidad == 2
        assert movs[0].costo_unitario == Decimal("40.00")


@pytest.mark.asyncio
async def test_cu06_habilitacion_idempotente(http, escenario, fabrica_sesiones):
    """CU06: Reintentos con Idempotency-Key devuelven la misma habilitación sin duplicar asignaciones."""
    http.usar(escenario.usuario_admin_a)
    key = uuid.uuid4()
    dispositivo_id = uuid.uuid4()

    payload = {
        "caja_id": "CAJA-02",
        "dispositivo_id": str(dispositivo_id),
        "sucursal_id": str(escenario.sucursal_a_id),
        "cupos": [
            {"variante_id": str(escenario.variante_a_id), "cantidad": 1}
        ],
        "revision": 1,
    }

    resp1 = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(key)},
        json=payload,
    )
    assert resp1.status_code == 201
    data1 = resp1.json()

    # Replay idéntico
    resp2 = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(key)},
        json=payload,
    )
    assert resp2.status_code == 201
    assert resp2.json()["turno_id"] == data1["turno_id"]

    # Replay con payload distinto -> 409
    payload_modificado = dict(payload, caja_id="CAJA-MODIFICADA")
    resp_conflicto = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(key)},
        json=payload_modificado,
    )
    assert resp_conflicto.status_code == 409

    async with fabrica_sesiones() as db:
        q_mov = select(MovimientoInventario).where(
            MovimientoInventario.referencia_tipo == "TURNO_CAJA",
            MovimientoInventario.referencia_id == uuid.UUID(data1["turno_id"]),
            MovimientoInventario.tipo == "COMPROMISO_CAJA",
        )
        assert len((await db.execute(q_mov)).scalars().all()) == 1


@pytest.mark.asyncio
async def test_cu06_cupo_insuficiente_todo_o_nada(http, escenario, fabrica_sesiones):
    """CU06: Si una variante no tiene suficiente stock libre, falla 409 y no asigna nada."""
    http.usar(escenario.usuario_admin_a)
    key = uuid.uuid4()
    dispositivo_id = uuid.uuid4()

    async with fabrica_sesiones() as db:
        q_inv_antes = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_antes = (await db.execute(q_inv_antes)).scalars().first()
        disp_inicial = inv_antes.disponible

    payload = {
        "caja_id": "CAJA-03",
        "dispositivo_id": str(dispositivo_id),
        "sucursal_id": str(escenario.sucursal_a_id),
        "cupos": [
            {"variante_id": str(escenario.variante_a_id), "cantidad": 1},
            {"variante_id": str(escenario.variante_sin_stock_id), "cantidad": 5},  # Stock 0
        ],
        "revision": 1,
    }

    resp = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(key)},
        json=payload,
    )
    assert resp.status_code == 409
    assert "CUPO_INSUFICIENTE" in resp.text

    # Verificar que no hubo asignación parcial
    async with fabrica_sesiones() as db:
        inv_despues = (await db.execute(q_inv_antes)).scalars().first()
        assert inv_despues.disponible == disp_inicial


@pytest.mark.asyncio
async def test_cu06_concurrencia_dos_cajas_ultima_unidad(http, escenario):
    """CU06: Dos cajas concurrentes intentan apartar la última unidad disponible: solo una tiene éxito."""
    http.usar(escenario.usuario_admin_a)
    disp1 = uuid.uuid4()
    disp2 = uuid.uuid4()

    payload1 = {
        "caja_id": "CAJA-CONC-1",
        "dispositivo_id": str(disp1),
        "sucursal_id": str(escenario.sucursal_a_id),
        "cupos": [{"variante_id": str(escenario.variante_ultima_id), "cantidad": 1}],
        "revision": 1,
    }
    payload2 = {
        "caja_id": "CAJA-CONC-2",
        "dispositivo_id": str(disp2),
        "sucursal_id": str(escenario.sucursal_a_id),
        "cupos": [{"variante_id": str(escenario.variante_ultima_id), "cantidad": 1}],
        "revision": 1,
    }

    res1, res2 = await asyncio.gather(
        http.cliente.post("/api/v1/cajas/turnos", headers={"Idempotency-Key": str(uuid.uuid4())}, json=payload1),
        http.cliente.post("/api/v1/cajas/turnos", headers={"Idempotency-Key": str(uuid.uuid4())}, json=payload2),
    )

    statuses = [res1.status_code, res2.status_code]
    assert 201 in statuses, f"Ninguna caja obtuvo cupo: {statuses}"
    assert 409 in statuses, f"Ambas cajas obtuvieron cupo indebidamente: {statuses}"


@pytest.mark.asyncio
async def test_cu06_dispositivo_con_turno_abierto_rechaza_segundo(http, escenario):
    """CU06: Un dispositivo con turno ABIERTO no puede habilitar un segundo turno."""
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    payload = {
        "caja_id": "CAJA-DUPLICADA",
        "dispositivo_id": str(disp_id),
        "sucursal_id": str(escenario.sucursal_a_id),
        "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        "revision": 1,
    }

    resp1 = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=payload,
    )
    assert resp1.status_code == 201

    # Intento de habilitar otro turno con el mismo dispositivo
    resp2 = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=payload,
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_cu06_consultar_turno_activo(http, escenario):
    """CU06: Consultar turno activo por dispositivo."""
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    payload = {
        "caja_id": "CAJA-ACTIVA",
        "dispositivo_id": str(disp_id),
        "sucursal_id": str(escenario.sucursal_a_id),
        "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        "revision": 1,
    }

    resp = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=payload,
    )
    assert resp.status_code == 201
    turno_id = resp.json()["turno_id"]

    resp_activo = await http.cliente.get(
        "/api/v1/cajas/turnos/activo",
        params={"dispositivo_id": str(disp_id)},
    )
    assert resp_activo.status_code == 200
    data_activo = resp_activo.json()
    assert data_activo is not None
    assert data_activo["turno_id"] == turno_id
    assert data_activo["estado"] == "ABIERTO"


@pytest.mark.asyncio
async def test_cu07_sincronizar_venta_offline_efectivo(http, escenario, fabrica_sesiones):
    """CU07: Sincronizar venta offline al contado, descontando cupo local y emitiendo Kardex sin doble descuento."""
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    # 1. Habilitar turno con cupo de 2
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-VTA",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]

    # 2. Registrar venta offline en efectivo
    operacion_id = uuid.uuid4()
    ahora = utcnow()
    payload_venta = {
        "operacion_id": str(operacion_id),
        "secuencia_local": 1,
        "vendida_local_en": ahora.isoformat(),
        "entregada_local_en": ahora.isoformat(),
        "version_precios": resp_turno.json()["version_precios"],
        "lineas": [
            {
                "variante_id": str(escenario.variante_a_id),
                "cantidad": 1,
                "precio_autorizado_bob": "100.00",
            }
        ],
        "total_bob": "100.00",
        "efectivo_recibido_bob": "100.00",
        "cambio_entregado_bob": "0.00",
    }

    resp_vta = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json=payload_venta,
    )
    assert resp_vta.status_code == 201, resp_vta.text
    data_vta = resp_vta.json()
    assert data_vta["resultado"] == "REGISTRADA_CENTRAL"
    assert data_vta["operacion_id"] == str(operacion_id)
    assert Decimal(str(data_vta["total_bob"])) == Decimal("100.00")

    async with fabrica_sesiones() as db:
        # 3. Verificar persistencia de Venta, DetalleVenta y Pago
        q_venta = select(Venta).where(Venta.id == operacion_id)
        venta_db = (await db.execute(q_venta)).scalars().first()
        assert venta_db is not None
        assert venta_db.canal == "PRESENCIAL"
        assert venta_db.estado == "PAGADA"
        assert venta_db.turno_caja_id == uuid.UUID(turno_id)

        q_pago = select(Pago).where(Pago.venta_id == operacion_id)
        pago_db = (await db.execute(q_pago)).scalars().first()
        assert pago_db is not None
        assert pago_db.metodo == "EFECTIVO"
        assert pago_db.monto == Decimal("100.00")

        # 4. Verificar CupoCaja (consumido incrementó a 1)
        q_cupo = select(CupoCaja).where(
            CupoCaja.turno_id == uuid.UUID(turno_id),
            CupoCaja.variante_id == escenario.variante_a_id,
        )
        cupo_db = (await db.execute(q_cupo)).scalars().first()
        assert cupo_db.consumido == 1

        # 5. Verificar Kardex: VENTA_PRESENCIAL
        q_mov = select(MovimientoInventario).where(
            MovimientoInventario.referencia_id == operacion_id,
            MovimientoInventario.tipo == "VENTA_PRESENCIAL",
        )
        mov_db = (await db.execute(q_mov)).scalars().first()
        assert mov_db is not None
        assert mov_db.cantidad == 1


@pytest.mark.asyncio
async def test_cu07_venta_offline_idempotencia_durable(http, escenario):
    """CU07: Reintento con el mismo operacion_id es completamente idempotente."""
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-IDEMP",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    turno_id = resp_turno.json()["turno_id"]
    operacion_id = uuid.uuid4()
    ahora = utcnow()

    payload_venta = {
        "operacion_id": str(operacion_id),
        "secuencia_local": 1,
        "vendida_local_en": ahora.isoformat(),
        "entregada_local_en": ahora.isoformat(),
        "version_precios": resp_turno.json()["version_precios"],
        "lineas": [
            {
                "variante_id": str(escenario.variante_a_id),
                "cantidad": 1,
                "precio_autorizado_bob": "100.00",
            }
        ],
        "total_bob": "100.00",
        "efectivo_recibido_bob": "100.00",
        "cambio_entregado_bob": "0.00",
    }

    resp1 = await http.cliente.post(f"/api/v1/cajas/turnos/{turno_id}/ventas", json=payload_venta)
    assert resp1.status_code == 201

    # Replay
    resp2 = await http.cliente.post(f"/api/v1/cajas/turnos/{turno_id}/ventas", json=payload_venta)
    assert resp2.status_code in (200, 201)
    assert resp2.json()["operacion_id"] == str(operacion_id)


@pytest.mark.asyncio
async def test_cu07_cupo_local_excedido(http, escenario):
    """CU07: Intentar registrar una venta offline excediendo el cupo disponible en caja -> 409."""
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-EXCEDIDA",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    turno_id = resp_turno.json()["turno_id"]

    # Venta pidiendo 5 unidades cuando solo se autorizó 1
    payload_excedido = {
        "operacion_id": str(uuid.uuid4()),
        "secuencia_local": 1,
        "vendida_local_en": utcnow().isoformat(),
        "entregada_local_en": utcnow().isoformat(),
        "version_precios": resp_turno.json()["version_precios"],
        "lineas": [
            {
                "variante_id": str(escenario.variante_a_id),
                "cantidad": 5,
                "precio_autorizado_bob": "100.00",
            }
        ],
        "total_bob": "500.00",
        "efectivo_recibido_bob": "500.00",
        "cambio_entregado_bob": "0.00",
    }

    resp = await http.cliente.post(f"/api/v1/cajas/turnos/{turno_id}/ventas", json=payload_excedido)
    assert resp.status_code == 409
    assert "CUPO_LOCAL_EXCEDIDO" in resp.text


@pytest.mark.asyncio
async def test_cu06_cu07_cierre_turno_y_devolucion_cupos(http, escenario, fabrica_sesiones):
    """CU06/CU07: Cierre de turno supervisado: devuelve cupos sobrantes a disponible."""
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    # Habilitar turno con cupo de 2
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-CIERRE",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    turno_id = resp_turno.json()["turno_id"]

    # 1. Vender 1 unidad
    await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json={
            "operacion_id": str(uuid.uuid4()),
            "secuencia_local": 1,
            "vendida_local_en": utcnow().isoformat(),
            "entregada_local_en": utcnow().isoformat(),
            "version_precios": resp_turno.json()["version_precios"],
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_autorizado_bob": "100.00",
                }
            ],
            "total_bob": "100.00",
            "efectivo_recibido_bob": "100.00",
            "cambio_entregado_bob": "0.00",
        },
    )

    # 2. Intento de cerrar con operaciones pendientes -> pasa a CONCILIACION
    resp_pend = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "operaciones_pendientes": [str(uuid.uuid4())],
        },
    )
    assert resp_pend.status_code == 200
    assert resp_pend.json()["estado"] == "CONCILIACION"

    # 3. El cierre ordinario conserva el remanente en CONCILIACION.
    resp_cerrar = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 2,
            "operaciones_pendientes": [],
            "ultima_secuencia_local": 1,
            "total_operaciones_locales": 1,
            "arqueo_efectivo_bob": "100.00",
        },
    )
    assert resp_cerrar.status_code == 200
    data_cerrar = resp_cerrar.json()
    assert data_cerrar["estado"] == "CONCILIACION"
    assert data_cerrar["cerrado_en"] is None
    assert data_cerrar["cupos_devueltos"] == []
    assert data_cerrar["cupos_retenidos"][0]["retenido"] == 1

    resp_cierre_supervisado = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": data_cerrar["revision"],
            "supervision_forzada": True,
            "motivo_supervision": "Conteo fisico completo de remanente de caja",
            "operaciones_pendientes": [],
            "ultima_secuencia_local": 1,
            "total_operaciones_locales": 1,
            "arqueo_declarado_bob": "100.00",
            "evidencia_cierre": {
                "referencia_acta": "ACTA-CIERRE-CU06-01",
                "conteo_fisico_por_variante": [
                    {"variante_id": str(escenario.variante_a_id), "cantidad_encontrada": 1}
                ],
            },
            "ajustes_inventario": {"resoluciones_por_variante": []},
        },
    )
    assert resp_cierre_supervisado.status_code == 200, resp_cierre_supervisado.text
    data_cerrar = resp_cierre_supervisado.json()
    assert data_cerrar["estado"] == "CERRADO"
    assert len(data_cerrar["cupos_devueltos"]) == 1
    assert data_cerrar["cupos_devueltos"][0]["devuelto"] == 1  # 2 otorgados - 1 vendido = 1 devuelto

    async with fabrica_sesiones() as db:
        # 4. Verificar que el cupo fue liberado en CupoCaja
        q_cupo = select(CupoCaja).where(
            CupoCaja.turno_id == uuid.UUID(turno_id),
            CupoCaja.variante_id == escenario.variante_a_id,
        )
        cupo_db = (await db.execute(q_cupo)).scalars().first()
        assert cupo_db.liberado == 1
        assert cupo_db.consumido == 1
        assert cupo_db.otorgado == 2


@pytest.mark.asyncio
async def test_cu06_recuperar_turno_perdido(http, escenario):
    """CU06: Caja perdida o dañada se pasa a RECUPERACION congelando cupos para resolución manual."""
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-RECUP",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    turno_id = resp_turno.json()["turno_id"]

    resp_recup = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/recuperar",
        json={
            "revision": 1,
            "motivo": "Fallo de hardware irreversible en tablet de caja",
            "evidencia": "Pantalla rota sin posibilidad de arranque",
        },
    )
    assert resp_recup.status_code == 200
    assert resp_recup.json()["estado"] == "RECUPERACION"



@pytest.mark.asyncio
async def test_cu07_cierre_adverso_venta_local_no_enviada_discrepancia_bloqueo4(http, escenario, fabrica_sesiones):
    """Bloqueo 4: Caso adverso: venta local cobrada no enviada, cliente manda operaciones_pendientes = []
    con secuencia local 1: el backend detecta discrepancia, pone CONCILIACION, NO libera cupos."""
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    # 1. Habilitar turno con cupo de 3 unidades
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-ADVERSA",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 3}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]

    # 2. El dispositivo cobró localmente la venta #1 pero NO la envió al servidor (conteo_central = 0).
    # El dispositivo intenta cerrar enviando operaciones_pendientes = [] y ultima_secuencia_local = 1.
    resp_cerrar = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "operaciones_pendientes": [],
            "ultima_secuencia_local": 1,
        },
    )
    assert resp_cerrar.status_code == 200
    data = resp_cerrar.json()
    assert data["estado"] == "CONCILIACION"
    assert data["cupos_devueltos"] == []
    assert data["revision"] == 2

    # 3. Verificar en base de datos que los cupos NO se liberaron
    async with fabrica_sesiones() as db:
        q_cupo = select(CupoCaja).where(
            CupoCaja.turno_id == uuid.UUID(turno_id),
            CupoCaja.variante_id == escenario.variante_a_id,
        )
        cupo_db = (await db.execute(q_cupo)).scalars().first()
        assert cupo_db.liberado == 0
        assert cupo_db.consumido == 0
        assert cupo_db.otorgado == 3

        q_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_db = (await db.execute(q_inv)).scalars().first()
        assert inv_db.comprometido_caja >= 3


@pytest.mark.asyncio
async def test_cu07_reenvio_reconciliacion_y_cierre_limpio(http, escenario, fabrica_sesiones):
    """Bloqueo 4: Reenvío y reconciliación: la venta local pendiente se sincroniza con éxito
    en estado CONCILIACION con su operacion_id original; el turno se cierra posteriormente a CERRADO
    liberando sólo los cupos no consumidos."""
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    # 1. Habilitar turno con cupo de 3
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-RECONCILIAR",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 3}],
            "revision": 1,
        },
    )
    turno_id = resp_turno.json()["turno_id"]
    version_precios = resp_turno.json()["version_precios"]

    # 2. El turno pasa a CONCILIACION porque faltaba la venta #1
    resp_cierre_fallido = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "operaciones_pendientes": [],
            "ultima_secuencia_local": 1,
        },
    )
    assert resp_cierre_fallido.json()["estado"] == "CONCILIACION"
    assert resp_cierre_fallido.json()["revision"] == 2

    # 3. La venta pendiente se sincroniza exitosamente mientras el turno está en CONCILIACION
    operacion_id = uuid.uuid4()
    ahora = utcnow()
    payload_venta = {
        "operacion_id": str(operacion_id),
        "secuencia_local": 1,
        "vendida_local_en": ahora.isoformat(),
        "entregada_local_en": ahora.isoformat(),
        "version_precios": version_precios,
        "lineas": [
            {
                "variante_id": str(escenario.variante_a_id),
                "cantidad": 2,
                "precio_autorizado_bob": "100.00",
            }
        ],
        "total_bob": "200.00",
        "efectivo_recibido_bob": "200.00",
        "cambio_entregado_bob": "0.00",
    }
    resp_venta = await http.cliente.post(f"/api/v1/cajas/turnos/{turno_id}/ventas", json=payload_venta)
    assert resp_venta.status_code == 201
    assert resp_venta.json()["resultado"] == "REGISTRADA_CENTRAL"

    # Verificar idempotencia: replay de la misma venta devuelve el mismo resultado sin duplicar
    resp_replay = await http.cliente.post(f"/api/v1/cajas/turnos/{turno_id}/ventas", json=payload_venta)
    assert resp_replay.status_code in (200, 201)
    assert resp_replay.json()["operacion_id"] == str(operacion_id)

    # 4. Verificar exactamente 1 Venta, 1 DetalleVenta, 1 Pago y 1 MovimientoInventario
    async with fabrica_sesiones() as db:
        q_v = select(Venta).where(Venta.id == operacion_id)
        ventas_db = (await db.execute(q_v)).scalars().all()
        assert len(ventas_db) == 1

        q_det = select(DetalleVenta).where(DetalleVenta.venta_id == operacion_id)
        dets_db = (await db.execute(q_det)).scalars().all()
        assert len(dets_db) == 1
        assert dets_db[0].cantidad == 2

        q_pago = select(Pago).where(Pago.venta_id == operacion_id)
        pagos_db = (await db.execute(q_pago)).scalars().all()
        assert len(pagos_db) == 1
        assert pagos_db[0].monto == Decimal("200.00")

        q_mov = select(MovimientoInventario).where(
            MovimientoInventario.referencia_id == operacion_id,
            MovimientoInventario.tipo == "VENTA_PRESENCIAL",
        )
        movs_db = (await db.execute(q_mov)).scalars().all()
        assert len(movs_db) == 1
        assert movs_db[0].cantidad == 2

    # 5. Posterior llamado a cerrar_turno ahora encuentra todas las operaciones conciliadas
    resp_cierre_ok = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 2,
            "operaciones_pendientes": [],
            "ultima_secuencia_local": 1,
            "total_operaciones_locales": 1,
            "arqueo_efectivo_bob": "200.00",
        },
    )
    assert resp_cierre_ok.status_code == 200
    data_cierre = resp_cierre_ok.json()
    assert data_cierre["estado"] == "CONCILIACION"
    assert data_cierre["cerrado_en"] is None
    assert data_cierre["cupos_devueltos"] == []
    assert data_cierre["cupos_retenidos"][0]["retenido"] == 1

    resp_cierre_supervisado = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": data_cierre["revision"],
            "supervision_forzada": True,
            "motivo_supervision": "Conteo final posterior a sincronizar ventas offline",
            "arqueo_declarado_bob": "200.00",
            "evidencia_cierre": {
                "referencia_acta": "ACTA-CIERRE-RECONCILIADO",
                "conteo_fisico_por_variante": [
                    {"variante_id": str(escenario.variante_a_id), "cantidad_encontrada": 1}
                ],
            },
            "ajustes_inventario": {"resoluciones_por_variante": []},
        },
    )
    assert resp_cierre_supervisado.status_code == 200, resp_cierre_supervisado.text
    data_cierre = resp_cierre_supervisado.json()
    assert data_cierre["estado"] == "CERRADO"
    assert data_cierre["cupos_devueltos"][0]["devuelto"] == 1
    assert data_cierre["cupos_devueltos"][0]["consumido"] == 2


@pytest.mark.asyncio
async def test_cu07_cierre_supervision_forzada_permisos_y_motivo(http, escenario, fabrica_sesiones):
    """Bloqueo 4: Control de permisos supervisores vs cajeros en caso de caja perdida / cierre forzado."""
    # Crear usuario con rol CAJERO
    async with fabrica_sesiones() as db:
        rol_cajero = (await db.execute(select(Rol).where(Rol.nombre == "CAJERO"))).scalars().first()
        usuario_cajero = Usuario(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            rol_id=rol_cajero.id,
            rol=rol_cajero,
            nombres="Cajero",
            apellidos="Supervisado",
            correo_electronico=f"cajero_sup_{uuid.uuid4().hex[:6]}@test.local",
            contrasenia_hash="no-usar",
            estado="ACTIVO",
        )
        db.add(usuario_cajero)
        await db.commit()

    http.usar(usuario_cajero)
    disp_id = uuid.uuid4()

    # Habilitar turno asignado al cajero
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-FORZADA",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]

    # 1. Cajero intenta forzar supervisión -> 403 Forbidden
    resp_cajero_forzar = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "supervision_forzada": True,
            "motivo_supervision": "Cajero intenta forzar cierre",
        },
    )
    assert resp_cajero_forzar.status_code == 403
    assert "solo un supervisor" in resp_cajero_forzar.text.lower()

    # 2. Supervisor intenta forzar supervisión sin motivo -> 400 Bad Request
    http.usar(escenario.usuario_admin_a)
    resp_admin_sin_motivo = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "supervision_forzada": True,
            "motivo_supervision": "",
        },
    )
    assert resp_admin_sin_motivo.status_code == 400
    assert "10 caracteres" in resp_admin_sin_motivo.text.lower()

    # 3. Supervisor ejecuta cierre forzado con descarte explícito -> CERRADO exitoso liberando cupos
    resp_admin_forzado = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "supervision_forzada": True,
            "arqueo_declarado_bob": "0.00",
            "evidencia_cierre": {
                "referencia_acta": "ACTA-FISICA-2",
                "conteo_fisico_por_variante": [
                    {"variante_id": str(escenario.variante_a_id), "cantidad_encontrada": 2}
                ],
            },
            "ajustes_inventario": {"resoluciones_por_variante": []},
            "motivo_supervision": "Dispositivo con daño de hardware catastrófico; arqueo físico manual completado",
        },
    )
    assert resp_admin_forzado.status_code == 200
    data_forzado = resp_admin_forzado.json()
    assert data_forzado["estado"] == "CERRADO"
    assert len(data_forzado["cupos_devueltos"]) == 1
    assert data_forzado["cupos_devueltos"][0]["devuelto"] == 2
    assert data_forzado["cerrado_por_id"] == str(escenario.usuario_admin_a.id)
    assert data_forzado["motivo_supervision"] == "Dispositivo con daño de hardware catastrófico; arqueo físico manual completado"
    assert data_forzado["supervision_forzada"] is True
    assert data_forzado["cupos_devueltos"][0]["mermado"] == 0

    async with fabrica_sesiones() as db:
        cupo = (await db.execute(select(CupoCaja).where(CupoCaja.turno_id == uuid.UUID(turno_id)))).scalars().first()
        assert cupo.liberado == 2
        assert cupo.mermado == 0
        movimientos = (await db.execute(select(MovimientoInventario).where(
            MovimientoInventario.referencia_tipo == "TURNO_CAJA_EVENTO",
            MovimientoInventario.referencia_id == uuid.UUID(data_forzado["evento_id"]),
            MovimientoInventario.tipo == "LIBERACION_CUPO_CAJA",
        ))).scalars().all()
        assert len(movimientos) == 1


@pytest.mark.asyncio
async def test_cu07_cierre_adverso_0_0_vacio_pasa_a_conciliacion_con_cupos_retenidos(http, escenario, fabrica_sesiones):
    """Bloqueo CU06/CU07 (Punto 1):
    Una caja con cupos asignados que intenta cerrar declarando 0, 0, [] (omitiendo ventas locales
    o ante incertidumbre sin ventas centrales) NO debe cerrar directamente ni liberar inventario;
    el turno pasa a CONCILIACION y los cupos permanecen retenidos.
    """
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    # 1. Habilitar turno con cupo de 3 unidades
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-ADVERSA-00",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 3}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]

    # 2. Cliente envía conteos 0, 0, [] intentando cerrar sin evidencia verificable central
    resp_cerrar = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "ultima_secuencia_local": 0,
            "total_operaciones_locales": 0,
            "operaciones_pendientes": [],
        },
    )
    assert resp_cerrar.status_code == 200
    data_cerrar = resp_cerrar.json()
    assert data_cerrar["estado"] == "CONCILIACION"
    assert data_cerrar["cupos_devueltos"] == []
    assert len(data_cerrar["cupos_retenidos"]) == 1
    assert data_cerrar["cupos_retenidos"][0]["retenido"] == 3
    assert data_cerrar["cupos_retenidos"][0]["otorgado"] == 3
    assert data_cerrar["cupos_retenidos"][0]["consumido"] == 0

    # 3. Verificar en BD que los cupos siguen retenidos en comprometido_caja y liberado=0
    async with fabrica_sesiones() as db:
        q_cupo = select(CupoCaja).where(
            CupoCaja.turno_id == uuid.UUID(turno_id),
            CupoCaja.variante_id == escenario.variante_a_id,
        )
        cupo_db = (await db.execute(q_cupo)).scalars().first()
        assert cupo_db.liberado == 0
        assert cupo_db.consumido == 0
        assert cupo_db.otorgado == 3

        q_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_db = (await db.execute(q_inv)).scalars().first()
        assert inv_db.comprometido_caja >= 3


@pytest.mark.asyncio
async def test_cu07_cierre_supervisado_forzado_persistencia_durable_y_retencion_cupos(http, escenario, fabrica_sesiones):
    """Bloqueo CU06/CU07 (Punto 2):
    En cierre forzado por supervisor, los campos durablemente auditables (cerrado_por_id, motivo_supervision,
    supervision_forzada, arqueo_declarado_bob, evidencia_cierre, ajustes_inventario) se persisten.
    Los faltantes marcados PENDIENTE_SINCRONIZACION permanecen retenidos en comprometido_caja.
    """
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-FORZADA-RETENIDA",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]

    motivo = "Cierre supervisado con faltante pendiente de sincronizacion"
    evidencia = {
        "referencia_acta": "ACT-2026-99",
        "conteo_fisico_por_variante": [
            {"variante_id": str(escenario.variante_a_id), "cantidad_encontrada": 0}
        ],
    }
    ajustes = {
        "resoluciones_por_variante": [
            {
                "variante_id": str(escenario.variante_a_id),
                "resolucion": "PENDIENTE_SINCRONIZACION",
                "motivo": "Venta offline pendiente de sincronizar",
            }
        ]
    }

    resp_cierre = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "supervision_forzada": True,
            "motivo_supervision": motivo,
            "arqueo_declarado_bob": "350.50",
            "evidencia_cierre": evidencia,
            "ajustes_inventario": ajustes,
        },
    )
    assert resp_cierre.status_code == 200, resp_cierre.text
    data = resp_cierre.json()
    assert data["estado"] == "CONCILIACION"
    assert data["cerrado_en"] is None
    assert data["cupos_devueltos"] == []
    assert len(data["cupos_retenidos"]) == 1
    assert data["cupos_retenidos"][0]["retenido"] == 2
    assert data["cerrado_por_id"] == str(escenario.usuario_admin_a.id)
    assert data["motivo_supervision"] == motivo
    assert data["supervision_forzada"] is True
    assert Decimal(str(data["arqueo_declarado_bob"])) == Decimal("350.50")
    assert data["evidencia_cierre"] == evidencia
    assert data["ajustes_inventario"]["resoluciones_por_variante"] == ajustes["resoluciones_por_variante"]

    # Verificar en BD que los datos están durables en comercial.turnos_caja
    async with fabrica_sesiones() as db:
        q_t = select(TurnoCaja).where(TurnoCaja.id == uuid.UUID(turno_id))
        t_db = (await db.execute(q_t)).scalars().first()
        assert t_db.estado == "CONCILIACION"
        assert t_db.cerrado_en is None
        assert t_db.cerrado_por_id == escenario.usuario_admin_a.id
        assert t_db.motivo_supervision == motivo
        assert t_db.supervision_forzada is True
        assert t_db.arqueo_declarado_bob == Decimal("350.50")
        assert t_db.evidencia_cierre == evidencia
        assert t_db.ajustes_inventario["resoluciones_por_variante"] == ajustes["resoluciones_por_variante"]
        assert t_db.ajustes_inventario["mermas"] == []

        # Cupos siguen en comprometido_caja (no se liberaron a disponible)
        q_cupo = select(CupoCaja).where(
            CupoCaja.turno_id == uuid.UUID(turno_id),
            CupoCaja.variante_id == escenario.variante_a_id,
        )
        cupo_db = (await db.execute(q_cupo)).scalars().first()
        assert cupo_db.liberado == 0
        assert cupo_db.mermado == 0
        assert cupo_db.otorgado == 2

        q_inv = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_db = (await db.execute(q_inv)).scalars().first()
        assert inv_db.comprometido_caja >= 2


@pytest.mark.asyncio
async def test_cu07_recepcion_tardia_venta_offline_post_cierre_supervisado_e_idempotencia(http, escenario, fabrica_sesiones):
    """Bloqueo CU06/CU07 (Punto 2 y 4):
    Una venta offline válida efectuada durante la vigencia del turno que llega tarde, tras el cierre
    supervisado forzado (con cupos retenidos), debe ser aceptada exactamente una vez y registrar
    Venta, DetalleVenta, Pago y Kardex VENTA_PRESENCIAL sin duplicar.
    El reintento con el mismo operacion_id debe retornar el resultado existente idéntico.
    """
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-TARDIA",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]
    version_precios = resp_turno.json()["version_precios"]

    # Cerrar con supervisión forzada y retención de cupos (descarte_venta_fisica=False)
    # El supervisor retiene todos los cupos hasta que llegue la venta offline tardia.
    resp_cierre = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "supervision_forzada": True,
            "motivo_supervision": "Caja offline; faltante queda pendiente de sincronizacion",
            "arqueo_declarado_bob": "0.00",
            "evidencia_cierre": {
                "referencia_acta": "ACTA-VENTA-TARDIA",
                "conteo_fisico_por_variante": [
                    {"variante_id": str(escenario.variante_a_id), "cantidad_encontrada": 0}
                ],
            },
            "ajustes_inventario": {
                "resoluciones_por_variante": [
                    {
                        "variante_id": str(escenario.variante_a_id),
                        "resolucion": "PENDIENTE_SINCRONIZACION",
                        "motivo": "Esperando recepcion de ventas del dispositivo",
                    }
                ]
            },
        },
    )
    assert resp_cierre.status_code == 200, resp_cierre.text
    assert resp_cierre.json()["estado"] == "CONCILIACION"
    assert resp_cierre.json()["cerrado_en"] is None
    assert resp_cierre.json()["cupos_devueltos"] == []

    # Verificar estado del inventario antes de la llegada tardía
    async with fabrica_sesiones() as db:
        q_inv_prev = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_prev = (await db.execute(q_inv_prev)).scalars().first()
        comprometido_prev = inv_prev.comprometido_caja

    # Llega la venta offline tardía efectuada dentro de la vigencia del turno
    operacion_id = uuid.uuid4()
    ahora = utcnow()
    payload_venta = {
        "operacion_id": str(operacion_id),
        "secuencia_local": 1,
        "vendida_local_en": ahora.isoformat(),
        "entregada_local_en": ahora.isoformat(),
        "version_precios": version_precios,
        "lineas": [
            {
                "variante_id": str(escenario.variante_a_id),
                "cantidad": 1,
                "precio_autorizado_bob": "100.00",
            }
        ],
        "total_bob": "100.00",
        "efectivo_recibido_bob": "100.00",
        "cambio_entregado_bob": "0.00",
    }

    resp_vta = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json=payload_venta,
    )
    assert resp_vta.status_code == 201
    data_vta = resp_vta.json()
    assert data_vta["resultado"] == "REGISTRADA_CENTRAL"
    assert data_vta["operacion_id"] == str(operacion_id)
    venta_id = data_vta["venta_id"]

    # Verificar en BD que se creó exactamente 1 Venta, 1 DetalleVenta, 1 Pago y 1 MovimientoInventario
    async with fabrica_sesiones() as db:
        q_v = select(Venta).where(Venta.id == uuid.UUID(venta_id))
        venta_db = (await db.execute(q_v)).scalars().first()
        assert venta_db is not None
        assert venta_db.estado == "PAGADA"
        assert venta_db.canal == "PRESENCIAL"
        assert venta_db.total == Decimal("100.00")

        q_det = select(DetalleVenta).where(DetalleVenta.venta_id == uuid.UUID(venta_id))
        dets = (await db.execute(q_det)).scalars().all()
        assert len(dets) == 1
        assert dets[0].cantidad == 1

        q_pago = select(Pago).where(Pago.venta_id == uuid.UUID(venta_id))
        pagos = (await db.execute(q_pago)).scalars().all()
        assert len(pagos) == 1
        assert pagos[0].metodo == "EFECTIVO"
        assert pagos[0].estado == "APROBADO"
        assert pagos[0].monto == Decimal("100.00")

        q_kardex = select(MovimientoInventario).where(
            MovimientoInventario.referencia_id == uuid.UUID(venta_id),
            MovimientoInventario.tipo == "VENTA_PRESENCIAL",
        )
        movs = (await db.execute(q_kardex)).scalars().all()
        assert len(movs) == 1
        assert movs[0].cantidad == 1

        # comprometido_caja disminuyó en 1
        q_inv_post = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_post = (await db.execute(q_inv_post)).scalars().first()
        assert inv_post.comprometido_caja == comprometido_prev - 1

    # REINTENTO IDEMPOTENTE: reenviar exactamente el mismo payload
    resp_reintento = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json=payload_venta,
    )
    assert resp_reintento.status_code in (200, 201)
    data_reintento = resp_reintento.json()
    assert data_reintento["resultado"] == "REGISTRADA_CENTRAL"
    assert data_reintento["operacion_id"] == str(operacion_id)
    assert data_reintento["venta_id"] == venta_id

    # Confirmar que sigue habiendo exactamente 1 Venta, 1 Detalle, 1 Pago y 1 MovimientoInventario
    async with fabrica_sesiones() as db:
        q_v_count = select(Venta).where(Venta.id == uuid.UUID(venta_id))
        assert len((await db.execute(q_v_count)).scalars().all()) == 1

        q_pago_count = select(Pago).where(Pago.venta_id == uuid.UUID(venta_id))
        assert len((await db.execute(q_pago_count)).scalars().all()) == 1

        q_kardex_count = select(MovimientoInventario).where(
            MovimientoInventario.referencia_id == uuid.UUID(venta_id),
            MovimientoInventario.tipo == "VENTA_PRESENCIAL",
        )
        assert len((await db.execute(q_kardex_count)).scalars().all()) == 1


    # Al sincronizar la venta, el supervisor libera solo el remanente contado.
    resp_cierre_final = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 2,
            "supervision_forzada": True,
            "motivo_supervision": "Venta recibida; conteo final de remanente",
            "arqueo_declarado_bob": "100.00",
            "operaciones_pendientes": [],
            "ultima_secuencia_local": 1,
            "total_operaciones_locales": 1,
            "evidencia_cierre": {
                "referencia_acta": "ACTA-FINAL-VENTA-TARDIA",
                "conteo_fisico_por_variante": [
                    {"variante_id": str(escenario.variante_a_id), "cantidad_encontrada": 1}
                ],
            },
            "ajustes_inventario": {"resoluciones_por_variante": []},
        },
    )
    assert resp_cierre_final.status_code == 200, resp_cierre_final.text
    cierre_final = resp_cierre_final.json()
    assert cierre_final["estado"] == "CERRADO"
    assert cierre_final["cupos_devueltos"][0]["devuelto"] == 1
    assert cierre_final["cupos_retenidos"] == []


@pytest.mark.asyncio
async def test_cu07_cierre_supervisado_bloquea_ventas_pendientes_no_sincronizadas(http, escenario, fabrica_sesiones):
    http.usar(escenario.usuario_admin_a)
    turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-PENDIENTE-SUPERVISION",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    assert turno.status_code == 201, turno.text
    turno_id = uuid.UUID(turno.json()["turno_id"])
    operacion_pendiente = uuid.uuid4()

    respuesta = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "supervision_forzada": True,
            "motivo_supervision": "Esperar sincronizacion de ventas declaradas",
            "arqueo_declarado_bob": "0.00",
            "operaciones_pendientes": [str(operacion_pendiente)],
            "evidencia_cierre": {
                "referencia_acta": "ACTA-PENDIENTE-SYNC",
                "conteo_fisico_por_variante": [
                    {"variante_id": str(escenario.variante_a_id), "cantidad_encontrada": 2}
                ],
            },
            "ajustes_inventario": {"resoluciones_por_variante": []},
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    data = respuesta.json()
    assert data["estado"] == "CONCILIACION"
    assert data["cerrado_en"] is None
    assert data["cupos_devueltos"] == []
    assert data["cupos_retenidos"][0]["retenido"] == 2

    async with fabrica_sesiones() as db:
        cupo = (await db.execute(select(CupoCaja).where(CupoCaja.turno_id == turno_id))).scalars().first()
        assert cupo.liberado == 0
        assert cupo.mermado == 0
        assert cupo.consumido == 0
        turno_db = (await db.execute(select(TurnoCaja).where(TurnoCaja.id == turno_id))).scalars().first()
        assert turno_db.estado == "CONCILIACION"
        assert turno_db.cerrado_en is None
        evento = (await db.execute(select(TurnoCajaEvento).where(
            TurnoCajaEvento.id == uuid.UUID(data["evento_id"])
        ))).scalars().first()
        assert evento is not None
        assert str(operacion_pendiente) in evento.datos["operaciones_pendientes_no_sincronizadas"]


@pytest.mark.asyncio
async def test_cu07_cierre_supervisado_rechaza_evidencia_incompleta_sin_mutar_cupos(http, escenario, fabrica_sesiones):
    http.usar(escenario.usuario_admin_a)
    turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-EVIDENCIA-INCOMPLETA",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    assert turno.status_code == 201, turno.text
    turno_id = uuid.UUID(turno.json()["turno_id"])

    respuesta = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "supervision_forzada": True,
            "motivo_supervision": "Conteo de caja requiere evidencia verificable",
            "arqueo_declarado_bob": "0.00",
            "evidencia_cierre": {
                "referencia_acta": "ACTA-INCOMPLETA",
                "conteo_fisico_por_variante": [],
            },
            "ajustes_inventario": {"resoluciones_por_variante": []},
        },
    )
    assert respuesta.status_code == 400

    async with fabrica_sesiones() as db:
        turno_db = (await db.execute(select(TurnoCaja).where(TurnoCaja.id == turno_id))).scalars().first()
        cupo = (await db.execute(select(CupoCaja).where(CupoCaja.turno_id == turno_id))).scalars().first()
        assert turno_db.estado == "ABIERTO"
        assert turno_db.revision == 1
        assert cupo.liberado == 0
        assert cupo.mermado == 0


@pytest.mark.asyncio
async def test_cu07_merma_supervisada_no_reincorpora_stock_y_kardex_es_auditable(http, escenario, fabrica_sesiones):
    http.usar(escenario.usuario_admin_a)
    async with fabrica_sesiones() as db:
        inv_inicial = (await db.execute(select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        ))).scalars().first()
        disponible_inicial = inv_inicial.disponible

    turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-MERMA-SUPERVISADA",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 3}],
            "revision": 1,
        },
    )
    assert turno.status_code == 201, turno.text
    turno_id = uuid.UUID(turno.json()["turno_id"])
    motivo = "Dos unidades faltantes verificadas en conteo fisico"

    # La caja conserva el costo vigente cuando se asignó el cupo aunque cambie
    # el costo promedio de catálogo antes de la conciliación.
    async with fabrica_sesiones() as db:
        cupo = (await db.execute(select(CupoCaja).where(CupoCaja.turno_id == turno_id))).scalars().first()
        variante = (await db.execute(select(VarianteProducto).where(
            VarianteProducto.id == escenario.variante_a_id
        ))).scalars().first()
        assert cupo.costo_unitario_snapshot == Decimal("40.00")
        variante.costo_promedio = Decimal("99.99")
        await db.commit()

    respuesta = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "supervision_forzada": True,
            "motivo_supervision": "Merma confirmada por responsable de sucursal",
            "arqueo_declarado_bob": "0.00",
            "evidencia_cierre": {
                "referencia_acta": "ACTA-MERMA-1",
                "conteo_fisico_por_variante": [
                    {"variante_id": str(escenario.variante_a_id), "cantidad_encontrada": 1}
                ],
            },
            "ajustes_inventario": {
                "resoluciones_por_variante": [
                    {
                        "variante_id": str(escenario.variante_a_id),
                        "resolucion": "MERMA",
                        "motivo": motivo,
                    }
                ]
            },
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    data = respuesta.json()
    assert data["estado"] == "CERRADO"
    assert data["cupos_devueltos"][0]["devuelto"] == 1
    assert data["cupos_devueltos"][0]["mermado"] == 2
    assert data["cupos_retenidos"] == []

    async with fabrica_sesiones() as db:
        cupo = (await db.execute(select(CupoCaja).where(CupoCaja.turno_id == turno_id))).scalars().first()
        assert cupo.liberado == 1
        assert cupo.mermado == 2
        assert cupo.consumido == 0

        inventario = (await db.execute(select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        ))).scalars().first()
        assert inventario.disponible == disponible_inicial - 2
        assert inventario.comprometido_caja == 0

        movimientos = (await db.execute(select(MovimientoInventario).where(
            MovimientoInventario.referencia_tipo == "TURNO_CAJA_EVENTO",
            MovimientoInventario.referencia_id == uuid.UUID(data["evento_id"]),
        ))).scalars().all()
        liberaciones = [m for m in movimientos if m.tipo == "LIBERACION_CUPO_CAJA"]
        mermas = [m for m in movimientos if m.tipo == "MERMA"]
        assert len(liberaciones) == 1 and liberaciones[0].cantidad == 1
        assert len(mermas) == 1 and mermas[0].cantidad == 2
        assert liberaciones[0].costo_unitario == Decimal("40.00")
        assert mermas[0].costo_unitario == Decimal("40.00")
        assert mermas[0].responsable_id == escenario.usuario_admin_a.id
        assert motivo in mermas[0].observacion


@pytest.mark.asyncio
async def test_cu07_cierre_concurrente_idempotente_libera_una_sola_vez(http, escenario, fabrica_sesiones):
    http.usar(escenario.usuario_admin_a)
    turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-CIERRE-CONCURRENTE",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    assert turno.status_code == 201, turno.text
    turno_id = uuid.UUID(turno.json()["turno_id"])
    payload = {
        "revision": 1,
        "supervision_forzada": True,
        "motivo_supervision": "Conteo concurrente con clave de revision",
        "arqueo_declarado_bob": "0.00",
        "evidencia_cierre": {
            "referencia_acta": "ACTA-CONCURRENTE",
            "conteo_fisico_por_variante": [
                {"variante_id": str(escenario.variante_a_id), "cantidad_encontrada": 1}
            ],
        },
        "ajustes_inventario": {"resoluciones_por_variante": []},
    }
    url = f"/api/v1/cajas/turnos/{turno_id}/cerrar"
    respuestas = await asyncio.gather(http.cliente.post(url, json=payload), http.cliente.post(url, json=payload))
    assert sorted(r.status_code for r in respuestas) == [200, 409]

    async with fabrica_sesiones() as db:
        cupo = (await db.execute(select(CupoCaja).where(CupoCaja.turno_id == turno_id))).scalars().first()
        assert cupo.liberado == 1
        movs = (await db.execute(select(MovimientoInventario).where(
            MovimientoInventario.referencia_tipo == "TURNO_CAJA_EVENTO",
            MovimientoInventario.tipo == "LIBERACION_CUPO_CAJA",
            MovimientoInventario.linea_referencia_id == cupo.id,
        ))).scalars().all()
        assert len(movs) == 1


@pytest.mark.asyncio
async def test_cu07_recepcion_tardia_venta_offline_post_recuperacion(http, escenario, fabrica_sesiones):
    """Bloqueo CU06/CU07 (Punto 4):
    Una venta offline válida efectuada en turno que pasó a RECUPERACION (caja perdida/dañada)
    se sincroniza exitosamente consumiendo del cupo congelado sin duplicar Kardex.
    """
    http.usar(escenario.usuario_admin_a)
    disp_id = uuid.uuid4()

    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-RECUP-TARDIA",
            "dispositivo_id": str(disp_id),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]
    version_precios = resp_turno.json()["version_precios"]

    # Pasar a RECUPERACION por supervisor
    resp_recup = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/recuperar",
        json={
            "revision": 1,
            "motivo": "Dispositivo extraviado durante traslado",
            "evidencia": "denuncia policial #1234",
        },
    )
    assert resp_recup.status_code == 200
    assert resp_recup.json()["estado"] == "RECUPERACION"

    # Se recupera el dispositivo y se transmiten las ventas offline válidas
    operacion_id = uuid.uuid4()
    ahora = utcnow()
    resp_vta = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json={
            "operacion_id": str(operacion_id),
            "secuencia_local": 1,
            "vendida_local_en": ahora.isoformat(),
            "entregada_local_en": ahora.isoformat(),
            "version_precios": version_precios,
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_autorizado_bob": "100.00",
                }
            ],
            "total_bob": "100.00",
            "efectivo_recibido_bob": "100.00",
            "cambio_entregado_bob": "0.00",
        },
    )
    assert resp_vta.status_code == 201
    assert resp_vta.json()["resultado"] == "REGISTRADA_CENTRAL"
    venta_id = resp_vta.json()["venta_id"]

    async with fabrica_sesiones() as db:
        q_v = select(Venta).where(Venta.id == uuid.UUID(venta_id))
        v_db = (await db.execute(q_v)).scalars().first()
        assert v_db is not None
        assert v_db.canal == "PRESENCIAL"
        assert v_db.estado == "PAGADA"
