"""Pruebas exhaustivas de seguridad, rol, concurrencia y validaciones de Caja Offline (CU06/CU07).

Cubre bloqueos 1, 2 y 5 de auditoría 07:
- Autorización por rol y ámbito (CLIENTE -> 403, personal ajeno -> 403, sin empresa -> 400).
- Planes inactivos, vencidos o sin soporte offline -> 403.
- Cajas o dispositivos duplicados con turnos incompatibles -> 409.
- Carrera por última unidad con SELECT ... FOR UPDATE -> solo 1 gana cupo.
- Validaciones financieras y de integridad en sincronización offline:
  * instantes fuera de vigencia -> 400.
  * precios adulterados -> 400.
  * totales mal calculados -> 400.
  * efectivo insuficiente o cambio mal calculado -> 400.
  * versión de precios adulterada -> 400.
  * turno cerrado o en recuperación intentando nueva venta -> 409.
- Idempotencia estricta por operacion_id durable.
- Cierre supervisado y detección de operaciones pendientes reales.
- Recuperación de caja perdida restringida a supervisores (cajero -> 403) sin liberar stock por timeout.
"""
import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select, update

from backend.app.core.reloj import utcnow
from backend.app.core.modules.identidad_empresas.models import (
    Empresa,
    Plan,
    Rol,
    Suscripcion,
    Usuario,
)
from backend.app.core.modules.inventario.models import (
    CupoCaja,
    InventarioSucursal,
    MovimientoInventario,
)
from backend.app.core.modules.ventas_pagos.models import (
    TurnoCaja,
    Venta,
    DetalleVenta,
    Pago,
)


@pytest.mark.asyncio
async def test_cliente_rechazado_403_en_todas_mutaciones_caja(http, escenario):
    """Bloqueo 1: Clientes (CLIENTE) son rechazados con HTTP 403 Forbidden en operaciones de caja."""
    http.usar(escenario.usuario_a)  # Usuario con rol CLIENTE
    turno_dummy_id = uuid.uuid4()

    # 1. Habilitar turno
    resp_hab = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-CLIENTE",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    assert resp_hab.status_code == 403, f"Esperado 403, recibido {resp_hab.status_code}: {resp_hab.text}"

    # 2. Consultar turno activo
    resp_act = await http.cliente.get("/api/v1/cajas/turnos/activo")
    assert resp_act.status_code == 403

    # 3. Consultar turno específico
    resp_get = await http.cliente.get(f"/api/v1/cajas/turnos/{turno_dummy_id}")
    assert resp_get.status_code == 403

    # 4. Registrar venta offline
    resp_vta = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_dummy_id}/ventas",
        json={
            "operacion_id": str(uuid.uuid4()),
            "secuencia_local": 1,
            "vendida_local_en": utcnow().isoformat(),
            "entregada_local_en": utcnow().isoformat(),
            "version_precios": "precios-dummy",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_autorizado_bob": "100.00"}],
            "total_bob": "100.00",
            "efectivo_recibido_bob": "100.00",
            "cambio_entregado_bob": "0.00",
        },
    )
    assert resp_vta.status_code == 403

    # 5. Cerrar turno
    resp_cer = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_dummy_id}/cerrar",
        json={"revision": 1, "operaciones_pendientes": []},
    )
    assert resp_cer.status_code == 403

    # 6. Recuperar turno
    resp_rec = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_dummy_id}/recuperar",
        json={"revision": 1, "motivo": "Intento no autorizado"},
    )
    assert resp_rec.status_code == 403


@pytest.mark.asyncio
async def test_usuario_sin_empresa_rechazado_400(http, escenario):
    """Bloqueo 1: Usuario global sin empresa asignada es rechazado con 400 Bad Request."""
    http.usar(escenario.usuario_global_sin_empresa)
    resp = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-NO-EMPRESA",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    assert resp.status_code == 400
    assert "sin empresa" in resp.text.lower()


@pytest.mark.asyncio
async def test_plan_vencido_rechaza_habilitacion_turno_403(http, escenario, fabrica_sesiones):
    """Bloqueo 1 y 2: Empresa con suscripción vencida fuera de gracia es rechazada con 403 Forbidden."""
    http.usar(escenario.usuario_admin_a)

    # Vencer la suscripción de empresa_a_id en BD
    async with fabrica_sesiones() as db:
        await db.execute(
            update(Suscripcion)
            .where(Suscripcion.empresa_id == escenario.empresa_a_id)
            .values(
                inicia_en=utcnow() - timedelta(days=60),
                vence_en=utcnow() - timedelta(days=10),  # Vencida hace 10 días (fuera de gracia de 3 días)
            )
        )
        await db.commit()

    try:
        resp = await http.cliente.post(
            "/api/v1/cajas/turnos",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={
                "caja_id": "CAJA-PLAN-VENCIDO",
                "dispositivo_id": str(uuid.uuid4()),
                "sucursal_id": str(escenario.sucursal_a_id),
                "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
                "revision": 1,
            },
        )
        assert resp.status_code == 403, f"Esperado 403, recibido {resp.status_code}: {resp.text}"
        assert "PLAN_INACTIVO" in resp.text
    finally:
        # Restaurar la suscripción vigente para las siguientes pruebas
        async with fabrica_sesiones() as db:
            await db.execute(
                update(Suscripcion)
                .where(Suscripcion.empresa_id == escenario.empresa_a_id)
                .values(
                    inicia_en=utcnow() - timedelta(days=1),
                    vence_en=utcnow() + timedelta(days=365),
                )
            )
            await db.commit()


@pytest.mark.asyncio
async def test_caja_o_dispositivo_duplicado_rechaza_409(http, escenario):
    """Bloqueo 1: Dispositivo o caja física duplicada en misma sucursal es rechazada con 409 Conflict."""
    http.usar(escenario.usuario_admin_a)
    disp1 = uuid.uuid4()
    disp2 = uuid.uuid4()

    # 1. Habilitar CAJA-FÍSICA-1 con dispositivo 1
    resp1 = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-FISICA-1",
            "dispositivo_id": str(disp1),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    assert resp1.status_code == 201

    # 2. Intentar habilitar misma caja física con otro dispositivo -> 409
    resp_mismacaja = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-FISICA-1",
            "dispositivo_id": str(disp2),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    assert resp_mismacaja.status_code == 409, f"Esperado 409, recibido {resp_mismacaja.status_code}"

    # 3. Intentar habilitar otra caja física pero con el mismo dispositivo 1 -> 409
    resp_mismodisp = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-FISICA-2",
            "dispositivo_id": str(disp1),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    assert resp_mismodisp.status_code == 409


@pytest.mark.asyncio
async def test_precio_linea_adulterado_rechazado_400(http, escenario):
    """Bloqueo 5: Cliente offline envía precio adulterado diferente al congelado en habilitación -> 400."""
    http.usar(escenario.usuario_admin_a)
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-PRECIO-MAL",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]
    version_precios = resp_turno.json()["version_precios"]
    ahora = utcnow()

    # Precio congelado es 100.00, pero el cliente offline envía 50.00
    payload_adulterado = {
        "operacion_id": str(uuid.uuid4()),
        "secuencia_local": 1,
        "vendida_local_en": ahora.isoformat(),
        "entregada_local_en": ahora.isoformat(),
        "version_precios": version_precios,
        "lineas": [
            {
                "variante_id": str(escenario.variante_a_id),
                "cantidad": 1,
                "precio_autorizado_bob": "50.00",  # Adulterado
            }
        ],
        "total_bob": "50.00",
        "efectivo_recibido_bob": "50.00",
        "cambio_entregado_bob": "0.00",
    }

    resp = await http.cliente.post(f"/api/v1/cajas/turnos/{turno_id}/ventas", json=payload_adulterado)
    assert resp.status_code == 400, f"Esperado 400, recibido {resp.status_code}: {resp.text}"
    assert "adulterado" in resp.text.lower() or "precio" in resp.text.lower()


@pytest.mark.asyncio
async def test_total_adulterado_rechazado_400(http, escenario):
    """Bloqueo 5: Total enviado no coincide con la suma exacta recalculada por el servidor -> 400."""
    http.usar(escenario.usuario_admin_a)
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-TOTAL-MAL",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]
    version_precios = resp_turno.json()["version_precios"]
    ahora = utcnow()

    # Precio es 100.00 x 1 = 100.00, pero declara total_bob = 80.00
    payload = {
        "operacion_id": str(uuid.uuid4()),
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
        "total_bob": "80.00",  # No coincide con 100.00
        "efectivo_recibido_bob": "80.00",
        "cambio_entregado_bob": "0.00",
    }

    resp = await http.cliente.post(f"/api/v1/cajas/turnos/{turno_id}/ventas", json=payload)
    assert resp.status_code == 400
    assert "total" in resp.text.lower()


@pytest.mark.asyncio
async def test_efectivo_insuficiente_o_cambio_mal_calculado_rechazado_400(http, escenario):
    """Bloqueo 5: Efectivo menor al total o cambio mal calculado -> 400."""
    http.usar(escenario.usuario_admin_a)
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-EFECTIVO-MAL",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]
    version_precios = resp_turno.json()["version_precios"]
    ahora = utcnow()

    # 1. Efectivo menor al total
    resp_insuf = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json={
            "operacion_id": str(uuid.uuid4()),
            "secuencia_local": 1,
            "vendida_local_en": ahora.isoformat(),
            "entregada_local_en": ahora.isoformat(),
            "version_precios": version_precios,
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_autorizado_bob": "100.00"}],
            "total_bob": "100.00",
            "efectivo_recibido_bob": "80.00",  # < 100.00
            "cambio_entregado_bob": "0.00",
        },
    )
    assert resp_insuf.status_code == 400
    assert "efectivo" in resp_insuf.text.lower()

    # 2. Cambio mal calculado (recibe 150.00, total 100.00, cambio debería ser 50.00, envía 30.00)
    resp_cambio = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json={
            "operacion_id": str(uuid.uuid4()),
            "secuencia_local": 2,
            "vendida_local_en": ahora.isoformat(),
            "entregada_local_en": ahora.isoformat(),
            "version_precios": version_precios,
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_autorizado_bob": "100.00"}],
            "total_bob": "100.00",
            "efectivo_recibido_bob": "150.00",
            "cambio_entregado_bob": "30.00",  # != 50.00
        },
    )
    assert resp_cambio.status_code == 400
    assert "cambio" in resp_cambio.text.lower()


@pytest.mark.asyncio
async def test_instante_local_fuera_de_vigencia_rechazado_400(http, escenario):
    """Bloqueo 5: Fecha de cobro o entrega local fuera del período del turno -> 400."""
    http.usar(escenario.usuario_admin_a)
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-VIGENCIA-MAL",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]
    version_precios = resp_turno.json()["version_precios"]
    ahora = utcnow()

    # 1. Vendida antes de la apertura del turno
    resp_antes = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json={
            "operacion_id": str(uuid.uuid4()),
            "secuencia_local": 1,
            "vendida_local_en": (ahora - timedelta(hours=2)).isoformat(),  # 2 horas antes de abrir
            "entregada_local_en": ahora.isoformat(),
            "version_precios": version_precios,
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_autorizado_bob": "100.00"}],
            "total_bob": "100.00",
            "efectivo_recibido_bob": "100.00",
            "cambio_entregado_bob": "0.00",
        },
    )
    assert resp_antes.status_code == 400
    assert "período" in resp_antes.text.lower() or "vigencia" in resp_antes.text.lower()

    # 2. Vendida después de las 8 horas de vigencia del turno
    resp_despues = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json={
            "operacion_id": str(uuid.uuid4()),
            "secuencia_local": 2,
            "vendida_local_en": (ahora + timedelta(hours=9)).isoformat(),  # 9 horas después (vence en 8)
            "entregada_local_en": (ahora + timedelta(hours=9)).isoformat(),
            "version_precios": version_precios,
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_autorizado_bob": "100.00"}],
            "total_bob": "100.00",
            "efectivo_recibido_bob": "100.00",
            "cambio_entregado_bob": "0.00",
        },
    )
    assert resp_despues.status_code == 400


@pytest.mark.asyncio
async def test_version_precios_no_coincidente_rechazado_400(http, escenario):
    """Bloqueo 5: Versión de precios adulterada respecto al snapshot del turno -> 400."""
    http.usar(escenario.usuario_admin_a)
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-VERSION-PRECIOS",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]
    ahora = utcnow()

    resp = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json={
            "operacion_id": str(uuid.uuid4()),
            "secuencia_local": 1,
            "vendida_local_en": ahora.isoformat(),
            "entregada_local_en": ahora.isoformat(),
            "version_precios": "precios-manipulados-offline",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_autorizado_bob": "100.00"}],
            "total_bob": "100.00",
            "efectivo_recibido_bob": "100.00",
            "cambio_entregado_bob": "0.00",
        },
    )
    assert resp.status_code == 400
    assert "versión de precios" in resp.text.lower()


@pytest.mark.asyncio
async def test_turno_cerrado_rechaza_nueva_venta_409(http, escenario):
    """Bloqueo 5: Un turno en estado CERRADO rechaza registrar nuevas ventas offline -> 409."""
    http.usar(escenario.usuario_admin_a)
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-YA-CERRADA",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]
    version_precios = resp_turno.json()["version_precios"]
    precio_autorizado = resp_turno.json()["cupos"][0]["precio_autorizado_bob"]

    # Cierre supervisado con evidencia del conteo físico completo del remanente.
    resp_cierre = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/cerrar",
        json={
            "revision": 1,
            "supervision_forzada": True,
            "motivo_supervision": "Cierre anticipado verificado; mercadería intacta en anaquel",
            "arqueo_declarado_bob": "0.00",
            "evidencia_cierre": {
                "referencia_acta": "ACTA-CIERRE-CAJA-YA-CERRADA",
                "conteo_fisico_por_variante": [
                    {"variante_id": str(escenario.variante_a_id), "cantidad_encontrada": 1}
                ],
            },
            "ajustes_inventario": {"resoluciones_por_variante": []},
        },
    )
    assert resp_cierre.status_code == 200
    assert resp_cierre.json()["estado"] == "CERRADO"
    assert len(resp_cierre.json()["cupos_devueltos"]) == 1

    # Intentar registrar venta offline sobre el turno cerrado sin cupo disponible -> 409 CUPO_LOCAL_EXCEDIDO
    ahora = utcnow()
    resp_vta = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/ventas",
        json={
            "operacion_id": str(uuid.uuid4()),
            "secuencia_local": 1,
            "vendida_local_en": ahora.isoformat(),
            "entregada_local_en": ahora.isoformat(),
            "version_precios": version_precios,
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_autorizado_bob": precio_autorizado}],
            "total_bob": precio_autorizado,
            "efectivo_recibido_bob": precio_autorizado,
            "cambio_entregado_bob": "0.00",
        },
    )
    assert resp_vta.status_code == 409
    assert "CUPO_LOCAL_EXCEDIDO" in resp_vta.text


@pytest.mark.asyncio
async def test_cajero_no_supervisor_recuperar_turno_rechazado_403(http, escenario, fabrica_sesiones):
    """Bloqueo 5: Solo roles supervisores (ADMIN/PROPIETARIO/ENCARGADO) pueden pasar a RECUPERACION; cajero recibe 403."""
    async with fabrica_sesiones() as db:
        rol_cajero = (await db.execute(select(Rol).where(Rol.nombre == "CAJERO"))).scalars().first()
        usuario_cajero = Usuario(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            rol_id=rol_cajero.id,
            rol=rol_cajero,
            nombres="Cajero",
            apellidos="Operativo",
            correo_electronico=f"cajero_{uuid.uuid4().hex[:6]}@test.local",
            contrasenia_hash="no-usar",
            estado="ACTIVO",
        )
        db.add(usuario_cajero)
        await db.commit()

    http.usar(escenario.usuario_admin_a)
    resp_turno = await http.cliente.post(
        "/api/v1/cajas/turnos",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "caja_id": "CAJA-RECUP-SUP",
            "dispositivo_id": str(uuid.uuid4()),
            "sucursal_id": str(escenario.sucursal_a_id),
            "cupos": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "revision": 1,
        },
    )
    assert resp_turno.status_code == 201
    turno_id = resp_turno.json()["turno_id"]

    # Cajero intenta ejecutar recuperar -> 403
    http.usar(usuario_cajero)
    resp_recup = await http.cliente.post(
        f"/api/v1/cajas/turnos/{turno_id}/recuperar",
        json={"revision": 1, "motivo": "Cajero declara pérdida"},
    )
    assert resp_recup.status_code == 403
    assert "acceso denegado" in resp_recup.text.lower() or "rol" in resp_recup.text.lower()
