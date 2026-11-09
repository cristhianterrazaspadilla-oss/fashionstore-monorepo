"""Pruebas del Lote B3: Posventa (CU20 y CU08).

Cubre:
- CU20: Devolución y Merma:
  - Solicitud de devolución dentro de los 15 días (custodia no vendible).
  - Inspección técnica: APROBADA_REPOSICION (reingreso de stock con Kardex DEVOLUCION),
    APROBADA_REEMBOLSO (custodia sin disponible) y RECHAZADA.
  - Merma auditada con reducción de inventario disponible y Kardex MERMA.
- CU08: Cambio de prenda y resolución de diferencia:
  - Solicitud de cambio dentro de 15 días, emisión de nota por 7 días, cálculo de diferencia.
  - Resolución financiera: exclusión estricta de reemplazo y saldo/reembolso simultáneos.
  - Diferencia a favor de la tienda exige PAGO_CLIENTE.
  - Diferencia a favor del cliente permite SALDO o REEMBOLSO exclusivos.
  - Prevención de cambio duplicado sobre la misma unidad.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Tuple

import pytest
from sqlalchemy import select

from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.posventa.services.cambio_service import Cambio, DetalleCambio, MovimientoSaldo
from backend.app.core.modules.posventa.services.devolucion_service import Devolucion, DetalleDevolucion
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Venta
from backend.app.core.modules.ventas_pagos.services.pedido_service import ObligacionReembolso


async def _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=3) -> Tuple[uuid.UUID, uuid.UUID]:
    """Helper para crear una venta PAGADA y ENTREGADA en base de datos para pruebas de posventa."""
    async with fabrica_sesiones() as db:
        venta_id = uuid.uuid4()
        det_id = uuid.uuid4()

        venta = Venta(
            id=venta_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PAGADA",
            subtotal=Decimal("100.00") * cantidad,
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00") * cantidad,
            creada_en=escenario.usuario_a.creado_en,
            confirmada_en=escenario.usuario_a.creado_en,
            entregada_en=escenario.usuario_a.creado_en,
        )
        db.add(venta)

        det = DetalleVenta(
            id=det_id,
            venta_id=venta_id,
            variante_id=escenario.variante_a_id,
            cantidad=cantidad,
            precio_unitario=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_promedio=Decimal("40.00"),
        )
        db.add(det)
        await db.commit()
        return venta_id, det_id


async def _crear_venta_custom(
    escenario, fabrica_sesiones, cantidad=3, entregada: bool = True, dias_antiguedad: int = 0
) -> Tuple[uuid.UUID, uuid.UUID]:
    """Helper para crear ventas con fecha de entrega controlada o sin entrega para pruebas de plazos."""
    async with fabrica_sesiones() as db:
        venta_id = uuid.uuid4()
        det_id = uuid.uuid4()
        ahora = datetime.now(timezone.utc)
        fecha_creacion = ahora - timedelta(days=dias_antiguedad)
        fecha_entrega = (ahora - timedelta(days=dias_antiguedad)) if entregada else None

        venta = Venta(
            id=venta_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"VTA-TEST-{uuid.uuid4().hex[:6]}",
            cliente_id=escenario.usuario_a.id,
            sucursal_id=escenario.sucursal_a_id,
            cajero_id=escenario.usuario_admin_a.id,
            canal="PRESENCIAL",
            estado="PAGADA",
            subtotal=Decimal("100.00") * cantidad,
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00") * cantidad,
            creada_en=fecha_creacion,
            confirmada_en=fecha_creacion,
            entregada_en=fecha_entrega,
        )
        db.add(venta)

        det = DetalleVenta(
            id=det_id,
            venta_id=venta_id,
            variante_id=escenario.variante_a_id,
            cantidad=cantidad,
            precio_unitario=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_promedio=Decimal("40.00"),
        )
        db.add(det)
        await db.commit()
        return venta_id, det_id


# ============================================================================
# CU20: DEVOLUCIÓN Y MERMA
# ============================================================================

@pytest.mark.asyncio
async def test_cu20_solicitar_devolucion_crea_solicitud_en_custodia(http, escenario, fabrica_sesiones):
    """CU20: Solicitar devolución física deja la prenda en custodia (SOLICITADA) sin alterar stock."""
    venta_id, det_id = await _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=3)

    # Stock antes
    async with fabrica_sesiones() as db:
        stmt = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_antes = (await db.execute(stmt)).scalars().first()
        disponible_antes = inv_antes.disponible

    http.usar(escenario.usuario_a)
    clave = uuid.uuid4()
    resp = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 2}],
            "motivo_codigo": "TALLA",
            "motivo_descripcion": "Talla demasiado grande",
        },
        headers={"Idempotency-Key": str(clave)},
    )
    assert resp.status_code == 201, resp.text
    dev = resp.json()

    assert dev["id"] is not None
    assert dev["estado"] == "SOLICITADA"
    assert dev["motivo_codigo"] == "TALLA"
    assert len(dev["detalles"]) == 1
    assert dev["detalles"][0]["cantidad_solicitada"] == 2
    assert dev["detalles"][0]["cantidad_recibida"] == 0

    # Stock no se modifica en solicitud (la prenda entra en custodia previa inspección)
    async with fabrica_sesiones() as db:
        inv_despues = (await db.execute(stmt)).scalars().first()
        assert inv_despues.disponible == disponible_antes


@pytest.mark.asyncio
async def test_cu20_solicitar_devolucion_excede_vendido_falla_409(http, escenario, fabrica_sesiones):
    """CU20: Solicitar devolver más de lo vendido en la línea devuelve 409 Conflict."""
    venta_id, det_id = await _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=2)

    http.usar(escenario.usuario_a)
    resp = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 5}],
            "motivo_codigo": "TALLA",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_cu20_inspeccion_aprobada_reposicion_reingresa_stock_y_kardex(
    http, escenario, fabrica_sesiones
):
    """CU20: Inspección técnica con dictamen APROBADA_REPOSICION reingresa stock y emite Kardex DEVOLUCION."""
    venta_id, det_id = await _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=2)

    # 1. Crear solicitud por cliente
    http.usar(escenario.usuario_a)
    resp_sol = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "motivo_codigo": "COLOR",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_sol.status_code == 201
    devolucion_id = resp_sol.json()["id"]

    # Stock antes de inspección
    async with fabrica_sesiones() as db:
        stmt = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        inv_antes = (await db.execute(stmt)).scalars().first()
        disponible_antes = inv_antes.disponible

    # 2. Inspección por Encargado / Admin
    http.usar(escenario.usuario_admin_a)
    resp_insp = await http.cliente.post(
        f"/api/v1/devoluciones/{devolucion_id}/inspecciones",
        json={
            "condicion_fisica": "BUENA",
            "responsabilidad_tienda": True,
            "dictamen": "APROBADA_REPOSICION",
            "observaciones": "Prenda en estado óptimo con etiquetas",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_insp.status_code == 200, resp_insp.text
    dev_insp = resp_insp.json()

    assert dev_insp["estado"] == "APROBADA_REPOSICION"
    assert dev_insp["detalles"][0]["cantidad_aceptada"] == 1

    # Verificar que el inventario disponible aumentó en 1
    async with fabrica_sesiones() as db:
        inv_despues = (await db.execute(stmt)).scalars().first()
        assert inv_despues.disponible == disponible_antes + 1

        # Verificar Kardex DEVOLUCION emitido
        stmt_k = select(MovimientoInventario).where(
            MovimientoInventario.tipo == "DEVOLUCION",
            MovimientoInventario.referencia_tipo == "DETALLE_VENTA",
            MovimientoInventario.referencia_id == det_id,
        )
        mov = (await db.execute(stmt_k)).scalars().first()
        assert mov is not None
        assert mov.cantidad == 1


@pytest.mark.asyncio
async def test_cu20_inspeccion_aprobada_reembolso_queda_en_custodia_sin_disponible(
    http, escenario, fabrica_sesiones
):
    """CU20: Dictamen APROBADA_REEMBOLSO aprueba la devolución pero no reingresa stock vendible."""
    venta_id, det_id = await _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=2)

    http.usar(escenario.usuario_a)
    resp_sol = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "motivo_codigo": "DEFECTO_FABRICACION",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    devolucion_id = resp_sol.json()["id"]

    async with fabrica_sesiones() as db:
        stmt = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        disponible_antes = (await db.execute(stmt)).scalars().first().disponible

    http.usar(escenario.usuario_admin_a)
    resp_insp = await http.cliente.post(
        f"/api/v1/devoluciones/{devolucion_id}/inspecciones",
        json={
            "condicion_fisica": "DEFECTUOSA",
            "responsabilidad_tienda": True,
            "dictamen": "APROBADA_REEMBOLSO",
            "observaciones": "Costura rota de fábrica",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_insp.status_code == 200, resp_insp.text
    assert resp_insp.json()["estado"] == "APROBADA_REEMBOLSO"

    # Stock vendible NO debe aumentar
    async with fabrica_sesiones() as db:
        disponible_despues = (await db.execute(stmt)).scalars().first().disponible
        assert disponible_despues == disponible_antes


@pytest.mark.asyncio
async def test_cu20_merma_reduce_disponible_y_emite_kardex(http, escenario, fabrica_sesiones):
    """CU20: Merma auditada reduce inventario disponible y emite Kardex MERMA."""
    http.usar(escenario.usuario_admin_a)

    async with fabrica_sesiones() as db:
        stmt = select(InventarioSucursal).where(
            InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
            InventarioSucursal.variante_id == escenario.variante_a_id,
        )
        disponible_antes = (await db.execute(stmt)).scalars().first().disponible

    resp = await http.cliente.post(
        "/api/v1/mermas",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "variante_id": str(escenario.variante_a_id),
            "cantidad": 1,
            "motivo_codigo": "PRENDA_DANADA_HUMEDAD",
            "descripcion": "Daño accidental en depósito",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 201, resp.text
    merma = resp.json()

    assert merma["id"] is not None
    assert merma["cantidad"] == 1

    # Verificar reducción en disponible
    async with fabrica_sesiones() as db:
        disponible_despues = (await db.execute(stmt)).scalars().first().disponible
        assert disponible_despues == disponible_antes - 1

        # Kardex MERMA
        stmt_m = select(MovimientoInventario).where(
            MovimientoInventario.id == uuid.UUID(merma["id"]),
            MovimientoInventario.tipo == "MERMA",
        )
        mov = (await db.execute(stmt_m)).scalars().first()
        assert mov is not None
        assert mov.cantidad == 1


# ============================================================================
# CU08: CAMBIO DE PRENDA Y RESOLUCIÓN DE DIFERENCIA
# ============================================================================

@pytest.mark.asyncio
async def test_cu08_solicitar_cambio_emite_nota_7_dias_y_calcula_diferencia_cero(
    http, escenario, fabrica_sesiones
):
    """CU08: Solicitar cambio de prenda calcula valor reconocido, cotiza reemplazo y emite nota por 7 días."""
    venta_id, det_id = await _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=2)

    http.usar(escenario.usuario_a)
    clave = uuid.uuid4()
    resp = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [{"variante_id": str(escenario.variante_ultima_id), "cantidad": 1}],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "TALLA",
        },
        headers={"Idempotency-Key": str(clave)},
    )
    assert resp.status_code == 201, resp.text
    cambio = resp.json()

    assert cambio["cambio_id"] is not None
    assert cambio["nota_codigo"].startswith("CAMB-")
    assert cambio["estado"] == "SOLICITADO"
    # Prenda original valía 100, reemplazo vale 100 -> diferencia 0
    assert float(cambio["valor_reconocido_bob"]) == 100.0
    assert float(cambio["diferencia_bob"]) == 0.0
    assert cambio["vence_espera_en"] is not None


@pytest.mark.asyncio
async def test_cu08_resolver_diferencia_cero_sin_diferencia(http, escenario, fabrica_sesiones):
    """CU08: Con diferencia monetaria cero, se resuelve con destino SIN_DIFERENCIA."""
    venta_id, det_id = await _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=1)

    http.usar(escenario.usuario_a)
    resp_sol = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [{"variante_id": str(escenario.variante_ultima_id), "cantidad": 1}],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "COLOR",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    cambio_id = resp_sol.json()["cambio_id"]

    resp_res = await http.cliente.post(
        f"/api/v1/cambios/{cambio_id}/resolver-diferencia",
        json={"destino_diferencia": "SIN_DIFERENCIA"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_res.status_code == 200, resp_res.text
    assert resp_res.json()["estado"] == "RESUELTO"


@pytest.mark.asyncio
async def test_cu08_cambio_sin_reemplazo_permite_saldo_o_reembolso_exclusivos(
    http, escenario, fabrica_sesiones
):
    """CU08: Cambio sin reemplazo (nota sin stock sustituto) acredita SALDO o REEMBOLSO (nunca ambos)."""
    venta_id, det_id = await _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=1)

    http.usar(escenario.usuario_a)
    # Solicitud sin prendas de reemplazo
    resp_sol = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "DEFECTO_FABRICACION",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    cambio_id = resp_sol.json()["cambio_id"]
    assert float(resp_sol.json()["valor_reconocido_bob"]) == 100.0

    # Resolver como SALDO
    resp_res = await http.cliente.post(
        f"/api/v1/cambios/{cambio_id}/resolver-diferencia",
        json={"destino_diferencia": "SALDO"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_res.status_code == 200, resp_res.text
    assert resp_res.json()["estado"] == "RESUELTO"

    # Verificar crédito en comercial.movimientos_saldo
    async with fabrica_sesiones() as db:
        stmt_s = select(MovimientoSaldo).where(
            MovimientoSaldo.origen_tipo == "CAMBIO",
            MovimientoSaldo.origen_id == uuid.UUID(cambio_id),
        )
        saldo_mov = (await db.execute(stmt_s)).scalars().first()
        assert saldo_mov is not None
        assert saldo_mov.monto_bob == Decimal("100.00")
        assert saldo_mov.tipo == "CREDITO"

        # Verificar que NO se creó obligación de reembolso simultánea (regla estricta de exclusión)
        stmt_r = select(ObligacionReembolso).where(
            ObligacionReembolso.origen_tipo == "CAMBIO",
            ObligacionReembolso.origen_id == uuid.UUID(cambio_id),
        )
        reemb_mov = (await db.execute(stmt_r)).scalars().first()
        assert reemb_mov is None


@pytest.mark.asyncio
async def test_cu08_no_permite_cambio_duplicado_misma_unidad(http, escenario, fabrica_sesiones):
    """CU08: No se permite cambiar más unidades que las efectivamente vendidas en la venta original."""
    venta_id, det_id = await _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=1)

    http.usar(escenario.usuario_a)
    # Primer cambio consume la unidad
    resp1 = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "TALLA",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp1.status_code == 201

    # Segundo cambio sobre la misma línea vendida debe fallar con 409
    resp2 = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "TALLA",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp2.status_code == 409, resp2.text


# ============================================================================
# CU20 y CU08: PLAZOS, ENTREGA REAL, DEFECTOS Y RESOLUCIÓN EXCLUSIVA
# ============================================================================

@pytest.mark.asyncio
async def test_cu20_devolucion_sin_entrega_real_falla_voluntaria_pero_defecto_pasa_a_evaluacion(
    http, escenario, fabrica_sesiones
):
    """CU20: Venta sin entrega real (entregada_en=None) rechaza devolución voluntaria pero acepta defecto para evaluación."""
    # Venta pagada pero aún no entregada
    venta_id, det_id = await _crear_venta_custom(escenario, fabrica_sesiones, cantidad=2, entregada=False)

    http.usar(escenario.usuario_a)

    # 1. Devolución voluntaria (TALLA) debe fallar con 400
    resp_vol = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "motivo_codigo": "TALLA",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_vol.status_code == 400, resp_vol.text
    assert "no ha sido entregada" in resp_vol.json()["detail"].lower()

    # 2. Reclamo por DEFECTO_FABRICACION no se rechaza automáticamente; pasa a PENDIENTE_EVALUACION
    resp_def = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "motivo_codigo": "DEFECTO_FABRICACION",
            "motivo_descripcion": "Falla reportada en confección",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_def.status_code == 201, resp_def.text
    dev = resp_def.json()
    assert dev["estado"] == "PENDIENTE_EVALUACION"


@pytest.mark.asyncio
async def test_cu20_devolucion_tardia_voluntaria_falla_pero_producto_incorrecto_pasa_a_evaluacion(
    http, escenario, fabrica_sesiones
):
    """CU20: Venta entregada hace 25 días rechaza devolución voluntaria pero pasa PRODUCTO_INCORRECTO a PENDIENTE_EVALUACION."""
    venta_id, det_id = await _crear_venta_custom(
        escenario, fabrica_sesiones, cantidad=2, entregada=True, dias_antiguedad=25
    )

    http.usar(escenario.usuario_a)

    # 1. Voluntaria (COLOR) vencida (>15 días) falla con 400
    resp_vol = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "motivo_codigo": "COLOR",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_vol.status_code == 400, resp_vol.text
    assert "ha vencido" in resp_vol.json()["detail"].lower()

    # 2. Incumplimiento tardío (PRODUCTO_INCORRECTO) queda en PENDIENTE_EVALUACION
    resp_inc = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "motivo_codigo": "PRODUCTO_INCORRECTO",
            "motivo_descripcion": "Entregado modelo diferente al pedido",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_inc.status_code == 201, resp_inc.text
    dev_id = resp_inc.json()["id"]
    assert resp_inc.json()["estado"] == "PENDIENTE_EVALUACION"

    # 3. Encargado realiza inspección técnica sobre la solicitud en PENDIENTE_EVALUACION
    http.usar(escenario.usuario_admin_a)
    resp_insp = await http.cliente.post(
        f"/api/v1/devoluciones/{dev_id}/inspecciones",
        json={
            "condicion_fisica": "BUENA",
            "responsabilidad_tienda": True,
            "dictamen": "APROBADA_REPOSICION",
            "observaciones": "Se constata envío erróneo de prenda",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_insp.status_code == 200, resp_insp.text
    assert resp_insp.json()["estado"] == "APROBADA_REPOSICION"


@pytest.mark.asyncio
async def test_cu08_cambio_sin_entrega_real_falla_voluntario_pero_defecto_pasa_a_evaluacion(
    http, escenario, fabrica_sesiones
):
    """CU08: Venta no entregada (entregada_en=None) rechaza cambio voluntario pero registra defecto para evaluación."""
    venta_id, det_id = await _crear_venta_custom(escenario, fabrica_sesiones, cantidad=1, entregada=False)

    http.usar(escenario.usuario_a)

    # 1. Voluntario falla con 400
    resp_vol = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "TALLA",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_vol.status_code == 400, resp_vol.text
    assert "no ha sido entregada" in resp_vol.json()["detail"].lower()

    # 2. Defecto de fabricación pasa a PENDIENTE_EVALUACION
    resp_def = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "DEFECTO_FABRICACION",
            "motivo_descripcion": "Defecto en cremallera",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_def.status_code == 201, resp_def.text
    assert resp_def.json()["estado"] == "PENDIENTE_EVALUACION"


@pytest.mark.asyncio
async def test_cu08_cambio_tardio_voluntario_falla_pero_defecto_pasa_a_evaluacion_y_bloquea_resolucion_previa(
    http, escenario, fabrica_sesiones
):
    """CU08: Cambio entregado hace 20 días rechaza voluntario, acepta defecto en PENDIENTE_EVALUACION y bloquea resolución antes de evaluar."""
    venta_id, det_id = await _crear_venta_custom(
        escenario, fabrica_sesiones, cantidad=1, entregada=True, dias_antiguedad=20
    )

    http.usar(escenario.usuario_a)

    # 1. Voluntario falla por vencimiento de 15 días
    resp_vol = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "TALLA",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_vol.status_code == 400, resp_vol.text

    # 2. Defecto de fabricación pasa a PENDIENTE_EVALUACION
    resp_def = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "DEFECTO_FABRICACION",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_def.status_code == 201, resp_def.text
    cambio_id = resp_def.json()["cambio_id"]
    assert resp_def.json()["estado"] == "PENDIENTE_EVALUACION"

    # 3. Intentar resolver diferencia sin dictamen técnico previo debe fallar con 409
    resp_res = await http.cliente.post(
        f"/api/v1/cambios/{cambio_id}/resolver-diferencia",
        json={"destino_diferencia": "SALDO"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_res.status_code == 409, resp_res.text
    assert "pendiente_evaluacion" in resp_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cu20_cu08_exclusion_cruzada_devolucion_y_cambio_misma_unidad(
    http, escenario, fabrica_sesiones
):
    """CU20/CU08: No se puede solicitar devolución de una prenda que ya está solicitada en cambio (exclusión estricta)."""
    venta_id, det_id = await _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=1)

    http.usar(escenario.usuario_a)

    # 1. Cambiar la única unidad
    resp_camb = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "TALLA",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_camb.status_code == 201

    # 2. Intentar devolver la misma unidad en CU20 debe fallar con 409
    resp_dev = await http.cliente.post(
        "/api/v1/devoluciones/solicitudes",
        json={
            "venta_id": str(venta_id),
            "lineas": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "motivo_codigo": "COLOR",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_dev.status_code == 409, resp_dev.text
    assert "ya cambiado" in resp_dev.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cu08_resolucion_exclusiva_reembolso(http, escenario, fabrica_sesiones):
    """CU08: Resolver diferencia hacia REEMBOLSO crea ObligacionReembolso y NO crea MovimientoSaldo (mutua exclusión)."""
    venta_id, det_id = await _crear_venta_entregada(escenario, fabrica_sesiones, cantidad=1)

    http.usar(escenario.usuario_a)
    resp_sol = await http.cliente.post(
        "/api/v1/cambios",
        json={
            "venta_id": str(venta_id),
            "lineas_originales": [{"detalle_venta_id": str(det_id), "cantidad": 1}],
            "reemplazos": [],
            "sucursal_id": str(escenario.sucursal_a_id),
            "modalidad_reemplazo": "RECOJO",
            "motivo_codigo": "COLOR",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    cambio_id = resp_sol.json()["cambio_id"]

    resp_res = await http.cliente.post(
        f"/api/v1/cambios/{cambio_id}/resolver-diferencia",
        json={"destino_diferencia": "REEMBOLSO"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_res.status_code == 200, resp_res.text
    assert resp_res.json()["estado"] == "RESUELTO"

    async with fabrica_sesiones() as db:
        # Verificar ObligacionReembolso creada
        stmt_r = select(ObligacionReembolso).where(
            ObligacionReembolso.origen_tipo == "CAMBIO",
            ObligacionReembolso.origen_id == uuid.UUID(cambio_id),
        )
        reemb = (await db.execute(stmt_r)).scalars().first()
        assert reemb is not None
        assert reemb.monto_bob == Decimal("100.00")

        # Verificar que NO se creó saldo simultáneo
        stmt_s = select(MovimientoSaldo).where(
            MovimientoSaldo.origen_tipo == "CAMBIO",
            MovimientoSaldo.origen_id == uuid.UUID(cambio_id),
        )
        saldo_mov = (await db.execute(stmt_s)).scalars().first()
        assert saldo_mov is None
