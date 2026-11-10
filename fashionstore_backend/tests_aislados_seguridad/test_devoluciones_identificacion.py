"""Devoluciones con relaciones reales en SQLite; no valida bloqueos PostgreSQL."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from test_bloque_seguridad import AHORA, datos, insertar, peticion
from backend.app.core.modules.ventas_pagos.models import Venta, DetalleVenta
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.posventa.models import ObligacionReembolso
from backend.app.core.modules.posventa.services.devolucion_service import (
    DevolucionService, DevolucionSolicitudDTO, InspeccionDTO, Devolucion,
)


@pytest.fixture
def compra(datos):
    e = datos
    # Adaptación exclusiva del dialecto: el no-op NO simula concurrencia PG.
    conexion = e.session.connection().connection.driver_connection
    conexion.create_function("hashtextextended", 2, lambda *_: 1)
    conexion.create_function("pg_advisory_xact_lock", 1, lambda *_: 0)
    e.venta = e.session.get(Venta, e.v1)
    e.venta.entregada_en = AHORA - timedelta(days=2)
    e.linea = insertar(e, DetalleVenta, venta_id=e.v1, variante_id=e.variante, cantidad=2,
                      precio_unitario=Decimal("55.50"), descuento=0, costo_promedio=10)
    e.inv = insertar(e, InventarioSucursal, variante_id=e.variante, sucursal_id=e.s1, disponible=5, reservado=0)
    e.session.commit()
    e.dto = DevolucionSolicitudDTO(venta_id=e.v1, lineas=[{"detalle_venta_id": e.linea, "cantidad": 1}], motivo_codigo="TALLA")
    return e


@pytest.mark.asyncio
async def test_http_exige_linea_original_no_uuid_variante(compra):
    e = compra
    e.usuario = e.cliente
    malo = await peticion(e, "POST", "/devoluciones/solicitudes", headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"venta_id": str(e.v1), "lineas": [{"variante_id": str(e.variante), "cantidad": 1}], "motivo_codigo": "TALLA"})
    assert malo.status_code == 422
    clave = str(uuid.uuid4())
    bueno = await peticion(e, "POST", "/devoluciones/solicitudes", headers={"Idempotency-Key": clave}, json=e.dto.model_dump(mode="json"))
    assert bueno.status_code == 201
    assert bueno.json()["venta_id"] == str(e.v1)
    assert bueno.json()["detalles"][0]["detalle_venta_id"] == str(e.linea)
    repetido = await peticion(e, "POST", "/devoluciones/solicitudes", headers={"Idempotency-Key": clave}, json=e.dto.model_dump(mode="json"))
    assert repetido.status_code == 201 and repetido.json()["id"] == bueno.json()["id"]
    assert e.session.get(InventarioSucursal, e.inv).disponible == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("actor,codigo", [("otro",403),("admin_b",404)])
async def test_solicitud_ajena_no_cambia_stock(compra, actor, codigo):
    e = compra
    with pytest.raises(HTTPException) as error:
        await DevolucionService(e.db).solicitar(getattr(e, actor), e.dto, uuid.uuid4())
    assert error.value.status_code == codigo
    assert e.session.get(InventarioSucursal, e.inv).disponible == 5
    assert not e.session.execute(select(Devolucion)).scalars().all()


@pytest.mark.asyncio
async def test_inspeccion_titular_encargado_y_reintento_kardex_unico(compra):
    e = compra
    servicio = DevolucionService(e.db)
    dev = await servicio.solicitar(e.cliente, e.dto, uuid.uuid4())
    inspeccion = InspeccionDTO(condicion_fisica="EXCELENTE", responsabilidad_tienda=True, dictamen="APROBADA_REPOSICION")
    with pytest.raises(HTTPException) as error:
        await servicio.inspeccionar(e.cliente, dev.id, inspeccion, uuid.uuid4())
    assert error.value.status_code == 403
    clave = uuid.uuid4()
    uno = await servicio.inspeccionar(e.personal, dev.id, inspeccion, clave)
    dos = await servicio.inspeccionar(e.personal, dev.id, inspeccion, clave)
    assert uno.id == dos.id and dos.estado == "APROBADA_REPOSICION"
    assert e.session.get(InventarioSucursal, e.inv).disponible == 6
    movimientos = e.session.execute(select(MovimientoInventario).where(MovimientoInventario.tipo == "DEVOLUCION")).scalars().all()
    assert len(movimientos) == 1 and movimientos[0].referencia_id == e.linea


@pytest.mark.asyncio
async def test_usada_no_repone_y_dictamen_financiero_no_es_reintegro(compra):
    e = compra
    servicio = DevolucionService(e.db)
    dev = await servicio.solicitar(e.cliente, e.dto, uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        await servicio.inspeccionar(e.personal, dev.id,
            InspeccionDTO(condicion_fisica="USADA", responsabilidad_tienda=True, dictamen="APROBADA_REPOSICION"), uuid.uuid4())
    assert error.value.status_code == 409
    resultado = await servicio.inspeccionar(e.personal, dev.id,
        InspeccionDTO(condicion_fisica="USADA", responsabilidad_tienda=True, dictamen="APROBADA_REEMBOLSO"), uuid.uuid4())
    assert resultado.estado == "APROBADA_REEMBOLSO"
    assert e.session.get(InventarioSucursal, e.inv).disponible == 5
    assert not e.session.execute(select(ObligacionReembolso)).scalars().all()


@pytest.mark.asyncio
async def test_cantidades_acumuladas_no_exceden_linea(compra):
    e = compra
    servicio = DevolucionService(e.db)
    await servicio.solicitar(e.cliente, e.dto, uuid.uuid4())
    await servicio.solicitar(e.cliente, e.dto, uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        await servicio.solicitar(e.cliente, e.dto, uuid.uuid4())
    assert error.value.status_code == 409
    assert len(e.session.execute(select(Devolucion)).scalars().all()) == 2
