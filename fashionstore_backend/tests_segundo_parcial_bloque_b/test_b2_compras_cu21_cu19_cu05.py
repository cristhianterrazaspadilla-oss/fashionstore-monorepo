"""Pruebas del Lote B2: Compra y Caja Conectada (CU21, CU19, CU05).

Cubre:
- CU21: Carrito propio (sin comprometer inventario), edición/eliminación de líneas,
        checkout durable creando PedidoCompra con oferta versionada y separación
        estricta de estados de pago y cumplimiento (A-PAGO-01).
- CU19: Venta presencial liquidada en caja (efectivo con cálculo de vuelto exacto,
        bloqueo atómico de inventario, emisión de comprobante y Kardex VENTA_PRESENCIAL único).
- CU05: Compra offline v3 por sincronización diferida:
        - Revalidación central de plan, identidad, empresa, oferta y tasa.
        - Coincidencia exacta con método preparado: cobro conectado, compromiso atómico de stock.
        - Sin stock (NO_CUMPLIBLE): derivación a reembolso íntegro CU27 sin stock negativo.
        - Variación de importes: REQUIERE_NUEVA_ACEPTACION.
        - Falta de método/consentimiento: PENDIENTE_INTERVENCION.
        - Autenticación 3DS: REQUIERE_ACCION_CLIENTE.
        - Idempotencia por UUID de operacion_id.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import time
import uuid
import asyncio
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from backend.app.core.config import settings
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.reservas_traslados.schemas_sincronizacion import (
    AutorizacionCobroV3DTO,
    OperacionDTO,
    OperacionDatosCompraDTO,
    OperacionLineaDTO,
)
from backend.app.core.modules.reservas_traslados.services.sincronizacion_service import SincronizacionService, calcular_huella_compra_canonica
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Pago, Venta
from backend.app.core.modules.ventas_pagos.models_ordenes import MetodoPreparado, OrdenPago
from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import (
    FakeStripeGateway,
    fijar_gateway,
    obtener_gateway,
)
from backend.app.core.modules.ventas_pagos.services.pedido_service import (
    Comprobante,
    DetallePedido,
    OfertaCompra,
    PedidoCompra,
    ObligacionReembolso,
)
from .conftest import T0, RelojControlable, app


@pytest.fixture(autouse=True)
def configurar_fake_stripe():
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    yield fake
    fijar_gateway(None)


def generar_firma_stripe(cuerpo: bytes, secret: str, timestamp: int) -> str:
    payload_a_firmar = f"{timestamp}.".encode("utf-8") + cuerpo
    firma = hmac.new(secret.encode("utf-8"), payload_a_firmar, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={firma}"


# ============================================================================
# CU21: GESTIONAR CARRITO Y CONFIRMAR COMPRA DIGITAL DURABLE
# ============================================================================

@pytest.mark.asyncio
async def test_cu21_consultar_carrito_vacio_lo_crea_activo(http, escenario):
    """CU21: Consultar el carrito propio crea un carrito ACTIVO vacío si no existía."""
    http.usar(escenario.usuario_a)
    resp = await http.cliente.get("/api/v1/carritos/mio")
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert datos["estado"] == "ACTIVO"
    assert datos["total_estimado_bob"] == "0.00" or float(datos["total_estimado_bob"]) == 0
    assert len(datos["lineas"]) == 0


@pytest.mark.asyncio
async def test_cu21_agregar_linea_no_compromete_stock(http, escenario, fabrica_sesiones):
    """CU21: Agregar una línea al carrito no bloquea ni reserva stock en inventario."""
    http.usar(escenario.usuario_a)

    # Stock inicial
    async with fabrica_sesiones() as db:
        stmt = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_antes = (await db.execute(stmt)).scalars().first()
        disponible_antes = inv_antes.disponible
        reservado_antes = inv_antes.reservado

    # Agregar 2 unidades
    resp = await http.cliente.post(
        "/api/v1/carritos/mio/lineas",
        json={"variante_id": str(escenario.variante_a_id), "cantidad": 2},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 200, resp.text
    cart = resp.json()
    assert len(cart["lineas"]) == 1
    assert cart["lineas"][0]["cantidad"] == 2
    assert float(cart["total_estimado_bob"]) == 200.0

    # Verificar que el stock sigue idéntico
    async with fabrica_sesiones() as db:
        inv_despues = (await db.execute(stmt)).scalars().first()
        assert inv_despues.disponible == disponible_antes
        assert inv_despues.reservado == reservado_antes


@pytest.mark.asyncio
async def test_cu21_modificar_y_quitar_linea(http, escenario):
    """CU21: Modificar cantidad de una línea y quitarla del carrito."""
    http.usar(escenario.usuario_a)

    # Asegurar línea en carrito
    await http.cliente.post(
        "/api/v1/carritos/mio/lineas",
        json={"variante_id": str(escenario.variante_a_id), "cantidad": 1},
    )

    # Modificar cantidad a 3
    resp_mod = await http.cliente.patch(
        f"/api/v1/carritos/mio/lineas/{escenario.variante_a_id}",
        json={"cantidad": 3},
    )
    assert resp_mod.status_code == 200, resp_mod.text
    assert resp_mod.json()["lineas"][0]["cantidad"] == 3
    assert float(resp_mod.json()["total_estimado_bob"]) == 300.0

    # Quitar línea
    resp_del = await http.cliente.delete(
        f"/api/v1/carritos/mio/lineas/{escenario.variante_a_id}"
    )
    assert resp_del.status_code == 200, resp_del.text
    assert len(resp_del.json()["lineas"]) == 0
    assert float(resp_del.json()["total_estimado_bob"]) == 0.0


@pytest.mark.asyncio
async def test_cu21_checkout_crea_pedido_durable_con_oferta_versionada(
    http, escenario, fabrica_sesiones
):
    """CU21: Checkout crea PedidoCompra durable con oferta versionada y estados independientes (A-PAGO-01)."""
    http.usar(escenario.usuario_a)

    # 1. Agregar prenda al carrito
    await http.cliente.post(
        "/api/v1/carritos/mio/lineas",
        json={"variante_id": str(escenario.variante_a_id), "cantidad": 2},
    )

    clave_checkout = uuid.uuid4()
    resp_co = await http.cliente.post(
        "/api/v1/carritos/mio/checkout",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
        },
        headers={"Idempotency-Key": str(clave_checkout)},
    )
    assert resp_co.status_code == 201, resp_co.text
    pedido = resp_co.json()

    # Validaciones contractuales
    assert pedido["pedido_id"] is not None
    assert pedido["oferta_revision"] == 1
    assert float(pedido["total_bob"]) == 200.0
    assert pedido["estado_pago"] == "SIN_PAGO"
    assert pedido["estado_cumplimiento"] == "SIN_ASIGNACION"
    assert pedido["estado"] == "BORRADOR"
    assert len(pedido["lineas"]) == 1

    # Verificar persistencia en base de datos
    async with fabrica_sesiones() as db:
        ped_db = await db.get(PedidoCompra, uuid.UUID(pedido["pedido_id"]))
        assert ped_db is not None
        assert ped_db.empresa_id == escenario.empresa_a_id
        assert ped_db.cliente_id == escenario.usuario_a.id
        assert ped_db.total_bob == Decimal("200.00")

        # Verificar oferta de compra en tabla comercial.ofertas_compra
        stmt_of = select(OfertaCompra).where(OfertaCompra.pedido_id == ped_db.id)
        oferta = (await db.execute(stmt_of)).scalars().first()
        assert oferta is not None
        assert oferta.revision == 1
        assert oferta.total_bob == Decimal("200.00")
        assert oferta.documento_hash is not None

    # Idempotencia: misma clave devuelve el mismo pedido
    resp_reintento = await http.cliente.post(
        "/api/v1/carritos/mio/checkout",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
        },
        headers={"Idempotency-Key": str(clave_checkout)},
    )
    assert resp_reintento.status_code == 200 or resp_reintento.status_code == 201
    assert resp_reintento.json()["pedido_id"] == pedido["pedido_id"]


@pytest.mark.asyncio
async def test_cu21_checkout_concurrente_misma_clave_retorna_mismo_pedido(
    http, escenario
):
    """El mismo checkout simultÃ¡neo no duplica pedidos ni filtra errores SQL."""
    http.usar(escenario.usuario_a)
    await http.cliente.post(
        "/api/v1/carritos/mio/lineas",
        json={"variante_id": str(escenario.variante_a_id), "cantidad": 1},
    )

    clave = str(uuid.uuid4())
    barrera = asyncio.Event()
    carga = {
        "sucursal_id": str(escenario.sucursal_a_id),
        "modalidad": "RECOJO",
    }

    async def checkout(cliente: AsyncClient):
        await barrera.wait()
        return await cliente.post(
            "/api/v1/carritos/mio/checkout",
            json=carga,
            headers={"Idempotency-Key": clave},
        )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://pruebas"
    ) as segundo_cliente:
        primero = asyncio.create_task(checkout(http.cliente))
        segundo = asyncio.create_task(checkout(segundo_cliente))
        await asyncio.sleep(0.02)
        barrera.set()
        resp_a, resp_b = await asyncio.gather(primero, segundo)

    assert resp_a.status_code in (200, 201), resp_a.text
    assert resp_b.status_code in (200, 201), resp_b.text
    assert resp_a.json()["pedido_id"] == resp_b.json()["pedido_id"]


@pytest.mark.asyncio
async def test_cu21_checkout_delivery_requiere_direccion(http, escenario):
    """CU21: Modalidad DELIVERY sin dirección de entrega devuelve 400 Bad Request."""
    http.usar(escenario.usuario_a)

    await http.cliente.post(
        "/api/v1/carritos/mio/lineas",
        json={"variante_id": str(escenario.variante_a_id), "cantidad": 1},
    )

    resp = await http.cliente.post(
        "/api/v1/carritos/mio/checkout",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "DELIVERY",
            "direccion": None,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 400, resp.text


# ============================================================================
# CU19: VENTA PRESENCIAL CONECTADA EN CAJA
# ============================================================================

@pytest.mark.asyncio
async def test_cu19_venta_presencial_liquidar_efectivo_con_vuelto_y_kardex(
    http, escenario, fabrica_sesiones
):
    """CU19: Liquidar venta presencial en efectivo, calcular vuelto exacto y emitir Kardex único."""
    # Usar cajero / admin de la empresa
    http.usar(escenario.usuario_admin_a)

    async with fabrica_sesiones() as db:
        stmt = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_antes = (await db.execute(stmt)).scalars().first()
        disponible_antes = inv_antes.disponible

    clave_venta = uuid.uuid4()
    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 2,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "EFECTIVO",
            "efectivo_recibido_bob": 250.0,
        },
        headers={"Idempotency-Key": str(clave_venta)},
    )
    assert resp.status_code == 201, resp.text
    res = resp.json()

    assert res["venta_id"] is not None
    assert float(res["total_bob"]) == 200.0
    # Monto recibido (250) - Total debido (200) = Vuelto entregado (50)
    assert float(res["cambio_entregado_bob"]) == 50.0
    assert res["estado_pago"] == "PAGADA"
    assert res["estado_entrega"] == "ENTREGADA"
    assert len(res["kardex_ids"]) == 1

    # Verificar stock reducido en exactamente 2 unidades
    async with fabrica_sesiones() as db:
        inv_despues = (await db.execute(stmt)).scalars().first()
        assert inv_despues.disponible == disponible_antes - 2

        # Verificar comprobante emitido
        stmt_comp = select(Comprobante).where(Comprobante.recurso_id == uuid.UUID(res["venta_id"]))
        comp = (await db.execute(stmt_comp)).scalars().first()
        assert comp is not None
        assert comp.tipo == "VENTA_PRESENCIAL"

        # Verificar Pago registrado
        stmt_pago = select(Pago).where(Pago.venta_id == uuid.UUID(res["venta_id"]))
        pago = (await db.execute(stmt_pago)).scalars().first()
        assert pago is not None
        assert pago.metodo == "EFECTIVO"
        assert pago.monto == Decimal("200.00")
        assert pago.cambio_entregado_bob == Decimal("50.00")

    # Idempotencia: misma clave devuelve la misma venta liquidada
    resp_reintento = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 2,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "EFECTIVO",
            "efectivo_recibido_bob": 250.0,
        },
        headers={"Idempotency-Key": str(clave_venta)},
    )
    assert resp_reintento.status_code == 201 or resp_reintento.status_code == 200
    assert resp_reintento.json()["venta_id"] == res["venta_id"]


@pytest.mark.asyncio
async def test_cu19_venta_presencial_efectivo_insuficiente_falla(http, escenario):
    """CU19: Si el efectivo recibido es menor al total adeudado devuelve 400 Bad Request."""
    http.usar(escenario.usuario_admin_a)

    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "EFECTIVO",
            "efectivo_recibido_bob": 80.0,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_cu19_venta_presencial_sin_stock_falla_409(http, escenario):
    """CU19: Intentar vender una prenda sin stock libre devuelve 409 Conflict."""
    http.usar(escenario.usuario_admin_a)

    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [
                {
                    "variante_id": str(escenario.variante_sin_stock_id),
                    "cantidad": 1,
                    "precio_unitario_bob": 100.0,
                }
            ],
            "medio_pago": "EFECTIVO",
            "efectivo_recibido_bob": 100.0,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_cu19_cliente_no_puede_liquidar_en_caja(http, escenario):
    """CU19: Rol CLIENTE no tiene permiso para liquidar ventas de caja (403 Forbidden)."""
    http.usar(escenario.usuario_a)

    resp = await http.cliente.post(
        "/api/v1/ventas/presenciales/liquidar",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "medio_pago": "EFECTIVO",
            "efectivo_recibido_bob": 100.0,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 403, resp.text


# ============================================================================
# CU05: COMPRA OFFLINE v3 POR SINCRONIZACIÓN DIFERIDA
# ============================================================================

@pytest.mark.asyncio
async def test_cu05_solicitar_compra_v3_con_stock_exito(http, escenario, fabrica_sesiones):
    """CU05 v3: Compra offline con método preparado y stock disponible compromete inventario y aprueba."""
    http.usar(escenario.usuario_a)

    # 1. Obtener referencia horaria
    disp_id = uuid.uuid4()
    resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
    assert resp_ref.status_code == 200, resp_ref.text
    ref_id = resp_ref.json()["referencia_horaria_id"]

    operacion_id = uuid.uuid4()
    metodo_prep_id = uuid.uuid4()
    ahora_local = datetime.now(timezone.utc)

    # Crear método preparado válido para el cliente
    async with fabrica_sesiones() as db:
        mp = MetodoPreparado(
            id=metodo_prep_id,
            empresa_id=escenario.empresa_a_id,
            cliente_id=escenario.usuario_a.id,
            proveedor="STRIPE",
            cliente_proveedor_cifrado=b"cus_test",
            metodo_proveedor_cifrado=b"pm_test",
            preparacion_proveedor_cifrado=b"seti_test",
            estado="LISTO",
        )
        db.add(mp)
        r_t = await db.execute(select(text("id, tasa_bob_por_usd FROM plataforma.tasas_cambio ORDER BY vigente_desde DESC LIMIT 1")))
        f_t = r_t.first()
        tasa_id = f_t[0] if f_t else uuid.uuid4()
        tasa_val = Decimal(str(f_t[1])) if f_t else Decimal("6.96")
        await db.commit()

    cid = uuid.uuid4()
    usd_cobro = (Decimal("100.00") / tasa_val).quantize(Decimal("0.01"))
    expira_en_calc = ahora_local + timedelta(hours=24)
    huella = calcular_huella_compra_canonica(
        empresa_id=escenario.empresa_a_id,
        usuario_id=escenario.usuario_a.id,
        sucursal_id=escenario.sucursal_a_id,
        modalidad="RECOJO",
        direccion=None,
        lineas=[{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_unitario_bob": "100.00"}],
        base_bob=Decimal("100.00"),
        descuento_bob=Decimal("0.00"),
        envio_bob=Decimal("0.00"),
        total_bob=Decimal("100.00"),
        moneda_cobro="USD",
        importe_cobro=usd_cobro,
        tasa_id=tasa_id,
        tasa_bob_por_usd=tasa_val,
        condiciones_version="v3",
        vigente_hasta=expira_en_calc,
    )

    # Operación SOLICITAR_COMPRA con autorización de cobro exacta de 15 campos contractuales
    datos_compra = {
        "sucursal_id": str(escenario.sucursal_a_id),
        "modalidad": "RECOJO",
        "lineas": [
            {
                "variante_id": str(escenario.variante_a_id),
                "cantidad": 1,
            }
        ],
        "autorizacion_cobro": {
            "consentimiento_id": str(cid),
            "aceptado_local_en": ahora_local.isoformat(),
            "huella_compra": huella,
            "base_bob": "100.00",
            "descuento_bob": "0.00",
            "envio_bob": "0.00",
            "total_bob": "100.00",
            "moneda_cobro": "USD",
            "importe_cobro": str(usd_cobro),
            "tasa_id": str(tasa_id),
            "tasa_bob_por_usd": str(tasa_val),
            "condiciones_version": "v3",
            "vigente_hasta": (ahora_local + timedelta(hours=24)).isoformat(),
            "preparacion_pago_id": str(metodo_prep_id),
            "permite_cobro_al_reconectar": True,
        },
    }

    op_payload = {
        "version_esquema": 3,
        "operacion_id": str(operacion_id),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 1,
        "referencia_horaria_id": str(ref_id),
        "datos": datos_compra,
    }

    resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
    assert resp.status_code == 200, resp.text
    resultado = resp.json()

    assert resultado["estado"] == "ACEPTADA"
    assert resultado["codigo"] == "OK"
    assert resultado["recurso_id"] is not None

    # Validar persistencia en base de datos
    async with fabrica_sesiones() as db:
        pedido = await db.get(PedidoCompra, uuid.UUID(resultado["recurso_id"]))
        assert pedido is not None
        assert pedido.estado == "CONFIRMADO"
        assert pedido.estado_pago == "PAGADO"
        assert pedido.estado_cumplimiento == "COMPROMETIDO"
        assert pedido.operacion_id == operacion_id

        # Validar que existe OrdenPago capturada vinculada al pedido
        stmt_ord = select(OrdenPago).where(
            OrdenPago.contexto == "PEDIDO",
            OrdenPago.pedido_id == pedido.id,
        )
        orden = (await db.execute(stmt_ord)).scalars().first()
        assert orden is not None
        assert orden.estado == "CAPTURADO"
        assert orden.proveedor == "STRIPE"


@pytest.mark.asyncio
async def test_cu05_solicitar_compra_v3_sin_stock_deriva_reembolso_cu27(
    http, escenario, fabrica_sesiones
):
    """CU05: Si hay cobro pero no hay existencias, pasa a NO_CUMPLIBLE y deriva reembolso íntegro CU27."""
    http.usar(escenario.usuario_a)

    disp_id = uuid.uuid4()
    resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
    ref_id = resp_ref.json()["referencia_horaria_id"]

    operacion_id = uuid.uuid4()
    metodo_prep_id = uuid.uuid4()
    ahora_local = datetime.now(timezone.utc)

    # Crear método preparado válido para el cliente
    async with fabrica_sesiones() as db:
        mp = MetodoPreparado(
            id=metodo_prep_id,
            empresa_id=escenario.empresa_a_id,
            cliente_id=escenario.usuario_a.id,
            proveedor="STRIPE",
            cliente_proveedor_cifrado=b"cus_test",
            metodo_proveedor_cifrado=b"pm_test",
            preparacion_proveedor_cifrado=b"seti_test",
            estado="LISTO",
        )
        db.add(mp)
        r_t = await db.execute(select(text("id, tasa_bob_por_usd FROM plataforma.tasas_cambio ORDER BY vigente_desde DESC LIMIT 1")))
        f_t = r_t.first()
        tasa_id = f_t[0] if f_t else uuid.uuid4()
        tasa_val = Decimal(str(f_t[1])) if f_t else Decimal("6.96")
        await db.commit()

    cid = uuid.uuid4()
    usd_cobro = (Decimal("100.00") / tasa_val).quantize(Decimal("0.01"))
    expira_en_calc = ahora_local + timedelta(hours=24)
    huella = calcular_huella_compra_canonica(
        empresa_id=escenario.empresa_a_id,
        usuario_id=escenario.usuario_a.id,
        sucursal_id=escenario.sucursal_a_id,
        modalidad="RECOJO",
        direccion=None,
        lineas=[{"variante_id": str(escenario.variante_sin_stock_id), "cantidad": 1, "precio_unitario_bob": "100.00"}],
        base_bob=Decimal("100.00"),
        descuento_bob=Decimal("0.00"),
        envio_bob=Decimal("0.00"),
        total_bob=Decimal("100.00"),
        moneda_cobro="USD",
        importe_cobro=usd_cobro,
        tasa_id=tasa_id,
        tasa_bob_por_usd=tasa_val,
        condiciones_version="v3",
        vigente_hasta=expira_en_calc,
    )

    op_payload = {
        "version_esquema": 3,
        "operacion_id": str(operacion_id),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 2,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [
                {
                    "variante_id": str(escenario.variante_sin_stock_id),
                    "cantidad": 1,
                }
            ],
            "autorizacion_cobro": {
                "consentimiento_id": str(cid),
                "aceptado_local_en": ahora_local.isoformat(),
                "huella_compra": huella,
                "base_bob": "100.00",
                "descuento_bob": "0.00",
                "envio_bob": "0.00",
                "total_bob": "100.00",
                "moneda_cobro": "USD",
                "importe_cobro": str(usd_cobro),
                "tasa_id": str(tasa_id),
                "tasa_bob_por_usd": str(tasa_val),
                "condiciones_version": "v3",
                "vigente_hasta": (ahora_local + timedelta(hours=24)).isoformat(),
                "preparacion_pago_id": str(metodo_prep_id),
                "permite_cobro_al_reconectar": True,
            },
        },
    }

    resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
    assert resp.status_code == 200, resp.text
    resultado = resp.json()

    assert resultado["estado"] == "ACEPTADA"
    assert resultado["codigo"] == "SIN_STOCK"
    pedido_id = uuid.UUID(resultado["recurso_id"])

    # Validar que se creó la obligación de reembolso en comercial.obligaciones_reembolso
    async with fabrica_sesiones() as db:
        pedido = await db.get(PedidoCompra, pedido_id)
        assert pedido.estado == "NO_CUMPLIBLE"
        assert pedido.estado_pago == "PAGADO"
        assert pedido.estado_cumplimiento == "NO_CUMPLIBLE"

        stmt_reemb = select(ObligacionReembolso).where(
            ObligacionReembolso.origen_tipo == "PEDIDO",
            ObligacionReembolso.origen_id == pedido_id,
        )
        reembolso = (await db.execute(stmt_reemb)).scalars().first()
        assert reembolso is not None
        assert reembolso.monto_bob == Decimal("100.00")
        assert reembolso.motivo_codigo == "SIN_STOCK"
        assert reembolso.estado == "PENDIENTE_AUTORIZACION"


@pytest.mark.asyncio
async def test_cu05_solicitar_compra_v3_sin_captura_nunca_pasa_a_pagado(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """CU05: Compra v3 sin captura confirmada de Stripe queda pendiente y jamás pasa a PAGADO."""
    http.usar(escenario.usuario_a)

    # Forzar que la pasarela devuelva REQUIRES_ACTION (SCA / 3DS pendiente)
    configurar_fake_stripe.simular_requiere_accion = True

    try:
        disp_id = uuid.uuid4()
        resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
        ref_id = resp_ref.json()["referencia_horaria_id"]

        operacion_id = uuid.uuid4()
        metodo_prep_id = uuid.uuid4()
        ahora_local = datetime.now(timezone.utc)

        async with fabrica_sesiones() as db:
            mp = MetodoPreparado(
                id=metodo_prep_id,
                empresa_id=escenario.empresa_a_id,
                cliente_id=escenario.usuario_a.id,
                proveedor="STRIPE",
                cliente_proveedor_cifrado=b"cus_test",
                metodo_proveedor_cifrado=b"pm_test",
                preparacion_proveedor_cifrado=b"seti_test",
                estado="LISTO",
            )
            db.add(mp)
            r_t = await db.execute(select(text("id, tasa_bob_por_usd FROM plataforma.tasas_cambio ORDER BY vigente_desde DESC LIMIT 1")))
            f_t = r_t.first()
            tasa_id = f_t[0] if f_t else uuid.uuid4()
            tasa_val = Decimal(str(f_t[1])) if f_t else Decimal("6.96")
            await db.commit()

        cid = uuid.uuid4()
        usd_cobro = (Decimal("100.00") / tasa_val).quantize(Decimal("0.01"))
        expira_en_calc = ahora_local + timedelta(hours=24)
        huella = calcular_huella_compra_canonica(
            empresa_id=escenario.empresa_a_id,
            usuario_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            modalidad="RECOJO",
            direccion=None,
            lineas=[{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_unitario_bob": "100.00"}],
            base_bob=Decimal("100.00"),
            descuento_bob=Decimal("0.00"),
            envio_bob=Decimal("0.00"),
            total_bob=Decimal("100.00"),
            moneda_cobro="USD",
            importe_cobro=usd_cobro,
            tasa_id=tasa_id,
            tasa_bob_por_usd=tasa_val,
            condiciones_version="v3",
            vigente_hasta=expira_en_calc,
        )

        op_payload = {
            "version_esquema": 3,
            "operacion_id": str(operacion_id),
            "tipo": "SOLICITAR_COMPRA",
            "creada_local_en": ahora_local.isoformat(),
            "empresa_id": str(escenario.empresa_a_id),
            "usuario_id": str(escenario.usuario_a.id),
            "dispositivo_id": str(disp_id),
            "secuencia_local": 3,
            "referencia_horaria_id": str(ref_id),
            "datos": {
                "sucursal_id": str(escenario.sucursal_a_id),
                "modalidad": "RECOJO",
                "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
                "autorizacion_cobro": {
                    "consentimiento_id": str(cid),
                    "aceptado_local_en": ahora_local.isoformat(),
                    "huella_compra": huella,
                    "base_bob": "100.00",
                    "descuento_bob": "0.00",
                    "envio_bob": "0.00",
                    "total_bob": "100.00",
                    "moneda_cobro": "USD",
                    "importe_cobro": str(usd_cobro),
                    "tasa_id": str(tasa_id),
                    "tasa_bob_por_usd": str(tasa_val),
                    "condiciones_version": "v3",
                    "vigente_hasta": (ahora_local + timedelta(hours=24)).isoformat(),
                    "preparacion_pago_id": str(metodo_prep_id),
                    "permite_cobro_al_reconectar": True,
                },
            },
        }

        resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
        assert resp.status_code == 200, resp.text
        res = resp.json()
        assert res["estado"] == "REQUIERE_ACCION_CLIENTE"
        assert res["codigo"] == "ACCION_CLIENTE_REQUERIDA"

        # Verificar en base de datos: SIN captura, estado_pago != PAGADO, stock libre NO comprometido
        async with fabrica_sesiones() as db:
            pedido = await db.get(PedidoCompra, uuid.UUID(res["recurso_id"]))
            assert pedido is not None
            assert pedido.estado_pago != "PAGADO"
            assert pedido.estado_pago == "EN_VERIFICACION"
            assert pedido.estado_cumplimiento == "SIN_ASIGNACION"

            # No se creó ninguna obligación de reembolso
            stmt_reemb = select(ObligacionReembolso).where(
                ObligacionReembolso.origen_tipo == "PEDIDO",
                ObligacionReembolso.origen_id == pedido.id,
            )
            reemb = (await db.execute(stmt_reemb)).scalars().first()
            assert reemb is None
    finally:
        configurar_fake_stripe.simular_requiere_accion = False


@pytest.mark.asyncio
async def test_cu05_solicitar_compra_v1_v2_no_cobran_automaticamente(
    http, escenario, fabrica_sesiones
):
    """CU05: Solicitudes de compra con versiones 1 y 2 registran pedido pero jamás cobran automáticamente."""
    http.usar(escenario.usuario_a)

    disp_id = uuid.uuid4()
    resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
    ref_id = resp_ref.json()["referencia_horaria_id"]
    ahora_local = datetime.now(timezone.utc)

    # 1. Prueba con version_esquema 1
    op_v1 = {
        "version_esquema": 1,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 10,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    r1 = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_v1)
    assert r1.status_code == 200, r1.text
    res1 = r1.json()
    assert res1["estado"] in ("PENDIENTE_PAGO", "ACEPTADA")
    p1_id = uuid.UUID(res1["recurso_id"])

    async with fabrica_sesiones() as db:
        p1 = await db.get(PedidoCompra, p1_id)
        assert p1 is not None
        assert p1.estado_pago == "SIN_PAGO"
        assert p1.estado_cumplimiento == "SIN_ASIGNACION"

        # Comprobar que no existe ninguna orden de pago creada automáticamente
        stmt_ord1 = select(OrdenPago).where(OrdenPago.contexto == "PEDIDO", OrdenPago.pedido_id == p1_id)
        assert (await db.execute(stmt_ord1)).scalars().first() is None

    # 2. Prueba con version_esquema 2 (requiere modalidad)
    op_v2 = {
        "version_esquema": 2,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 11,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    r2 = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_v2)
    assert r2.status_code == 200, r2.text
    res2 = r2.json()
    assert res2["estado"] in ("PENDIENTE_PAGO", "ACEPTADA")
    p2_id = uuid.UUID(res2["recurso_id"])

    async with fabrica_sesiones() as db:
        p2 = await db.get(PedidoCompra, p2_id)
        assert p2 is not None
        assert p2.estado_pago == "SIN_PAGO"
        assert p2.estado_cumplimiento == "SIN_ASIGNACION"

        stmt_ord2 = select(OrdenPago).where(OrdenPago.contexto == "PEDIDO", OrdenPago.pedido_id == p2_id)
        assert (await db.execute(stmt_ord2)).scalars().first() is None


@pytest.mark.asyncio
async def test_cu05_solicitar_compra_v3_webhook_repetido_no_duplica_cargo_ni_asignacion_ni_reembolso(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """CU05 / CU22: Webhook repetido o reintento no duplican cargo, asignación de stock ni reembolso."""
    http.usar(escenario.usuario_a)

    configurar_fake_stripe.simular_requiere_accion = True
    try:
        disp_id = uuid.uuid4()
        resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
        ref_id = resp_ref.json()["referencia_horaria_id"]

        operacion_id = uuid.uuid4()
        metodo_prep_id = uuid.uuid4()
        ahora_local = datetime.now(timezone.utc)

        async with fabrica_sesiones() as db:
            mp = MetodoPreparado(
                id=metodo_prep_id,
                empresa_id=escenario.empresa_a_id,
                cliente_id=escenario.usuario_a.id,
                proveedor="STRIPE",
                cliente_proveedor_cifrado=b"cus_test",
                metodo_proveedor_cifrado=b"pm_test",
                preparacion_proveedor_cifrado=b"seti_test",
                estado="LISTO",
            )
            db.add(mp)
            r_t = await db.execute(select(text("id, tasa_bob_por_usd FROM plataforma.tasas_cambio ORDER BY vigente_desde DESC LIMIT 1")))
            f_t = r_t.first()
            tasa_id = f_t[0] if f_t else uuid.uuid4()
            tasa_val = Decimal(str(f_t[1])) if f_t else Decimal("6.96")
            await db.commit()

        cid = uuid.uuid4()
        usd_cobro = (Decimal("100.00") / tasa_val).quantize(Decimal("0.01"))
        expira_en_calc = ahora_local + timedelta(hours=24)
        huella = calcular_huella_compra_canonica(
            empresa_id=escenario.empresa_a_id,
            usuario_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            modalidad="RECOJO",
            direccion=None,
            lineas=[{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_unitario_bob": "100.00"}],
            base_bob=Decimal("100.00"),
            descuento_bob=Decimal("0.00"),
            envio_bob=Decimal("0.00"),
            total_bob=Decimal("100.00"),
            moneda_cobro="USD",
            importe_cobro=usd_cobro,
            tasa_id=tasa_id,
            tasa_bob_por_usd=tasa_val,
            condiciones_version="v3",
            vigente_hasta=expira_en_calc,
        )

        op_payload = {
            "version_esquema": 3,
            "operacion_id": str(operacion_id),
            "tipo": "SOLICITAR_COMPRA",
            "creada_local_en": ahora_local.isoformat(),
            "empresa_id": str(escenario.empresa_a_id),
            "usuario_id": str(escenario.usuario_a.id),
            "dispositivo_id": str(disp_id),
            "secuencia_local": 20,
            "referencia_horaria_id": str(ref_id),
            "datos": {
                "sucursal_id": str(escenario.sucursal_a_id),
                "modalidad": "RECOJO",
                "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
                "autorizacion_cobro": {
                    "consentimiento_id": str(cid),
                    "aceptado_local_en": ahora_local.isoformat(),
                    "huella_compra": huella,
                    "base_bob": "100.00",
                    "descuento_bob": "0.00",
                    "envio_bob": "0.00",
                    "total_bob": "100.00",
                    "moneda_cobro": "USD",
                    "importe_cobro": str(usd_cobro),
                    "tasa_id": str(tasa_id),
                    "tasa_bob_por_usd": str(tasa_val),
                    "condiciones_version": "v3",
                    "vigente_hasta": (ahora_local + timedelta(hours=24)).isoformat(),
                    "preparacion_pago_id": str(metodo_prep_id),
                    "permite_cobro_al_reconectar": True,
                },
            },
        }

        # 1. Enviar compra offline que queda pendiente de 3DS
        resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
        assert resp.status_code == 200, resp.text
        res = resp.json()
        assert res["estado"] == "REQUIERE_ACCION_CLIENTE"
        pedido_id = uuid.UUID(res["recurso_id"])

        async with fabrica_sesiones() as db:
            stmt_ord = select(OrdenPago).where(OrdenPago.contexto == "PEDIDO", OrdenPago.pedido_id == pedido_id)
            ord_pago = (await db.execute(stmt_ord)).scalars().first()
            assert ord_pago is not None
            pi_id = ord_pago.referencia_externa

            # Leer inventario previo
            stmt_inv = select(InventarioSucursal).where(
                InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                InventarioSucursal.variante_id == escenario.variante_a_id,
            )
            inv_inicial = (await db.execute(stmt_inv)).scalars().first()
            disp_inicial = inv_inicial.disponible
            res_inicial = inv_inicial.reservado

        # 2. Primer webhook firmado confirmando captura en Stripe
        cuerpo_webhook = json.dumps({
            "id": f"evt_test_{uuid.uuid4().hex[:6]}",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": pi_id,
                    "amount": ord_pago.centavos_usd,
                    "currency": "usd",
                    "metadata": {
                        "empresa_id": str(ord_pago.empresa_id),
                        "pedido_id": str(pedido_id),
                    },
                }
            },
        }).encode("utf-8")
        ts = int(time.time())
        firma = generar_firma_stripe(cuerpo_webhook, settings.STRIPE_WEBHOOK_SECRET or "whsec_test", ts)

        r_wh1 = await http.cliente.post(
            "/api/v1/pagos/stripe/webhook",
            content=cuerpo_webhook,
            headers={"Stripe-Signature": firma, "Content-Type": "application/json"},
        )
        assert r_wh1.status_code == 200, r_wh1.text
        assert r_wh1.json()["estado"] == "APROBADO"

        # Verificar que el pedido pasó a PAGADO y se comprometió el inventario exactamente una vez
        async with fabrica_sesiones() as db:
            pedido = await db.get(PedidoCompra, pedido_id)
            assert pedido.estado_pago == "PAGADO"
            assert pedido.estado == "CONFIRMADO"
            assert pedido.estado_cumplimiento == "COMPROMETIDO"

            inv_tras_wh1 = (await db.execute(stmt_inv)).scalars().first()
            assert inv_tras_wh1.disponible == disp_inicial - 1
            assert inv_tras_wh1.reservado == res_inicial + 1

        # 3. Segundo webhook firmado (duplicado/reintento de red)
        r_wh2 = await http.cliente.post(
            "/api/v1/pagos/stripe/webhook",
            content=cuerpo_webhook,
            headers={"Stripe-Signature": firma, "Content-Type": "application/json"},
        )
        assert r_wh2.status_code == 200, r_wh2.text
        assert r_wh2.json()["estado"] == "APROBADO"

        # Verificar que NO se volvió a descontar inventario
        async with fabrica_sesiones() as db:
            inv_tras_wh2 = (await db.execute(stmt_inv)).scalars().first()
            assert inv_tras_wh2.disponible == disp_inicial - 1
            assert inv_tras_wh2.reservado == res_inicial + 1

        # 4. Reintento de la operación offline original: devuelve resultado durable sin duplicar
        r_reintento = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
        assert r_reintento.status_code == 200, r_reintento.text
        res_reint = r_reintento.json()
        assert res_reint["operacion_id"] == str(operacion_id)

        async with fabrica_sesiones() as db:
            inv_final = (await db.execute(stmt_inv)).scalars().first()
            assert inv_final.disponible == disp_inicial - 1
            assert inv_final.reservado == res_inicial + 1
    finally:
        configurar_fake_stripe.simular_requiere_accion = False


@pytest.mark.asyncio
async def test_cu05_solicitar_compra_cambio_precio_requiere_nueva_aceptacion(http, escenario, fabrica_sesiones):
    """CU05: Diferencia en precio central vs visto offline da REQUIERE_NUEVA_ACEPTACION."""
    http.usar(escenario.usuario_a)

    disp_id = uuid.uuid4()
    resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
    ref_id = resp_ref.json()["referencia_horaria_id"]
    ahora_local = datetime.now(timezone.utc)
    metodo_prep_id = uuid.uuid4()

    async with fabrica_sesiones() as db:
        mp = MetodoPreparado(
            id=metodo_prep_id,
            empresa_id=escenario.empresa_a_id,
            cliente_id=escenario.usuario_a.id,
            proveedor="STRIPE",
            cliente_proveedor_cifrado=b"cus_test",
            metodo_proveedor_cifrado=b"pm_test",
            preparacion_proveedor_cifrado=b"seti_test",
            estado="LISTO",
        )
        db.add(mp)
        r_t = await db.execute(select(text("id, tasa_bob_por_usd FROM plataforma.tasas_cambio ORDER BY vigente_desde DESC LIMIT 1")))
        f_t = r_t.first()
        tasa_id = f_t[0] if f_t else uuid.uuid4()
        tasa_val = Decimal(str(f_t[1])) if f_t else Decimal("6.96")
        await db.commit()

    cid = uuid.uuid4()
    usd_cobro = (Decimal("80.00") / tasa_val).quantize(Decimal("0.01"))
    huella = hashlib.sha256(f"{cid}:80.00:USD:{metodo_prep_id}".encode("utf-8")).hexdigest()

    op_payload = {
        "version_esquema": 3,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 30,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "autorizacion_cobro": {
                "consentimiento_id": str(cid),
                "aceptado_local_en": ahora_local.isoformat(),
                "huella_compra": huella,
                "base_bob": "80.00",
                "descuento_bob": "0.00",
                "envio_bob": "0.00",
                "total_bob": "80.00",
                "moneda_cobro": "USD",
                "importe_cobro": str(usd_cobro),
                "tasa_id": str(tasa_id),
                "tasa_bob_por_usd": str(tasa_val),
                "condiciones_version": "v3",
                "vigente_hasta": (ahora_local + timedelta(hours=24)).isoformat(),
                "preparacion_pago_id": str(metodo_prep_id),
                "permite_cobro_al_reconectar": True,
            },
        },
    }

    resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["estado"] == "REQUIERE_NUEVA_ACEPTACION"
    assert res["codigo"] == "PRECIO_CAMBIADO"


@pytest.mark.asyncio
async def test_cu05_solicitar_compra_falta_consentimiento_da_pendiente_intervencion(http, escenario):
    """CU05: Sin consentimiento explícito o sin método preparado se omite autorizacion_cobro y da PENDIENTE_INTERVENCION;
    si se envía un objeto parcial presente, devuelve 422 Unprocessable Entity según contrato v3."""
    http.usar(escenario.usuario_a)

    disp_id = uuid.uuid4()
    resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
    ref_id = resp_ref.json()["referencia_horaria_id"]
    ahora_local = datetime.now(timezone.utc)

    # Caso A: Objeto autorizacion_cobro omitido -> Solicitud guardada sin cobro en PENDIENTE_INTERVENCION
    op_payload_sin_cobro = {
        "version_esquema": 3,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 31,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            # autorizacion_cobro omitida
        },
    }

    resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload_sin_cobro)
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["estado"] == "PENDIENTE_INTERVENCION"
    assert res["codigo"] == "AUTORIZACION_REQUERIDA"

    # Caso B: Objeto autorizacion_cobro presente pero parcial/inválido -> Rechazo estricto HTTP 422
    op_payload_invalido = {
        "version_esquema": 3,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "secuencia_local": 32,
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
            "autorizacion_cobro": {
                "consentimiento": False,
            },
        },
    }

    resp_inv = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload_invalido)
    assert resp_inv.status_code == 422, resp_inv.text


@pytest.mark.asyncio
async def test_cu05_solicitar_compra_simular_3ds_da_requiere_accion_cliente(
    http, escenario, fabrica_sesiones, configurar_fake_stripe
):
    """CU05: Si el proveedor exige verificación da REQUIERE_ACCION_CLIENTE determinado por la pasarela."""
    http.usar(escenario.usuario_a)

    configurar_fake_stripe.simular_requiere_accion = True
    try:
        disp_id = uuid.uuid4()
        resp_ref = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
        ref_id = resp_ref.json()["referencia_horaria_id"]
        ahora_local = datetime.now(timezone.utc)

        metodo_prep_id = uuid.uuid4()
        async with fabrica_sesiones() as db:
            mp = MetodoPreparado(
                id=metodo_prep_id,
                empresa_id=escenario.empresa_a_id,
                cliente_id=escenario.usuario_a.id,
                proveedor="STRIPE",
                cliente_proveedor_cifrado=b"cus_test",
                metodo_proveedor_cifrado=b"pm_test",
                preparacion_proveedor_cifrado=b"seti_test",
                estado="LISTO",
            )
            db.add(mp)
            r_t = await db.execute(select(text("id, tasa_bob_por_usd FROM plataforma.tasas_cambio ORDER BY vigente_desde DESC LIMIT 1")))
            f_t = r_t.first()
            tasa_id = f_t[0] if f_t else uuid.uuid4()
            tasa_val = Decimal(str(f_t[1])) if f_t else Decimal("6.96")
            await db.commit()

        cid = uuid.uuid4()
        usd_cobro = (Decimal("100.00") / tasa_val).quantize(Decimal("0.01"))
        expira_en_calc = ahora_local + timedelta(hours=24)
        huella = calcular_huella_compra_canonica(
            empresa_id=escenario.empresa_a_id,
            usuario_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            modalidad="RECOJO",
            direccion=None,
            lineas=[{"variante_id": str(escenario.variante_a_id), "cantidad": 1, "precio_unitario_bob": "100.00"}],
            base_bob=Decimal("100.00"),
            descuento_bob=Decimal("0.00"),
            envio_bob=Decimal("0.00"),
            total_bob=Decimal("100.00"),
            moneda_cobro="USD",
            importe_cobro=usd_cobro,
            tasa_id=tasa_id,
            tasa_bob_por_usd=tasa_val,
            condiciones_version="v3",
            vigente_hasta=expira_en_calc,
        )

        op_payload = {
            "version_esquema": 3,
            "operacion_id": str(uuid.uuid4()),
            "tipo": "SOLICITAR_COMPRA",
            "creada_local_en": ahora_local.isoformat(),
            "empresa_id": str(escenario.empresa_a_id),
            "usuario_id": str(escenario.usuario_a.id),
            "dispositivo_id": str(disp_id),
            "secuencia_local": 32,
            "referencia_horaria_id": str(ref_id),
            "datos": {
                "sucursal_id": str(escenario.sucursal_a_id),
                "modalidad": "RECOJO",
                "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
                "autorizacion_cobro": {
                    "consentimiento_id": str(cid),
                    "aceptado_local_en": ahora_local.isoformat(),
                    "huella_compra": huella,
                    "base_bob": "100.00",
                    "descuento_bob": "0.00",
                    "envio_bob": "0.00",
                    "total_bob": "100.00",
                    "moneda_cobro": "USD",
                    "importe_cobro": str(usd_cobro),
                    "tasa_id": str(tasa_id),
                    "tasa_bob_por_usd": str(tasa_val),
                    "condiciones_version": "v3",
                    "vigente_hasta": (ahora_local + timedelta(hours=24)).isoformat(),
                    "preparacion_pago_id": str(metodo_prep_id),
                    "permite_cobro_al_reconectar": True,
                },
            },
        }

        resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
        assert resp.status_code == 200, resp.text
        res = resp.json()
        assert res["estado"] == "REQUIERE_ACCION_CLIENTE"
        assert res["codigo"] == "ACCION_CLIENTE_REQUERIDA"
    finally:
        configurar_fake_stripe.simular_requiere_accion = False


@pytest.mark.asyncio
async def test_huella_compra_canonica_vectores_publicos_y_sensibilidad():
    """P1 Auditoría 23: Verifica vectores canónicos públicos e invariantes de huella."""
    from datetime import datetime, timezone
    # Vector 1 (RECOJO)
    h1 = calcular_huella_compra_canonica(
        empresa_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        usuario_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        sucursal_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        modalidad="RECOJO",
        direccion=None,
        lineas=[{"variante_id": "22222222-2222-2222-2222-222222222222", "cantidad": 1, "precio_unitario_bob": "100.00"}],
        base_bob=Decimal("100.00"),
        descuento_bob=Decimal("0.00"),
        envio_bob=Decimal("0.00"),
        total_bob=Decimal("100.00"),
        moneda_cobro="USD",
        importe_cobro=Decimal("14.37"),
        tasa_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        tasa_bob_por_usd=Decimal("6.96"),
        condiciones_version="v3",
        vigente_hasta=datetime(2026, 11, 6, 15, 0, 0, tzinfo=timezone.utc),
    )
    assert h1 == "5249e0cea418ec6262f9f0ef7a71686d2d6cecf8c4083dafe77aa0d24c3eacee"

    # Vector 2 (DELIVERY con dirección y espacios a colapsar)
    h2 = calcular_huella_compra_canonica(
        empresa_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        usuario_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        sucursal_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        modalidad="DELIVERY",
        direccion="  Av.  Las   Americas  123 ",
        lineas=[{"variante_id": "22222222-2222-2222-2222-222222222222", "cantidad": 1, "precio_unitario_bob": "100.00"}],
        base_bob=Decimal("100.00"),
        descuento_bob=Decimal("0.00"),
        envio_bob=Decimal("15.00"),
        total_bob=Decimal("115.00"),
        moneda_cobro="USD",
        importe_cobro=Decimal("16.52"),
        tasa_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        tasa_bob_por_usd=Decimal("6.96"),
        condiciones_version="v3",
        vigente_hasta=datetime(2026, 11, 6, 15, 0, 0, tzinfo=timezone.utc),
    )
    assert h2 == "b095703bdd526b2a7da5d97f5e52dbe7ec7a118d72511c72b9602cd03fd98f07"

    # Sensibilidad: cambiar cualquier campo produce un hash distinto
    h_dif_cant = calcular_huella_compra_canonica(
        empresa_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        usuario_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        sucursal_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        modalidad="RECOJO",
        direccion=None,
        lineas=[{"variante_id": "22222222-2222-2222-2222-222222222222", "cantidad": 2, "precio_unitario_bob": "100.00"}],
        base_bob=Decimal("100.00"),
        descuento_bob=Decimal("0.00"),
        envio_bob=Decimal("0.00"),
        total_bob=Decimal("100.00"),
        moneda_cobro="USD",
        importe_cobro=Decimal("14.37"),
        tasa_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        tasa_bob_por_usd=Decimal("6.96"),
        condiciones_version="v3",
        vigente_hasta=datetime(2026, 11, 6, 15, 0, 0, tzinfo=timezone.utc),
    )
    assert h_dif_cant != h1


# ============================================================================
# CU05 Auditoría 28: Pruebas estrictas de contrato de autorización offline v3
# ============================================================================

async def _obtener_referencia_horaria(http, escenario):
    disp_id = uuid.uuid4()
    resp = await http.cliente.get(f"/api/v1/sincronizacion/referencia-horaria?dispositivo_id={disp_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()["referencia_horaria_id"], disp_id, datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_cu05_solicitar_compra_v3_extra_fields_rechazados_422(http, escenario):
    """P0 Auditoría 28: El DTO AutorizacionCobroV3DTO usa extra='forbid'.
    Campos como 'consentimiento', 'metodo_preparado_id' o 'huella_dispositivo'
    deben ser rechazados con HTTP 422 por FastAPI."""
    http.usar(escenario.usuario_a)

    ref_id, disp_id, ahora_local = await _obtener_referencia_horaria(http, escenario)

    op_payload = {
        "version_esquema": 3,
        "operacion_id": str(uuid.uuid4()),
        "secuencia_local": 1,
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": "100.00",
                }
            ],
            "autorizacion_cobro": {
                "consentimiento_id": str(uuid.uuid4()),
                "aceptado_local_en": ahora_local.isoformat(),
                "huella_compra": "0" * 64,
                "base_bob": "100.00",
                "descuento_bob": "0.00",
                "envio_bob": "0.00",
                "total_bob": "100.00",
                "moneda_cobro": "USD",
                "importe_cobro": "14.37",
                "tasa_id": str(uuid.uuid4()),
                "tasa_bob_por_usd": "6.96",
                "condiciones_version": "v3",
                "vigente_hasta": (ahora_local + timedelta(hours=24)).isoformat(),
                "preparacion_pago_id": str(uuid.uuid4()),
                "permite_cobro_al_reconectar": True,
                # Claves prohibidas que la PWA generaba antes de la corrección
                "consentimiento": True,
                "metodo_preparado_id": str(uuid.uuid4()),
                "huella_dispositivo": "dev_test_123",
            },
        },
    }

    resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
    assert resp.status_code == 422, resp.text
    detalles = str(resp.json())
    assert "extra_forbidden" in detalles or "extra" in detalles.lower()


@pytest.mark.asyncio
async def test_cu05_solicitar_compra_v3_moneda_ausente_rechazada_422(http, escenario):
    """P0 Auditoría 28: 'moneda_cobro' es obligatoria en v3 y no debe tener default;
    su omisión debe provocar HTTP 422."""
    http.usar(escenario.usuario_a)

    ref_id, disp_id, ahora_local = await _obtener_referencia_horaria(http, escenario)

    op_payload = {
        "version_esquema": 3,
        "operacion_id": str(uuid.uuid4()),
        "secuencia_local": 1,
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": "100.00",
                }
            ],
            "autorizacion_cobro": {
                "consentimiento_id": str(uuid.uuid4()),
                "aceptado_local_en": ahora_local.isoformat(),
                "huella_compra": "0" * 64,
                "base_bob": "100.00",
                "descuento_bob": "0.00",
                "envio_bob": "0.00",
                "total_bob": "100.00",
                # 'moneda_cobro' omitida intencionalmente
                "importe_cobro": "14.37",
                "tasa_id": str(uuid.uuid4()),
                "tasa_bob_por_usd": "6.96",
                "condiciones_version": "v3",
                "vigente_hasta": (ahora_local + timedelta(hours=24)).isoformat(),
                "preparacion_pago_id": str(uuid.uuid4()),
                "permite_cobro_al_reconectar": True,
            },
        },
    }

    resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_cu05_solicitar_compra_v3_omision_autorizacion_persiste_pendiente_intervencion(http, escenario):
    """P0 Auditoría 28: Sin autorización (o con autorizacion_cobro null), se encola
    v3 y persiste PENDIENTE_INTERVENCION sin cobrar nada."""
    http.usar(escenario.usuario_a)

    ref_id, disp_id, ahora_local = await _obtener_referencia_horaria(http, escenario)

    op_payload = {
        "version_esquema": 3,
        "operacion_id": str(uuid.uuid4()),
        "secuencia_local": 1,
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": str(disp_id),
        "tipo": "SOLICITAR_COMPRA",
        "creada_local_en": ahora_local.isoformat(),
        "referencia_horaria_id": str(ref_id),
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad": "RECOJO",
            "lineas": [
                {
                    "variante_id": str(escenario.variante_a_id),
                    "cantidad": 1,
                    "precio_unitario_bob": "100.00",
                }
            ],
            "autorizacion_cobro": None,
        },
    }

    resp = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=op_payload)
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["estado"] == "PENDIENTE_INTERVENCION"
    assert res["codigo"] == "AUTORIZACION_REQUERIDA"
