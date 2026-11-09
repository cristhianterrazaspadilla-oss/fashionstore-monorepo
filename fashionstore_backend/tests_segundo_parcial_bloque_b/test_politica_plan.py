"""Pruebas para CU03/CU04/CU18: Política de capacidad del plan y suscripciones reales.

Valida:
1. Empresa con plan vigente -> puede reservar (online 201, offline ACEPTADA).
2. Empresa en periodo de gracia (3 días tras vencimiento) -> puede reservar.
3. Empresa vencida fuera de gracia (> 3 días tras vencimiento) -> bloquea reservas
   (online 403 PLAN_NO_HABILITADO, offline RECHAZADA PLAN_NO_HABILITADO durable).
4. Empresa sin suscripción -> bloquea reservas (online 403, offline RECHAZADA).
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update, delete

from backend.app.core.modules.identidad_empresas.models import (
    Empresa,
    Plan,
    Suscripcion,
    Usuario,
    Rol,
)
from backend.app.core.modules.identidad_empresas.services.plan_service import (
    PlanService,
    EstadoCapacidadPlan,
)
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.reservas_traslados.models import (
    OperacionSincronizacion,
    Reserva,
)
from backend.app.core.modules.reservas_traslados.schemas import ReservaCrearDTO, LineaReservaCrearDTO
from backend.app.core.modules.reservas_traslados.services.reserva_service import ReservaService
from backend.app.core.modules.reservas_traslados.services.sincronizacion_service import (
    SincronizacionService,
)

from .conftest import T0, RelojControlable
from .test_sincronizacion_offline import construir_operacion, stock, contar


@pytest.mark.asyncio
async def test_servicio_plan_estados_capacidad(escenario, fabrica_sesiones):
    """Verifica directamente en PlanService los cuatro estados requeridos."""
    ahora = T0
    async with fabrica_sesiones() as db:
        servicio = PlanService(db)

        # 1. Vigente (escenario por defecto tiene suscripción vigente por 365 días)
        cap_vigente = await servicio.validar_capacidad(escenario.empresa_a_id, ahora=ahora)
        assert cap_vigente.habilitado is True
        assert cap_vigente.estado_suscripcion == "VIGENTE"
        assert cap_vigente.en_gracia is False

        # 2. En gracia: vence hace 1 día (dentro de la ventana de 3 días = 72h)
        await db.execute(
            update(Suscripcion)
            .where(Suscripcion.empresa_id == escenario.empresa_a_id)
            .values(
                inicia_en=ahora - timedelta(days=30),
                vence_en=ahora - timedelta(days=1),
            )
        )
        await db.commit()

        cap_gracia = await servicio.validar_capacidad(escenario.empresa_a_id, ahora=ahora)
        assert cap_gracia.habilitado is True
        assert cap_gracia.estado_suscripcion == "EN_GRACIA"
        assert cap_gracia.en_gracia is True

        # 3. Vencida fuera de gracia: vence hace 4 días (> 3 días de gracia)
        await db.execute(
            update(Suscripcion)
            .where(Suscripcion.empresa_id == escenario.empresa_a_id)
            .values(
                inicia_en=ahora - timedelta(days=60),
                vence_en=ahora - timedelta(days=4),
            )
        )
        await db.commit()

        cap_vencida = await servicio.validar_capacidad(escenario.empresa_a_id, ahora=ahora)
        assert cap_vencida.habilitado is False
        assert cap_vencida.estado_suscripcion == "VENCIDA_FUERA_DE_GRACIA"
        assert "gracia" in cap_vencida.motivo_rechazo.lower()

        # 4. Sin suscripción: eliminamos la suscripción de la empresa B
        await db.execute(
            delete(Suscripcion).where(Suscripcion.empresa_id == escenario.empresa_b_id)
        )
        await db.commit()

        cap_sin_sub = await servicio.validar_capacidad(escenario.empresa_b_id, ahora=ahora)
        assert cap_sin_sub.habilitado is False
        assert cap_sin_sub.estado_suscripcion == "SIN_SUSCRIPCION"
        assert "suscripción" in cap_sin_sub.motivo_rechazo.lower() or "suscripcion" in cap_sin_sub.motivo_rechazo.lower()


@pytest.mark.asyncio
async def test_reserva_online_bloqueada_por_plan_vencido_fuera_de_gracia(
    escenario, fabrica_sesiones, http
):
    """Creación online bloqueada: devuelve 403 PLAN_NO_HABILITADO sin reserva ni Kardex."""
    ahora_utc = datetime.now(timezone.utc)
    async with fabrica_sesiones() as db:
        # Poner la suscripción de empresa A vencida hace 5 días
        await db.execute(
            update(Suscripcion)
            .where(Suscripcion.empresa_id == escenario.empresa_a_id)
            .values(
                inicia_en=ahora_utc - timedelta(days=35),
                vence_en=ahora_utc - timedelta(days=5),
            )
        )
        await db.commit()

        antes_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        inv_antes = await stock(db, escenario)

    http.usar(escenario.usuario_a)
    cuerpo = {
        "sucursal_destino_id": str(escenario.sucursal_a_id),
        "fecha_visita": (ahora_utc + timedelta(hours=2)).isoformat(),
        "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
    }
    respuesta = await http.cliente.post(
        "/api/v1/reservas",
        json=cuerpo,
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert respuesta.status_code == 403
    assert "PLAN_NO_HABILITADO" in respuesta.json()["detail"]

    async with fabrica_sesiones() as db:
        despues_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        inv_despues = await stock(db, escenario)

    assert despues_reservas == antes_reservas
    assert inv_despues.disponible == inv_antes.disponible
    assert inv_despues.reservado == inv_antes.reservado


@pytest.mark.asyncio
async def test_reserva_online_bloqueada_por_empresa_sin_suscripcion(
    escenario, fabrica_sesiones, http
):
    """Creación online bloqueada para empresa sin suscripción: devuelve 403."""
    async with fabrica_sesiones() as db:
        await db.execute(
            delete(Suscripcion).where(Suscripcion.empresa_id == escenario.empresa_a_id)
        )
        await db.commit()

    http.usar(escenario.usuario_a)
    ahora_utc = datetime.now(timezone.utc)
    cuerpo = {
        "sucursal_destino_id": str(escenario.sucursal_a_id),
        "fecha_visita": (ahora_utc + timedelta(hours=2)).isoformat(),
        "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
    }
    respuesta = await http.cliente.post(
        "/api/v1/reservas",
        json=cuerpo,
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert respuesta.status_code == 403
    assert "PLAN_NO_HABILITADO" in respuesta.json()["detail"]


@pytest.mark.asyncio
async def test_reserva_online_permitida_durante_gracia(
    escenario, fabrica_sesiones, http
):
    """Durante los 3 días de gracia, el servicio continúa y la reserva se crea."""
    ahora_utc = datetime.now(timezone.utc)
    async with fabrica_sesiones() as db:
        # Vence hace 2 días (dentro de los 3 días de gracia)
        await db.execute(
            update(Suscripcion)
            .where(Suscripcion.empresa_id == escenario.empresa_a_id)
            .values(
                inicia_en=ahora_utc - timedelta(days=32),
                vence_en=ahora_utc - timedelta(days=2),
            )
        )
        await db.commit()

    http.usar(escenario.usuario_a)
    cuerpo = {
        "sucursal_destino_id": str(escenario.sucursal_a_id),
        "fecha_visita": (ahora_utc + timedelta(hours=2)).isoformat(),
        "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
    }
    respuesta = await http.cliente.post(
        "/api/v1/reservas",
        json=cuerpo,
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["empresa_id"] == str(escenario.empresa_a_id)


@pytest.mark.asyncio
async def test_sincronizacion_offline_rechazada_por_plan_vencido_fuera_de_gracia(
    escenario, fabrica_sesiones
):
    """Solicitud offline con empresa fuera de gracia: persiste RECHAZADA/PLAN_NO_HABILITADO."""
    reloj = RelojControlable(T0)
    dispositivo = uuid.uuid4()

    async with fabrica_sesiones() as db:
        # Suscripción vencida hace 4 días en T0
        await db.execute(
            update(Suscripcion)
            .where(Suscripcion.empresa_id == escenario.empresa_a_id)
            .values(
                inicia_en=T0 - timedelta(days=60),
                vence_en=T0 - timedelta(days=4),
            )
        )
        await db.commit()

        servicio = SincronizacionService(db, reloj=reloj)
        referencia = await servicio.emitirReferenciaHoraria(
            escenario.usuario_a, dispositivo_id=dispositivo
        )
        antes_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        inv_antes = await stock(db, escenario)

        op = construir_operacion(
            escenario,
            referencia.referencia_horaria_id,
            dispositivo,
            creada_local=T0,
            visita=T0 + timedelta(hours=5),
            secuencia=1,
        )
        resultado = await servicio.procesarOperacion(escenario.usuario_a, op)

        assert resultado.estado == "RECHAZADA"
        assert resultado.codigo == "PLAN_NO_HABILITADO"
        assert resultado.recurso_id is None
        assert "gracia" in resultado.detalle.lower()

        # Persistencia durable: consultarOperacion devuelve el mismo resultado
        op_guardada = await servicio.consultarOperacion(escenario.usuario_a, op.operacion_id)
        assert op_guardada.estado == "RECHAZADA"
        assert op_guardada.codigo == "PLAN_NO_HABILITADO"

        # Verificar que NO se crearon reservas ni movimientos de inventario
        despues_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        inv_despues = await stock(db, escenario)

    assert despues_reservas == antes_reservas
    assert inv_despues.disponible == inv_antes.disponible
    assert inv_despues.reservado == inv_antes.reservado


@pytest.mark.asyncio
async def test_sincronizacion_offline_rechazada_por_empresa_sin_suscripcion(
    escenario, fabrica_sesiones
):
    """Solicitud offline con empresa sin suscripción: persiste RECHAZADA/PLAN_NO_HABILITADO."""
    reloj = RelojControlable(T0)
    dispositivo = uuid.uuid4()

    async with fabrica_sesiones() as db:
        await db.execute(
            delete(Suscripcion).where(Suscripcion.empresa_id == escenario.empresa_a_id)
        )
        await db.commit()

        servicio = SincronizacionService(db, reloj=reloj)
        referencia = await servicio.emitirReferenciaHoraria(
            escenario.usuario_a, dispositivo_id=dispositivo
        )

        op = construir_operacion(
            escenario,
            referencia.referencia_horaria_id,
            dispositivo,
            creada_local=T0,
            visita=T0 + timedelta(hours=5),
            secuencia=1,
        )
        resultado = await servicio.procesarOperacion(escenario.usuario_a, op)

        assert resultado.estado == "RECHAZADA"
        assert resultado.codigo == "PLAN_NO_HABILITADO"
        assert resultado.recurso_id is None
        assert "suscripción" in resultado.detalle.lower() or "suscripcion" in resultado.detalle.lower()
