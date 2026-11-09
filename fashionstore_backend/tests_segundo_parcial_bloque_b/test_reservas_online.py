"""CU18: reserva online con origen 24 h, visita validada y apartado atómico."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.reservas_traslados.models import DetalleReserva, Reserva
from backend.app.core.modules.reservas_traslados.schemas import (
    LineaReservaCrearDTO,
    ReservaCrearDTO,
)
from backend.app.core.modules.reservas_traslados.services.reserva_service import ReservaService
from backend.app.core.modules.ventas_pagos.schemas import AdelantoCrearDTO
from backend.app.core.modules.ventas_pagos.services.pago_service import PagoService

from .conftest import T0, RelojControlable


def dto_reserva(escenario, cantidad=1, visita=None, variante=None):
    return ReservaCrearDTO(
        sucursal_destino_id=escenario.sucursal_a_id,
        fecha_visita=visita if visita is not None else T0 + timedelta(hours=2),
        observacion="Prueba online",
        lineas=[
            LineaReservaCrearDTO(
                variante_id=variante or escenario.variante_a_id,
                cantidad=cantidad,
            )
        ],
    )


async def contar(db, modelo, **filtros):
    consulta = select(func.count()).select_from(modelo)
    for campo, valor in filtros.items():
        consulta = consulta.where(getattr(modelo, campo) == valor)
    return int((await db.execute(consulta)).scalar() or 0)


@pytest.mark.asyncio
async def test_creacion_online_vence_24h_y_visita_no_mueve_origen(
    escenario, fabrica_sesiones
):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = ReservaService(db, reloj=reloj)
        reserva, creada = await servicio.crear(
            escenario.usuario_a, dto_reserva(escenario, cantidad=2), uuid.uuid4()
        )

    assert creada is True
    assert reserva.empresa_id == escenario.empresa_a_id
    assert reserva.origen_plazo_en == T0
    assert reserva.vence_en == T0 + timedelta(hours=24)
    assert reserva.fecha_visita == T0 + timedelta(hours=2)
    assert reserva.detalles[0].cantidad_reservada == 2

    async with fabrica_sesiones() as db:
        movimientos = (
            await db.execute(
                select(MovimientoInventario).where(
                    MovimientoInventario.referencia_id == reserva.id,
                    MovimientoInventario.tipo == "RESERVA",
                )
            )
        ).scalars().all()
    assert len(movimientos) == 1
    assert movimientos[0].cantidad == 2


@pytest.mark.asyncio
async def test_visita_invalida_retorna_422_sin_reserva_ni_kardex(
    escenario, fabrica_sesiones
):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = ReservaService(db, reloj=reloj)
        antes_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        antes_movimientos = await contar(db, MovimientoInventario, variante_id=escenario.variante_a_id)

        for visita in (T0 - timedelta(hours=1), T0 + timedelta(hours=25)):
            with pytest.raises(HTTPException) as error:
                await servicio.crear(
                    escenario.usuario_a,
                    dto_reserva(escenario, visita=visita),
                    uuid.uuid4(),
                )
            assert error.value.status_code == 422

        despues_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        despues_movimientos = await contar(db, MovimientoInventario, variante_id=escenario.variante_a_id)
        inventario = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                )
            )
        ).scalars().first()

    assert despues_reservas == antes_reservas
    assert despues_movimientos == antes_movimientos
    assert inventario.disponible == 5
    assert inventario.reservado == 0


@pytest.mark.asyncio
async def test_lineas_duplicadas_retorna_400(escenario, fabrica_sesiones):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = ReservaService(db, reloj=reloj)
        dto = ReservaCrearDTO(
            sucursal_destino_id=escenario.sucursal_a_id,
            fecha_visita=T0 + timedelta(hours=1),
            lineas=[
                LineaReservaCrearDTO(variante_id=escenario.variante_a_id, cantidad=1),
                LineaReservaCrearDTO(variante_id=escenario.variante_a_id, cantidad=1),
            ],
        )
        with pytest.raises(HTTPException) as error:
            await servicio.crear(escenario.usuario_a, dto, uuid.uuid4())
        assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_idempotencia_y_conflicto_de_payload(escenario, fabrica_sesiones):
    reloj = RelojControlable(T0)
    clave = uuid.uuid4()
    async with fabrica_sesiones() as db:
        servicio = ReservaService(db, reloj=reloj)
        original, creada = await servicio.crear(
            escenario.usuario_a, dto_reserva(escenario), clave
        )
        repetida, creada_repetida = await servicio.crear(
            escenario.usuario_a, dto_reserva(escenario), clave
        )
        with pytest.raises(HTTPException) as error:
            await servicio.crear(
                escenario.usuario_a, dto_reserva(escenario, cantidad=3), clave
            )
        assert error.value.status_code == 409

    assert creada is True
    assert creada_repetida is False
    assert repetida.id == original.id


@pytest.mark.asyncio
async def test_aislamiento_por_empresa_y_sesion_sin_empresa(escenario, fabrica_sesiones):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = ReservaService(db, reloj=reloj)
        reserva, _ = await servicio.crear(
            escenario.usuario_a, dto_reserva(escenario), uuid.uuid4()
        )
        with pytest.raises(HTTPException) as error:
            await servicio.obtener(escenario.usuario_b, reserva.id)
        assert error.value.status_code == 404

        for llamada in (
            lambda: servicio.crear(escenario.usuario_global_sin_empresa, dto_reserva(escenario), uuid.uuid4()),
            lambda: servicio.obtener(escenario.usuario_global_sin_empresa, reserva.id),
            lambda: servicio.listar(escenario.usuario_global_sin_empresa),
        ):
            with pytest.raises(HTTPException) as error:
                await llamada()
            assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_adelanto_oportuno_fija_origen_mas_72h_y_tardio_rechaza(
    escenario, fabrica_sesiones
):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = ReservaService(db, reloj=reloj)
        reserva, _ = await servicio.crear(
            escenario.usuario_a, dto_reserva(escenario), uuid.uuid4()
        )

        reloj.avanzar(timedelta(hours=10))
        pago_service = PagoService(db, reloj=reloj)
        pago, _ = await pago_service.registrarAdelanto(
            escenario.usuario_a,
            AdelantoCrearDTO(reserva_id=reserva.id, metodo="EFECTIVO"),
            uuid.uuid4(),
        )
        assert pago.monto == Decimal("50.00")
        actual = await servicio.obtener(escenario.usuario_a, reserva.id)
        assert actual.vence_en == T0 + timedelta(hours=72)

        reloj.fijar(T0 + timedelta(hours=73))
        with pytest.raises(HTTPException) as error:
            await pago_service.registrarAdelanto(
                escenario.usuario_a,
                AdelantoCrearDTO(reserva_id=reserva.id, metodo="EFECTIVO"),
                uuid.uuid4(),
            )
        assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_dos_operaciones_compiten_por_ultima_unidad(escenario, fabrica_sesiones):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = ReservaService(db, reloj=reloj)
        primera, _ = await servicio.crear(
            escenario.usuario_a,
            dto_reserva(escenario, variante=escenario.variante_ultima_id),
            uuid.uuid4(),
        )
        assert primera.detalles[0].cantidad_reservada == 1

        with pytest.raises(HTTPException) as error:
            await servicio.crear(
                escenario.usuario_a,
                dto_reserva(escenario, variante=escenario.variante_ultima_id),
                uuid.uuid4(),
            )
        assert error.value.status_code == 409

        inventario = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                    InventarioSucursal.variante_id == escenario.variante_ultima_id,
                )
            )
        ).scalars().first()
    assert inventario.disponible == 0
    assert inventario.reservado == 1


@pytest.mark.asyncio
async def test_reserva_multilinea_revierte_todo_si_una_linea_falla(
    escenario, fabrica_sesiones
):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = ReservaService(db, reloj=reloj)
        antes_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        dto = ReservaCrearDTO(
            sucursal_destino_id=escenario.sucursal_a_id,
            fecha_visita=T0 + timedelta(hours=1),
            lineas=[
                LineaReservaCrearDTO(variante_id=escenario.variante_a_id, cantidad=2),
                LineaReservaCrearDTO(variante_id=escenario.variante_sin_stock_id, cantidad=1),
            ],
        )
        with pytest.raises(HTTPException) as error:
            await servicio.crear(escenario.usuario_a, dto, uuid.uuid4())
        assert error.value.status_code == 409

        fila_ok = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                )
            )
        ).scalars().first()
        despues_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        detalles = await contar(
            db, DetalleReserva, reserva_id=uuid.uuid4()
        )  # consulta inocua para mantener la sesión activa

    assert fila_ok.disponible == 5
    assert fila_ok.reservado == 0
    assert despues_reservas == antes_reservas
    assert detalles == 0
