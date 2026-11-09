"""CU04/C34: sincronización offline, tiempos, visita, idempotencia y concurrencia."""
import asyncio
import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.reservas_traslados.models import (
    OperacionSincronizacion,
    Reserva,
)
from backend.app.core.modules.reservas_traslados.schemas_sincronizacion import (
    OperacionDTO,
    OperacionDatosReservaDTO,
    OperacionLineaDTO,
)
from backend.app.core.modules.reservas_traslados.services.sincronizacion_service import (
    SincronizacionService,
)

from .conftest import T0, RelojControlable


def construir_operacion(
    escenario,
    referencia_id,
    dispositivo_id,
    operacion_id=None,
    creada_local=None,
    visita=None,
    cantidad=1,
    variante=None,
    secuencia=1,
):
    creada = creada_local or T0
    return OperacionDTO(
        version_esquema=1,
        operacion_id=operacion_id or uuid.uuid4(),
        tipo="SOLICITAR_RESERVA",
        creada_local_en=creada,
        empresa_id=escenario.empresa_a_id,
        usuario_id=escenario.usuario_a.id,
        dispositivo_id=dispositivo_id,
        secuencia_local=secuencia,
        referencia_horaria_id=referencia_id,
        datos=OperacionDatosReservaDTO(
            sucursal_id=escenario.sucursal_a_id,
            visita_en=visita or (creada + timedelta(hours=6)),
            lineas=[
                OperacionLineaDTO(
                    variante_id=variante or escenario.variante_a_id,
                    cantidad=cantidad,
                )
            ],
        ),
    )


async def contar(db, modelo, **filtros):
    consulta = select(func.count()).select_from(modelo)
    for campo, valor in filtros.items():
        consulta = consulta.where(getattr(modelo, campo) == valor)
    return int((await db.execute(consulta)).scalar() or 0)


async def stock(db, escenario, variante_id=None):
    variante_final = variante_id if variante_id is not None else escenario.variante_a_id
    fila = (
        await db.execute(
            select(InventarioSucursal).where(
                InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                InventarioSucursal.variante_id == variante_final,
            )
        )
    ).scalars().first()
    return fila


@pytest.fixture
def dispositivo():
    return uuid.uuid4()


@pytest.mark.asyncio
async def test_c34_tolerancia_ventana_y_vencimiento_24h(
    escenario, fabrica_sesiones, dispositivo
):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = SincronizacionService(db, reloj=reloj)
        referencia = await servicio.emitirReferenciaHoraria(
            escenario.usuario_a, dispositivo_id=dispositivo
        )
        assert referencia.vence_en == T0 + timedelta(hours=8)

        # Creada 3 min antes de la emisión: tolerancia de 5 min.
        reloj.fijar(T0 + timedelta(hours=2))
        aceptada = await servicio.procesarOperacion(
            escenario.usuario_a,
            construir_operacion(
                escenario,
                referencia.referencia_horaria_id,
                dispositivo,
                creada_local=T0 - timedelta(minutes=3),
                secuencia=1,
            ),
        )
        assert aceptada.estado == "ACEPTADA"
        assert aceptada.codigo == "OK"
        assert aceptada.vence_en == T0 - timedelta(minutes=3) + timedelta(hours=24)

        # Creada 1 h después del vence de la referencia (8 h + 5 min de gracia).
        fuera = await servicio.procesarOperacion(
            escenario.usuario_a,
            construir_operacion(
                escenario,
                referencia.referencia_horaria_id,
                dispositivo,
                creada_local=T0 + timedelta(hours=9),
                secuencia=2,
            ),
        )
        assert fuera.estado == "CONFLICTO"
        assert fuera.codigo == "TIEMPO_INCOHERENTE"
        assert fuera.recurso_id is None

        # Creada dentro de la ventana, pero sincronizada 25 h después: vencida.
        reloj.fijar(T0 + timedelta(hours=26))
        vencida = await servicio.procesarOperacion(
            escenario.usuario_a,
            construir_operacion(
                escenario,
                referencia.referencia_horaria_id,
                dispositivo,
                creada_local=T0 + timedelta(hours=1),
                secuencia=3,
            ),
        )
        assert vencida.estado == "RECHAZADA"
        assert vencida.codigo == "SOLICITUD_VENCIDA"
        assert vencida.recurso_id is None

        inventario = await stock(db, escenario)
        movimientos = (
            await db.execute(
                select(MovimientoInventario).where(
                    MovimientoInventario.referencia_id == aceptada.recurso_id,
                    MovimientoInventario.tipo == "RESERVA",
                )
            )
        ).scalars().all()
        total_movimientos = await contar(
            db,
            MovimientoInventario,
            referencia_id=aceptada.recurso_id,
        )

    # Solo la primera aceptación apartó una unidad; las otras no tocaron stock.
    assert inventario.disponible == 4
    assert inventario.reservado == 1
    assert len(movimientos) == 1
    assert movimientos[0].cantidad == 1
    assert total_movimientos == 1


@pytest.mark.asyncio
async def test_visita_invalida_es_conflicto_durable_sin_stock(
    escenario, fabrica_sesiones, dispositivo
):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = SincronizacionService(db, reloj=reloj)
        referencia = await servicio.emitirReferenciaHoraria(
            escenario.usuario_a, dispositivo_id=dispositivo
        )
        reloj.fijar(T0 + timedelta(hours=2))
        antes_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)

        for indice, visita in enumerate(
            (T0 - timedelta(minutes=1), T0 + timedelta(hours=25)), start=1
        ):
            resultado = await servicio.procesarOperacion(
                escenario.usuario_a,
                construir_operacion(
                    escenario,
                    referencia.referencia_horaria_id,
                    dispositivo,
                    creada_local=T0,
                    visita=visita,
                    secuencia=10 + indice,
                ),
            )
            assert resultado.estado == "CONFLICTO"
            assert resultado.codigo == "TIEMPO_INCOHERENTE"
            assert resultado.recurso_id is None

        despues_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        inventario = await stock(db, escenario)

    assert despues_reservas == antes_reservas
    assert inventario.disponible == 5
    assert inventario.reservado == 0


@pytest.mark.asyncio
async def test_lineas_duplicadas_retorna_400(escenario, fabrica_sesiones, dispositivo):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = SincronizacionService(db, reloj=reloj)
        referencia = await servicio.emitirReferenciaHoraria(
            escenario.usuario_a, dispositivo_id=dispositivo
        )
        operacion = construir_operacion(
            escenario, referencia.referencia_horaria_id, dispositivo
        )
        operacion.datos.lineas.append(
            OperacionLineaDTO(variante_id=escenario.variante_a_id, cantidad=1)
        )
        with pytest.raises(HTTPException) as error:
            await servicio.procesarOperacion(escenario.usuario_a, operacion)
        assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_reintento_idempotente_y_operacion_modificada(
    escenario, fabrica_sesiones, dispositivo
):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = SincronizacionService(db, reloj=reloj)
        referencia = await servicio.emitirReferenciaHoraria(
            escenario.usuario_a, dispositivo_id=dispositivo
        )
        operacion = construir_operacion(
            escenario, referencia.referencia_horaria_id, dispositivo
        )
        primera = await servicio.procesarOperacion(escenario.usuario_a, operacion)
        repetida = await servicio.procesarOperacion(escenario.usuario_a, operacion)
        assert primera.estado == repetida.estado == "ACEPTADA"
        assert primera.recurso_id == repetida.recurso_id

        alterada = operacion.model_copy(deep=True)
        alterada.datos.lineas[0].cantidad = 2
        with pytest.raises(HTTPException) as error:
            await servicio.procesarOperacion(escenario.usuario_a, alterada)
        assert error.value.status_code == 409
        assert error.value.detail["codigo"] == "OPERACION_MODIFICADA"

        operaciones = await contar(
            db,
            OperacionSincronizacion,
            empresa_id=escenario.empresa_a_id,
            operacion_id=operacion.operacion_id,
        )
        reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
    assert operaciones == 1
    assert reservas == 1


@pytest.mark.asyncio
async def test_consulta_por_uuid_exige_empresa_y_actor(
    escenario, fabrica_sesiones, dispositivo
):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = SincronizacionService(db, reloj=reloj)
        referencia = await servicio.emitirReferenciaHoraria(
            escenario.usuario_a, dispositivo_id=dispositivo
        )
        operacion = construir_operacion(
            escenario, referencia.referencia_horaria_id, dispositivo
        )
        await servicio.procesarOperacion(escenario.usuario_a, operacion)

        consulta = await servicio.consultarOperacion(
            escenario.usuario_a, operacion.operacion_id
        )
        assert consulta.recurso_id is not None

        with pytest.raises(HTTPException) as ajena:
            await servicio.consultarOperacion(escenario.usuario_b, operacion.operacion_id)
        assert ajena.value.status_code == 404

        with pytest.raises(HTTPException) as sin_empresa:
            await servicio.consultarOperacion(
                escenario.usuario_global_sin_empresa, operacion.operacion_id
            )
        assert sin_empresa.value.status_code == 400


@pytest.mark.asyncio
async def test_dto_exige_visita_y_solo_version_1(escenario):
    datos = {
        "version_esquema": 1,
        "operacion_id": uuid.uuid4(),
        "tipo": "SOLICITAR_RESERVA",
        "creada_local_en": T0,
        "empresa_id": escenario.empresa_a_id,
        "usuario_id": escenario.usuario_a.id,
        "dispositivo_id": uuid.uuid4(),
        "secuencia_local": 1,
        "datos": {
            "sucursal_id": escenario.sucursal_a_id,
            "lineas": [
                {"variante_id": escenario.variante_a_id, "cantidad": 1}
            ],
        },
    }
    with pytest.raises(ValidationError):
        OperacionDTO(**datos)

    # version_esquema es obligatorio en el contrato: no se asume por defecto.
    sin_version = {clave: valor for clave, valor in datos.items() if clave != "version_esquema"}
    sin_version["datos"] = {
        **datos["datos"],
        "visita_en": T0 + timedelta(hours=1),
    }
    with pytest.raises(ValidationError):
        OperacionDTO(**sin_version)

    datos["datos"]["visita_en"] = T0 + timedelta(hours=1)
    datos["version_esquema"] = 2
    with pytest.raises(ValidationError):
        OperacionDTO(**datos)


@pytest.mark.asyncio
async def test_concurrencia_mismo_operacion_id_devuelve_un_solo_resultado(
    escenario, fabrica_sesiones, dispositivo
):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = SincronizacionService(db, reloj=reloj)
        referencia = await servicio.emitirReferenciaHoraria(
            escenario.usuario_a, dispositivo_id=dispositivo
        )
    operacion = construir_operacion(
        escenario, referencia.referencia_horaria_id, dispositivo
    )

    async with fabrica_sesiones() as db1, fabrica_sesiones() as db2:
        servicio1 = SincronizacionService(db1, reloj=reloj)
        servicio2 = SincronizacionService(db2, reloj=reloj)
        resultados = await asyncio.gather(
            servicio1.procesarOperacion(escenario.usuario_a, operacion),
            servicio2.procesarOperacion(escenario.usuario_a, operacion),
            return_exceptions=True,
        )

    assert all(not isinstance(r, Exception) for r in resultados), resultados
    assert resultados[0].estado == resultados[1].estado == "ACEPTADA"
    assert resultados[0].recurso_id == resultados[1].recurso_id

    async with fabrica_sesiones() as db:
        operaciones = await contar(
            db,
            OperacionSincronizacion,
            empresa_id=escenario.empresa_a_id,
            operacion_id=operacion.operacion_id,
        )
        reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        inventario = await stock(db, escenario)
    assert operaciones == 1
    assert reservas == 1
    assert inventario.disponible == 4
    assert inventario.reservado == 1


@pytest.mark.asyncio
async def test_dos_operaciones_distintas_compiten_por_ultima_unidad(
    escenario, fabrica_sesiones, dispositivo
):
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = SincronizacionService(db, reloj=reloj)
        referencia = await servicio.emitirReferenciaHoraria(
            escenario.usuario_a, dispositivo_id=dispositivo
        )
    operacion_a = construir_operacion(
        escenario,
        referencia.referencia_horaria_id,
        dispositivo,
        variante=escenario.variante_ultima_id,
        secuencia=1,
    )
    operacion_b = construir_operacion(
        escenario,
        referencia.referencia_horaria_id,
        dispositivo,
        variante=escenario.variante_ultima_id,
        secuencia=2,
    )

    async with fabrica_sesiones() as db1, fabrica_sesiones() as db2:
        servicio1 = SincronizacionService(db1, reloj=reloj)
        servicio2 = SincronizacionService(db2, reloj=reloj)
        resultados = await asyncio.gather(
            servicio1.procesarOperacion(escenario.usuario_a, operacion_a),
            servicio2.procesarOperacion(escenario.usuario_a, operacion_b),
            return_exceptions=True,
        )

    assert all(not isinstance(r, Exception) for r in resultados), resultados
    aceptadas = [r for r in resultados if r.estado == "ACEPTADA"]
    rechazadas = [r for r in resultados if r.estado == "RECHAZADA"]
    assert len(aceptadas) == 1
    assert len(rechazadas) == 1
    assert rechazadas[0].codigo == "SIN_STOCK"

    async with fabrica_sesiones() as db:
        inventario = await stock(db, escenario, escenario.variante_ultima_id)
    assert inventario.disponible == 0
    assert inventario.reservado == 1


@pytest.mark.asyncio
async def test_visita_pasada_al_sincronizar_creada_t0_visita_t1_sync_t2_se_rechaza_sin_inventario(
    escenario, fabrica_sesiones, dispositivo
):
    """Requisito 2: creada en T0, visita en T0+1h y sincronizada en T0+2h se rechaza sin afectar inventario.

    También comprueba que una visita futura válida al sincronizar (visita en T0+5h a las T0+2h) se acepta.
    """
    reloj = RelojControlable(T0)
    async with fabrica_sesiones() as db:
        servicio = SincronizacionService(db, reloj=reloj)
        referencia = await servicio.emitirReferenciaHoraria(
            escenario.usuario_a, dispositivo_id=dispositivo
        )
        antes_reservas = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)

        # Servidor recibe en T0 + 2 horas
        reloj.fijar(T0 + timedelta(hours=2))

        # 1. Creada en T0, visita en T0 + 1h (ya pasó a las T0+2h de recepción)
        op_rechazada = construir_operacion(
            escenario,
            referencia.referencia_horaria_id,
            dispositivo,
            creada_local=T0,
            visita=T0 + timedelta(hours=1),
            secuencia=1,
        )
        resultado_rechazo = await servicio.procesarOperacion(
            escenario.usuario_a, op_rechazada
        )

        assert resultado_rechazo.estado == "CONFLICTO"
        assert resultado_rechazo.codigo == "TIEMPO_INCOHERENTE"
        assert resultado_rechazo.recurso_id is None
        assert "transcurrio" in resultado_rechazo.detalle.lower() or "transcurrió" in resultado_rechazo.detalle.lower()

        # Persistencia durable: idempotencia devuelve el mismo conflicto
        reintento = await servicio.procesarOperacion(
            escenario.usuario_a, op_rechazada
        )
        assert reintento.estado == "CONFLICTO"
        assert reintento.codigo == "TIEMPO_INCOHERENTE"

        # Verificar que NO se crearon reservas ni movimientos de inventario
        despues_reservas_1 = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        assert despues_reservas_1 == antes_reservas

        inv_1 = await stock(db, escenario)
        assert inv_1.disponible == 5
        assert inv_1.reservado == 0

        # 2. Creada en T0, visita futura válida en T0 + 5h al sincronizar en T0 + 2h
        op_valida = construir_operacion(
            escenario,
            referencia.referencia_horaria_id,
            dispositivo,
            creada_local=T0,
            visita=T0 + timedelta(hours=5),
            secuencia=2,
        )
        resultado_valido = await servicio.procesarOperacion(
            escenario.usuario_a, op_valida
        )

        assert resultado_valido.estado == "ACEPTADA"
        assert resultado_valido.codigo == "OK"
        assert resultado_valido.recurso_id is not None

        # Verificar que SÍ se creó la reserva y se reservó inventario
        despues_reservas_2 = await contar(db, Reserva, empresa_id=escenario.empresa_a_id)
        assert despues_reservas_2 == antes_reservas + 1

        inv_2 = await stock(db, escenario)
        assert inv_2.disponible == 4
        assert inv_2.reservado == 1

        movimiento = (
            await db.execute(
                select(MovimientoInventario).where(
                    MovimientoInventario.referencia_id == resultado_valido.recurso_id,
                    MovimientoInventario.tipo == "RESERVA",
                )
            )
        ).scalars().first()
        assert movimiento is not None
        assert movimiento.cantidad == 1
