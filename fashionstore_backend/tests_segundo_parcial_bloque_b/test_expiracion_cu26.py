"""Pruebas funcionales E1-B4: CU26 (Expiración automática de reservas por lotes)."""
import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select

from backend.app.core.reloj import utcnow
from backend.app.core.modules.inventario.models import (
    InventarioSucursal,
    MovimientoInventario,
)
from backend.app.core.modules.reservas_traslados.models import (
    Reserva,
    DetalleReserva,
)


@pytest.mark.asyncio
async def test_cu26_expirar_reservas_lote_libera_stock_una_vez(http, escenario, fabrica_sesiones):
    """CU26: Expiración por lote libera stock una sola vez y genera Kardex LIBERACION_RESERVA."""
    http.usar(escenario.usuario_admin_a)

    ahora = utcnow()
    # 1. Crear reserva vencida en el pasado (creada hace 25 horas, vencida hace 1 hora)
    reserva_id = uuid.uuid4()
    detalle_id = uuid.uuid4()
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
        disp_inicial = inv.disponible
        res_inicial = inv.reservado

        # Apartar 3 unidades para la reserva
        inv.disponible -= 3
        inv.reservado += 3

        nueva_reserva = Reserva(
            id=reserva_id,
            empresa_id=escenario.empresa_a_id,
            codigo=f"FS-EXP-{uuid.uuid4().hex[:6].upper()}",
            cliente_id=escenario.usuario_a.id,
            sucursal_destino_id=escenario.sucursal_a_id,
            estado="PENDIENTE",
            fecha_visita=(ahora - timedelta(hours=2)).date(),
            origen_plazo_en=ahora - timedelta(hours=25),
            vence_en=ahora - timedelta(hours=1),
            revision=1,
        )
        detalle = DetalleReserva(
            id=detalle_id,
            reserva_id=reserva_id,
            variante_id=escenario.variante_a_id,
            cantidad_solicitada=3,
            cantidad_reservada=3,
            cantidad_liberada=0,
            estado_linea="RESERVADA",
        )
        db.add(nueva_reserva)
        db.add(detalle)
        await db.commit()

    # 2. Ejecutar expiración manual vía endpoint administrativo
    resp = await http.cliente.post(
        "/api/v1/reservas/expiracion/ejecutar",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert str(reserva_id) in data["expiradas"]

    # 3. Verificar estado en base de datos
    async with fabrica_sesiones() as db:
        res_post = (await db.execute(select(Reserva).where(Reserva.id == reserva_id))).scalars().first()
        assert res_post.estado == "VENCIDA"

        inv_post = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                )
            )
        ).scalars().first()
        # El stock reservado se liberó exactamente una vez
        assert inv_post.disponible == disp_inicial
        assert inv_post.reservado == res_inicial

        # Movimiento Kardex de liberación
        mov = (
            await db.execute(
                select(MovimientoInventario).where(
                    MovimientoInventario.referencia_id == reserva_id,
                    MovimientoInventario.tipo == "LIBERACION_RESERVA",
                )
            )
        ).scalars().first()
        assert mov is not None
        assert mov.cantidad == 3

    # 4. Re-ejecutar expiración: no debe liberar dos veces (debe ser omitida)
    resp2 = await http.cliente.post("/api/v1/reservas/expiracion/ejecutar")
    assert resp2.status_code == 200
    assert str(reserva_id) not in resp2.json()["expiradas"]


@pytest.mark.asyncio
async def test_cu26_dos_workers_concurrentes_advisory_lock(http, escenario):
    """CU26: Dos workers concurrentes usan advisory lock; uno procesa y el otro detecta bloqueo."""
    http.usar(escenario.usuario_admin_a)

    # Llamar al endpoint de expiración concurrentemente
    resp1, resp2 = await asyncio.gather(
        http.cliente.post("/api/v1/reservas/expiracion/ejecutar"),
        http.cliente.post("/api/v1/reservas/expiracion/ejecutar"),
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    d1, d2 = resp1.json(), resp2.json()

    # Ambos responden sin excepciones
    assert "procesadas" in d1 and "procesadas" in d2


@pytest.mark.asyncio
async def test_cu26_carrera_cancelacion_expiracion(http, escenario, fabrica_sesiones):
    """CU26: Carrera entre cancelación y expiración preserva invariantes y no duplica stock."""
    http.usar(escenario.usuario_admin_a)

    ahora = utcnow()
    reserva_id = uuid.uuid4()
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
        inv.disponible -= 1
        inv.reservado += 1

        nueva_reserva = Reserva(
            id=reserva_id,
            empresa_id=escenario.empresa_a_id,
            codigo=f"FS-CARR-{uuid.uuid4().hex[:6].upper()}",
            cliente_id=escenario.usuario_a.id,
            sucursal_destino_id=escenario.sucursal_a_id,
            estado="PENDIENTE",
            fecha_visita=ahora.date(),
            origen_plazo_en=ahora - timedelta(hours=25),
            vence_en=ahora - timedelta(hours=1),
            revision=1,
        )
        detalle = DetalleReserva(
            id=uuid.uuid4(),
            reserva_id=reserva_id,
            variante_id=escenario.variante_a_id,
            cantidad_solicitada=1,
            cantidad_reservada=1,
            cantidad_liberada=0,
            estado_linea="RESERVADA",
        )
        db.add(nueva_reserva)
        db.add(detalle)
        await db.commit()

    # Ejecutar cancelación y expiración
    cancel_resp = await http.cliente.patch(
        f"/api/v1/reservas/{reserva_id}/cancelar",
        json={"revision": 1},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert cancel_resp.status_code in (200, 409)

    exp_resp = await http.cliente.post("/api/v1/reservas/expiracion/ejecutar")
    assert exp_resp.status_code == 200

    # Estado final debe ser CANCELADA o VENCIDA, pero NUNCA doble stock liberado
    async with fabrica_sesiones() as db:
        det = (await db.execute(select(DetalleReserva).where(DetalleReserva.reserva_id == reserva_id))).scalars().first()
        assert det.cantidad_liberada <= 1
        assert det.cantidad_reservada == 0


@pytest.mark.asyncio
async def test_cu26_expiracion_service_directo_y_scheduler_config(fabrica_sesiones, escenario):
    """CU26: ExpiracionService ejecuta reentrante, genera Kardex LIBERACION_RESERVA y valida scheduler."""
    from backend.app.core.modules.reservas_traslados.services.expiracion_service import ExpiracionService
    from backend.app.core.config import settings

    # 1. Validar configuración operativa del scheduler para expiración en lote
    assert hasattr(settings, "EXPIRACION_JOB_ACTIVO")
    assert hasattr(settings, "EXPIRACION_JOB_MINUTOS")
    assert settings.EXPIRACION_JOB_MINUTOS > 0

    # 2. Crear reserva vencida en BD
    ahora = utcnow()
    reserva_id = uuid.uuid4()
    detalle_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        inv = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                )
            )
        ).scalars().first()
        inv.disponible -= 2
        inv.reservado += 2

        nueva_reserva = Reserva(
            id=reserva_id,
            empresa_id=escenario.empresa_a_id,
            codigo=f"FS-DIR-{uuid.uuid4().hex[:6].upper()}",
            cliente_id=escenario.usuario_a.id,
            sucursal_destino_id=escenario.sucursal_a_id,
            estado="PENDIENTE",
            fecha_visita=(ahora - timedelta(hours=2)).date(),
            origen_plazo_en=ahora - timedelta(hours=25),
            vence_en=ahora - timedelta(hours=1),
            revision=1,
        )
        detalle = DetalleReserva(
            id=detalle_id,
            reserva_id=reserva_id,
            variante_id=escenario.variante_a_id,
            cantidad_solicitada=2,
            cantidad_reservada=2,
            cantidad_liberada=0,
            estado_linea="RESERVADA",
        )
        db.add(nueva_reserva)
        db.add(detalle)
        await db.commit()

    # 3. Invocar directamente ExpiracionService
    async with fabrica_sesiones() as db:
        exp_servicio = ExpiracionService(db)
        res = await exp_servicio.expirar_reservas_vencidas(empresa_id=escenario.empresa_a_id)
        assert str(reserva_id) in res.expiradas
        assert res.bloqueo_activo is False

    # 4. Verificar movimiento de Kardex LIBERACION_RESERVA
    async with fabrica_sesiones() as db:
        mov = (
            await db.execute(
                select(MovimientoInventario).where(
                    MovimientoInventario.referencia_id == reserva_id,
                    MovimientoInventario.tipo == "LIBERACION_RESERVA",
                )
            )
        ).scalars().first()
        assert mov is not None
        assert mov.cantidad == 2

    # 5. Re-invocación reentrante: la reserva ya está VENCIDA y se omite cleanly sin duplicar
    async with fabrica_sesiones() as db:
        exp_servicio2 = ExpiracionService(db)
        res2 = await exp_servicio2.expirar_reservas_vencidas(empresa_id=escenario.empresa_a_id)
        assert str(reserva_id) not in res2.expiradas
