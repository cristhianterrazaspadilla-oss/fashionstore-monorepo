"""Flujos reales sobre SQLite en memoria; no prueba concurrencia PostgreSQL."""
import socket
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from test_bloque_seguridad import AHORA, datos, insertar
from backend.app.core.config import settings
from backend.app.core.modules.catalogo.models import Producto, VarianteProducto
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.reservas_traslados.models import Reserva, DetalleReserva
from backend.app.core.modules.reservas_traslados.services.reserva_service import ReservaService
from backend.app.core.modules.ventas_pagos.services.pedido_service import (
    PedidoService, LineaCarritoCrearDTO, LineaCarritoModificarDTO,
)


def test_aislamiento_no_lee_dotenv_ni_habilita_red():
    assert settings.DATABASE_URL == "sqlite:///:memory:"
    assert not settings.STRIPE_ENABLED and not settings.DECART_ENABLED
    assert not settings.GEMINI_API_KEY and not settings.EXPIRACION_JOB_ACTIVO
    # El audit hook rechaza antes de abrir: no lee un archivo real.
    with pytest.raises(AssertionError, match="archivos .env"):
        Path(".env").read_text()
    with pytest.raises(AssertionError, match="conexiones externas"):
        socket.create_connection(("proveedor.invalid", 443))


@pytest.mark.asyncio
async def test_carrito_precio_servidor_reintento_y_aislamiento(datos):
    e = datos
    variante = e.session.get(VarianteProducto, e.variante)
    variante.precio = Decimal("12.34")
    e.session.commit()
    servicio = PedidoService(e.db)
    dto = LineaCarritoCrearDTO(variante_id=e.variante, cantidad=2)
    clave = uuid.uuid4()
    primero = await servicio.agregar_linea(e.cliente, dto, "WEB", clave)
    repetido = await servicio.agregar_linea(e.cliente, dto, "WEB", clave)
    assert primero.id == repetido.id and repetido.lineas[0].cantidad == 2
    assert repetido.total_estimado_bob == Decimal("24.68")
    assert repetido.lineas[0].precio_unitario_bob == Decimal("12.34")
    # UUID de variante usado por web y UUID de línea admitido por el API.
    cambiado = await servicio.modificar_linea(e.cliente, e.variante,
        LineaCarritoModificarDTO(cantidad=3), "WEB", uuid.uuid4())
    assert cambiado.total_estimado_bob == Decimal("37.02")
    ajeno = await servicio.consultar_carrito(e.cliente_b, "WEB")
    assert not ajeno.lineas and ajeno.id != primero.id
    with pytest.raises(HTTPException) as error:
        await servicio.agregar_linea(e.cliente_b, dto, "WEB", uuid.uuid4())
    assert error.value.status_code == 404
    quitado = await servicio.quitar_linea(e.cliente, cambiado.lineas[0].id, "WEB", uuid.uuid4())
    assert not quitado.lineas and quitado.total_estimado_bob == 0


@pytest.mark.asyncio
async def test_carrito_no_inventa_precio_cero_si_falta_variante(datos):
    e = datos
    servicio = PedidoService(e.db)
    await servicio.agregar_linea(e.cliente,
        LineaCarritoCrearDTO(variante_id=e.variante, cantidad=1), "WEB", uuid.uuid4())
    e.session.delete(e.session.get(VarianteProducto, e.variante))
    e.session.commit()
    with pytest.raises(HTTPException) as error:
        await servicio.consultar_carrito(e.cliente, "WEB")
    assert error.value.status_code == 409 and "PRECIO_NO_DISPONIBLE" in error.value.detail


@pytest.mark.asyncio
async def test_ultima_unidad_secuencial_no_se_reserva_dos_veces(datos):
    e = datos
    insertar(e, InventarioSucursal, variante_id=e.variante, sucursal_id=e.s1,
             disponible=1, reservado=0)
    e.session.commit()
    repo = InventarioRepository(e.db)
    fila = await repo.moverDisponibleAReservado(e.variante, e.s1, 1)
    await e.db.commit()
    assert (fila.disponible, fila.reservado) == (0, 1)
    with pytest.raises(HTTPException) as error:
        await repo.moverDisponibleAReservado(e.variante, e.s1, 1)
    assert error.value.status_code == 409
    liberada = await repo.liberarReservado(e.variante, e.s1, 1)
    assert (liberada.disponible, liberada.reservado) == (1, 0)


@pytest.fixture
def reserva_multiple(datos):
    e = datos
    e.variante2 = insertar(e, VarianteProducto, empresa_id=e.a, producto_id=e.producto)
    pb = insertar(e, Producto, empresa_id=e.b, nombre="Producto B")
    vb = insertar(e, VarianteProducto, empresa_id=e.b, producto_id=pb)
    e.inv1 = insertar(e, InventarioSucursal, variante_id=e.variante, sucursal_id=e.s1, disponible=4, reservado=1)
    e.inv2 = insertar(e, InventarioSucursal, variante_id=e.variante2, sucursal_id=e.s1, disponible=5, reservado=2)
    e.invb = insertar(e, InventarioSucursal, variante_id=vb, sucursal_id=e.sb, disponible=999, reservado=9)
    e.rid = insertar(e, Reserva, empresa_id=e.a, cliente_id=e.cliente.id, sucursal_destino_id=e.s1,
        codigo="RES-A", estado="PENDIENTE", fecha_creacion=AHORA, vence_en=AHORA+timedelta(days=1))
    insertar(e, DetalleReserva, reserva_id=e.rid, variante_id=e.variante, cantidad_solicitada=3,
        cantidad_reservada=1, cantidad_vendida=2, cantidad_liberada=0, cantidad_pendiente_traslado=0,
        estado_linea="VENDIDA_PARCIAL")
    insertar(e, DetalleReserva, reserva_id=e.rid, variante_id=e.variante2, cantidad_solicitada=2,
        cantidad_reservada=2, cantidad_vendida=0, cantidad_liberada=0, cantidad_pendiente_traslado=0,
        estado_linea="RESERVADA")
    e.session.commit()
    return e


@pytest.mark.asyncio
async def test_cancelar_reserva_multiple_libera_solo_restante_una_vez(reserva_multiple):
    e = reserva_multiple
    servicio = ReservaService(e.db)
    uno = await servicio.cancelar(e.cliente, e.rid)
    dos = await servicio.cancelar(e.cliente, e.rid)
    assert uno.estado == dos.estado == "CANCELADA"
    assert (e.session.get(InventarioSucursal, e.inv1).disponible,
            e.session.get(InventarioSucursal, e.inv1).reservado) == (5, 0)
    assert (e.session.get(InventarioSucursal, e.inv2).disponible,
            e.session.get(InventarioSucursal, e.inv2).reservado) == (7, 0)
    assert e.session.get(InventarioSucursal, e.invb).reservado == 9
    movimientos = e.session.execute(select(MovimientoInventario).where(
        MovimientoInventario.referencia_id == e.rid)).scalars().all()
    assert sorted(m.cantidad for m in movimientos) == [1, 2]
    assert all(m.tipo == "LIBERACION_RESERVA" for m in movimientos)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor,codigo", [("admin_b", 404), ("otro", 403)])
async def test_cancelacion_ajena_no_libera_existencias(reserva_multiple, actor, codigo):
    e = reserva_multiple
    rid, inv_id = e.rid, e.inv1
    with pytest.raises(HTTPException) as error:
        await ReservaService(e.db).cancelar(getattr(e, actor), rid)
    assert error.value.status_code == codigo
    assert e.session.get(InventarioSucursal, inv_id).reservado == 1
    assert not e.session.execute(select(MovimientoInventario).where(
        MovimientoInventario.referencia_id == rid)).scalars().all()
