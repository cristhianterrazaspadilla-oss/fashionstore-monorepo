"""Suite de Pruebas de Contraejemplos P0: Auditoría 39 (CU19, CU22 y Worker de Expiración).

Cubre exhaustivamente los tres frentes críticos identificados en la Auditoría 39
y acordados en la interfaz compartida (R0):

1. P0-1: Worker de Expiración y Cancelación Segura de Ventas Vencidas (`cancelar_ventas_stripe_vencidas`):
   - a) Intención en requires_payment_method donde `cancelar_intencion` arroja error de red o timeout (503/502).
        Verifica que la venta permanece PENDIENTE_PAGO, la orden PENDIENTE, el stock comprometido_digital
        NO se libera, no se crea LIBERACION_DIGITAL en Kardex, y la venta queda en 'omitidas'.
   - b) Captura concurrente entre consulta y cancelación (`cancelar_intencion` arroja HTTP 400 o pasa a SUCCEEDED).
        Verifica que el stock NO se libera, no hay LIBERACION_DIGITAL, y la orden se sincroniza a CAPTURADO.

2. P0-2: Recuperación de Orden Activa de Caja (`GET /api/v1/pagos/stripe/ordenes/activa-caja`):
   - a) Contrato DTO completo (`OrdenActivaCajaDTO`): venta_id, stripe_payment_intent_id, tasa_bob_por_usd congelada,
        líneas completas con variante_id, cantidad, precio_unitario_bob, descuento_bob, sku, nombre_producto, y procedencia.
   - b) Autorización y aislamiento: tenant isolation (otra empresa), cajero ajeno no admin, turno no coincidente,
        y ordenamiento determinista ante múltiples órdenes activas (creada_en DESC, id DESC).

3. P0-3: Validación Financiera Rigurosa (`validar_intencion_con_orden`):
   - a) PaymentIntent ajeno (ID distinto): rechaza con 400, no marca CAPTURADO.
   - b) Moneda distinta (EUR en vez de USD): rechaza con 400, no marca CAPTURADO.
   - c) Centavos discrepantes: rechaza con 400, no marca CAPTURADO.
   - d) Metadata empresa_id faltante o ajena: rechaza con 400, no marca CAPTURADO.
   - e) Metadata venta_id faltante o ajena: rechaza con 400, no marca CAPTURADO.
   - f) Timeout / error de red en pasarela: no se oculta con pass; responde estado_verificacion='NO_VERIFICADO_ERROR_PASARELA'
        sin mutar la orden a CAPTURADO ni cancelar la venta.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import pytest
import pytest_asyncio
from fastapi import HTTPException, status
from sqlalchemy import select, text

from backend.app.core.modules.catalogo.models import Producto, VarianteProducto
from backend.app.core.modules.identidad_empresas.models import Empleado, Rol, Usuario
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.organizacion.models import TasaCambio
from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import (
    FakeStripeGateway,
    IntencionPago,
    fijar_gateway,
)
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Pago, TurnoCaja, Venta
from backend.app.core.modules.ventas_pagos.models_ordenes import (
    LineaRecuperadaCajaDTO,
    OrdenActivaCajaDTO,
    OrdenPago,
)
from backend.app.core.modules.ventas_pagos.services.stripe_service import StripeService
from backend.tests_segundo_parcial_bloque_b.conftest import usuario_simple


# =============================================================================
# FIXTURES Y HELPERS COMPARTIDOS
# =============================================================================

@pytest.fixture
def fake_stripe():
    """Configura una instancia limpia de FakeStripeGateway."""
    fake = FakeStripeGateway()
    fijar_gateway(fake)
    yield fake
    fijar_gateway(None)


@pytest_asyncio.fixture(autouse=True)
async def asegurar_tasa_vigente(fabrica_sesiones, escenario):
    """Garantiza una tasa de cambio vigente en plataforma.tasas_cambio para cotización USD."""
    async with fabrica_sesiones() as db:
        stmt = (
            select(TasaCambio)
            .where(TasaCambio.vigente_hasta.is_(None))
            .order_by(TasaCambio.vigente_desde.desc())
        )
        tasa = (await db.execute(stmt)).scalars().first()
        if tasa is None:
            ahora = datetime.now(timezone.utc)
            version_anterior = (
                await db.execute(select(TasaCambio.version).order_by(TasaCambio.version.desc()).limit(1))
            ).scalar_one_or_none()
            tasa = TasaCambio(
                id=uuid.uuid4(),
                version=(version_anterior or 0) + 1,
                tasa_bob_por_usd=Decimal("6.96000000"),
                vigente_desde=ahora - timedelta(days=30),
                vigente_hasta=None,
                motivo="Tasa vigente de prueba",
                creada_por=escenario.ids.get("superadmin"),
                creada_en=ahora - timedelta(days=30),
            )
            db.add(tasa)
            await db.commit()


async def _ejecutar_cancelacion_vencidas(
    servicio: StripeService,
    lote: int = 100,
    ahora_param: Optional[datetime] = None,
    empresa_id: Optional[uuid.UUID] = None,
    venta_id: Optional[uuid.UUID] = None,
) -> dict:
    """Invoca la rutina de cancelación de ventas vencidas (soporta alias contractual)."""
    if hasattr(servicio, "cancelar_ventas_stripe_vencidas"):
        return await servicio.cancelar_ventas_stripe_vencidas(
            lote=lote, ahora_param=ahora_param, empresa_id=empresa_id, venta_id=venta_id
        )
    return await servicio.cancelarVencidas(
        lote=lote, ahora_param=ahora_param, empresa_id=empresa_id, venta_id=venta_id
    )


async def _crear_usuario_cajero(
    fabrica_sesiones, empresa_id: uuid.UUID, sucursal_id: Optional[uuid.UUID] = None
):
    """Crea un usuario con rol CAJERO desacoplado para pruebas de caja asignado a una sucursal."""
    sufijo = uuid.uuid4().hex[:6]
    cajero_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        rol_cajero = (
            await db.execute(select(Rol).where(Rol.nombre == "CAJERO"))
        ).scalars().first()
        assert rol_cajero is not None, "El rol CAJERO debe existir en seguridad.roles"

        cajero = Usuario(
            id=cajero_id,
            empresa_id=empresa_id,
            rol_id=rol_cajero.id,
            rol=rol_cajero,
            nombres="Cajero",
            apellidos=f"Test {sufijo}",
            correo_electronico=f"cajero_{sufijo}@test.local",
            contrasenia_hash="no-usar",
            estado="ACTIVO",
        )
        db.add(cajero)
        await db.flush()

        if sucursal_id is not None:
            db.add(
                Empleado(
                    usuario_id=cajero_id,
                    sucursal_id=sucursal_id,
                    cargo="Cajero de Sucursal",
                    activo=True,
                )
            )
        await db.commit()

    from types import SimpleNamespace
    return SimpleNamespace(
        id=cajero_id,
        empresa_id=empresa_id,
        rol=SimpleNamespace(nombre="CAJERO"),
        empleado=SimpleNamespace(sucursal_id=sucursal_id) if sucursal_id else None,
        cliente=None,
    )


# =============================================================================
# P0-1: WORKER DE EXPIRACIÓN Y CANCELACIÓN SEGURA (P0-1a y P0-1b)
# =============================================================================

@pytest.mark.asyncio
async def test_p0_1a_cancelar_intencion_falla_red_timeout_no_libera_stock_ni_kardex_y_omite(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """P0-1a: Cuando cancelar_intencion arroja error de red o timeout (503/502):

    - La venta DEBE permanecer en PENDIENTE_PAGO.
    - La orden DEBE permanecer en PENDIENTE.
    - El stock comprometido_digital NO se libera (se mantiene intacto).
    - El stock disponible NO se incrementa.
    - NO se emite movimiento Kardex 'LIBERACION_DIGITAL'.
    - La venta se reporta dentro de 'omitidas' (no en 'canceladas').
    """
    http.usar(escenario.usuario_admin_a)

    # 1. Iniciar venta presencial Stripe legítima (1 unidad = 100 BOB)
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201, resp_init.text
    datos_init = resp_init.json()
    venta_id = uuid.UUID(datos_init["venta_id"])
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    pi_id = datos_init["stripe_payment_intent_id"]

    # 2. Forzar fecha de expiración en el pasado (vencida)
    ahora_utc = datetime.now(timezone.utc)
    vencida_hace = ahora_utc - timedelta(minutes=10)

    async with fabrica_sesiones() as db:
        venta_db = await db.get(Venta, venta_id)
        assert venta_db is not None
        venta_db.expira_en = vencida_hace
        await db.commit()

        # Medir inventario tras iniciar venta: comprometido_digital >= 1
        inv_antes = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                )
            )
        ).scalars().first()
        disp_antes = inv_antes.disponible
        comp_antes = inv_antes.comprometido_digital
        assert comp_antes >= 1

    # 3. Configurar doble de Stripe: consultar_intencion responde REQUIRES_PAYMENT_METHOD,
    # pero cancelar_intencion falla con timeout / 503 SERVICE UNAVAILABLE.
    fake_stripe.intenciones[pi_id].estado = "REQUIRES_PAYMENT_METHOD"

    class GatewayConFalloEnCancelacion(FakeStripeGateway):
        async def cancelar_intencion(self, payment_intent_id: str) -> IntencionPago:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "STRIPE_TIMEOUT", "mensaje": "Timeout de conexión simulado hacia Stripe"},
            )

    gw_fallo = GatewayConFalloEnCancelacion()
    gw_fallo.intenciones = fake_stripe.intenciones
    fijar_gateway(gw_fallo)

    # 4. Ejecutar el worker de cancelación
    async with fabrica_sesiones() as db:
        servicio = StripeService(db)
        res = await _ejecutar_cancelacion_vencidas(
            servicio, ahora_param=ahora_utc, venta_id=venta_id
        )

    # 5. Verificaciones estrictas de no-liberación en incertidumbre
    assert str(venta_id) in res.get("omitidas", []), f"Venta {venta_id} debe estar en omitidas: {res}"
    assert str(venta_id) not in res.get("canceladas", []), f"Venta {venta_id} NO debe estar en canceladas: {res}"

    async with fabrica_sesiones() as db:
        # Estado de venta y orden deben permanecer intactos
        venta_post = await db.get(Venta, venta_id)
        assert venta_post.estado == "PENDIENTE_PAGO", f"Venta pasó a {venta_post.estado}, debía ser PENDIENTE_PAGO"

        op_post = await db.get(OrdenPago, orden_pago_id)
        assert op_post.estado == "PENDIENTE", f"OrdenPago pasó a {op_post.estado}, debía ser PENDIENTE"

        # Inventario NO debe ser liberado
        inv_post = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                )
            )
        ).scalars().first()
        assert inv_post.comprometido_digital == comp_antes, "comprometido_digital no debió decrementar"
        assert inv_post.disponible == disp_antes, "disponible no debió incrementar"

        # Kardex: NO debe existir LIBERACION_DIGITAL para esta venta
        kardex = (
            await db.execute(
                select(MovimientoInventario).where(
                    MovimientoInventario.referencia_id == venta_id,
                    MovimientoInventario.tipo == "LIBERACION_DIGITAL",
                )
            )
        ).scalars().all()
        assert len(kardex) == 0, f"Se emitieron movimientos Kardex indebidos: {kardex}"


@pytest.mark.asyncio
async def test_p0_1b_captura_concurrente_entre_consulta_y_cancelacion_no_libera_stock_y_sincroniza_capturado(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """P0-1b: Captura concurrente entre la consulta y la cancelación:

    Si durante la cancelación Stripe rechaza con HTTP 400 (porque ya fue capturado)
    o la intención transiciona a SUCCEEDED:
    - El stock comprometido_digital NO se libera.
    - NO se emite LIBERACION_DIGITAL en Kardex.
    - La orden se sincroniza atómicamente a CAPTURADO.
    - La venta se añade a 'omitidas'.
    """
    http.usar(escenario.usuario_admin_a)

    # 1. Iniciar venta presencial Stripe
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201, resp_init.text
    datos_init = resp_init.json()
    venta_id = uuid.UUID(datos_init["venta_id"])
    orden_pago_id = uuid.UUID(datos_init["orden_pago_id"])
    pi_id = datos_init["stripe_payment_intent_id"]

    ahora_utc = datetime.now(timezone.utc)
    async with fabrica_sesiones() as db:
        v = await db.get(Venta, venta_id)
        v.expira_en = ahora_utc - timedelta(minutes=5)
        await db.commit()

        inv_antes = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                )
            )
        ).scalars().first()
        comp_antes = inv_antes.comprometido_digital
        disp_antes = inv_antes.disponible

    # 2. Simular carrera: en consultar_intencion la intención parecía REQUIRES_PAYMENT_METHOD,
    # pero al invocar cancelar_intencion, la pasarela reporta que ya fue capturada (HTTP 400),
    # y la intención real en Stripe pasa a SUCCEEDED.
    fake_stripe.intenciones[pi_id].estado = "REQUIRES_PAYMENT_METHOD"

    class GatewayConCapturaConcurrente(FakeStripeGateway):
        def __init__(self, backend_gateway):
            super().__init__()
            self.intenciones = backend_gateway.intenciones
            self.intenciones_creadas = backend_gateway.intenciones_creadas
            self.por_venta = backend_gateway.por_venta

        async def cancelar_intencion(self, payment_intent_id: str) -> IntencionPago:
            # Simular captura concurrente en Stripe justo antes de cancelar
            inten = self.intenciones[payment_intent_id]
            inten.estado = "SUCCEEDED"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"codigo": "STRIPE_ESTADO_INVALIDO", "mensaje": "PaymentIntent ya fue capturado en Stripe"},
            )

    gw_carrera = GatewayConCapturaConcurrente(fake_stripe)
    fijar_gateway(gw_carrera)

    # 3. Ejecutar el worker de vencimiento
    async with fabrica_sesiones() as db:
        servicio = StripeService(db)
        res = await _ejecutar_cancelacion_vencidas(
            servicio, ahora_param=ahora_utc, venta_id=venta_id
        )

    # 4. Validar que no se liberó el stock y que la orden sincronizó a CAPTURADO
    assert str(venta_id) in res.get("omitidas", [])
    assert str(venta_id) not in res.get("canceladas", [])

    async with fabrica_sesiones() as db:
        op_post = await db.get(OrdenPago, orden_pago_id)
        assert op_post.estado == "CAPTURADO", f"OrdenPago debió sincronizar a CAPTURADO, está en {op_post.estado}"

        inv_post = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.sucursal_id == escenario.sucursal_a_id,
                    InventarioSucursal.variante_id == escenario.variante_a_id,
                )
            )
        ).scalars().first()
        assert inv_post.comprometido_digital == comp_antes, "Stock no debe ser liberado si fue capturado"
        assert inv_post.disponible == disp_antes

        kardex = (
            await db.execute(
                select(MovimientoInventario).where(
                    MovimientoInventario.referencia_id == venta_id,
                    MovimientoInventario.tipo == "LIBERACION_DIGITAL",
                )
            )
        ).scalars().all()
        assert len(kardex) == 0


# =============================================================================
# P0-2: CONTRATO Y AUTORIZACIÓN GET /api/v1/pagos/stripe/ordenes/activa-caja
# =============================================================================

@pytest.mark.asyncio
async def test_p0_2a_recuperar_orden_activa_caja_estructura_completa_dto_presencial_y_offline(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """P0-2a: Valida la estructura completa de OrdenActivaCajaDTO tanto para

    venta presencial directa como para venta asociada a un turno offline.
    Verifica congelamiento de tasa_bob_por_usd, presencia de líneas completas y procedencia.
    """
    http.usar(escenario.usuario_admin_a)

    # 1. Caso PRESENCIAL directo (sin turno)
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 2}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init.status_code == 201, resp_init.text
    init_data = resp_init.json()
    venta_id = init_data["venta_id"]
    ord_id = init_data["orden_pago_id"]
    pi_ref = init_data["stripe_payment_intent_id"]

    # Invocar GET /api/v1/pagos/stripe/ordenes/activa-caja
    resp_activa = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_activa.status_code == 200, resp_activa.text
    dto = resp_activa.json()
    assert dto is not None

    # Validar campos contractuales de OrdenActivaCajaDTO
    assert dto["orden_pago_id"] == ord_id
    assert dto["venta_id"] == venta_id
    assert dto["stripe_payment_intent_id"] == pi_ref
    assert dto["client_secret"] is not None and dto["client_secret"].startswith("pi_")
    assert Decimal(dto["monto_bob"]) == Decimal("200.00")
    assert dto["centavos_usd"] is not None and dto["centavos_usd"] > 0
    assert dto["tasa_bob_por_usd"] is not None
    assert Decimal(dto["tasa_bob_por_usd"]) > 0
    assert dto["estado_orden"] == "PENDIENTE"
    assert dto["sucursal_id"] == str(escenario.sucursal_a_id)
    assert dto["turno_caja_id"] is None
    assert dto["procedencia"] == "PRESENCIAL"
    assert dto["estado_verificacion"] == "VERIFICADO"

    # Validar líneas
    assert len(dto["lineas"]) == 1
    linea = dto["lineas"][0]
    assert linea["variante_id"] == str(escenario.variante_a_id)
    assert linea["cantidad"] == 2
    assert Decimal(linea["precio_unitario_bob"]) == Decimal("100.00")
    assert Decimal(linea["descuento_bob"]) == Decimal("0.00")
    assert linea["sku"] is not None
    assert linea["nombre_producto"] is not None

    # 2. Caso TURNO_OFFLINE
    turno_id = uuid.uuid4()
    ahora = datetime.now(timezone.utc)
    async with fabrica_sesiones() as db:
        db.add(
            TurnoCaja(
                id=turno_id,
                empresa_id=escenario.empresa_a_id,
                sucursal_id=escenario.sucursal_a_id,
                cajero_id=escenario.usuario_admin_a.id,
                dispositivo_id=uuid.uuid4(),
                caja_codigo="CAJA-P0-AUD39",
                estado="ABIERTO",
                cupos_hash="hash_test_p0",
                inicio_en=ahora,
                vence_en=ahora + timedelta(hours=8),
                version_precios="v1",
            )
        )
        await db.commit()

    resp_init_turno = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "turno_caja_id": str(turno_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init_turno.status_code == 201, resp_init_turno.text
    dto_turno_init = resp_init_turno.json()

    resp_activa_turno = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}&turno_caja_id={turno_id}"
    )
    assert resp_activa_turno.status_code == 200
    dto_t = resp_activa_turno.json()
    assert dto_t is not None
    assert dto_t["procedencia"] == "TURNO_OFFLINE"
    assert dto_t["turno_caja_id"] == str(turno_id)
    assert dto_t["orden_pago_id"] == dto_turno_init["orden_pago_id"]


@pytest.mark.asyncio
async def test_p0_2b_autorizacion_y_aislamiento_caja_tenant_y_cajero(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """P0-2b: Reglas estrictas de autorización y ordenamiento determinista:

    1. Tenant Isolation: Usuario de Empresa B no puede acceder a órdenes de Empresa A.
    2. Cajero: Cajero no admin solo ve órdenes creadas por él.
    3. Turno: No retorna órdenes de otro turno cuando se filtra por turno_caja_id.
    4. Determinismo: Retorna estrictamente la última orden activa (creada_en DESC, id DESC).
    """
    cajero_1 = await _crear_usuario_cajero(fabrica_sesiones, escenario.empresa_a_id, sucursal_id=escenario.sucursal_a_id)
    cajero_2 = await _crear_usuario_cajero(fabrica_sesiones, escenario.empresa_a_id, sucursal_id=escenario.sucursal_a_id)

    # 1. Crear venta iniciada con cajero_1
    http.usar(cajero_1)
    resp_init_1 = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init_1.status_code == 201, resp_init_1.text
    ord_id_1 = resp_init_1.json()["orden_pago_id"]

    # 2. Verificar que cajero_1 la recupera
    resp_c1 = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_c1.status_code == 200
    assert resp_c1.json() is not None
    assert resp_c1.json()["orden_pago_id"] == ord_id_1

    # 3. Cajero_2 (mismo tenant pero distinto usuario no-admin) NO debe ver la orden de cajero_1
    http.usar(cajero_2)
    resp_c2 = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_c2.status_code == 200
    assert resp_c2.json() is None

    # 4. Tenant isolation: Usuario de Empresa B no debe ver la orden de Empresa A
    http.usar(escenario.usuario_b)
    resp_emp_b = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_emp_b.status_code == 200
    assert resp_emp_b.json() is None

    # 5. Turno no coincidente: un turno ajeno no recupera la orden sin turno
    http.usar(cajero_1)
    turno_otro = uuid.uuid4()
    resp_turno_mismatch = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}&turno_caja_id={turno_otro}"
    )
    assert resp_turno_mismatch.status_code == 200
    assert resp_turno_mismatch.json() is None

    # 6. Determinismo ante múltiples órdenes: cajero_1 crea una segunda orden
    resp_init_2 = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp_init_2.status_code == 201
    ord_id_2 = resp_init_2.json()["orden_pago_id"]

    resp_det = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_det.status_code == 200
    assert resp_det.json()["orden_pago_id"] == ord_id_2, "Debe retornar la orden más reciente"


# =============================================================================
# P0-3: VALIDACIÓN FINANCIERA RIGUROSA (P0-3a a P0-3f)
# =============================================================================

@pytest.mark.asyncio
async def test_p0_3a_intencion_id_discrepante_rechaza_captura(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """P0-3a: Si la intención devuelta por Stripe tiene ID diferente al de la orden,

    rechaza con HTTP 400 y NO transiciona a CAPTURADO.
    """
    http.usar(escenario.usuario_admin_a)
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    init_data = resp_init.json()
    ord_id = uuid.UUID(init_data["orden_pago_id"])
    pi_ref = init_data["stripe_payment_intent_id"]

    # Simular que Stripe devuelve un objeto IntencionPago con id adulterado
    inten_real = fake_stripe.intenciones[pi_ref]
    inten_adulterada = copy.deepcopy(inten_real)
    inten_adulterada.id = "pi_alien_infiltrado_999"
    inten_adulterada.estado = "SUCCEEDED"

    class GatewayIdDiscrepante(FakeStripeGateway):
        async def consultar_intencion(self, payment_intent_id: str) -> IntencionPago:
            return inten_adulterada

    fijar_gateway(GatewayIdDiscrepante())

    resp = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp.status_code == 400, resp.text
    assert "id no coincide" in resp.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, ord_id)
        assert op.estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_p0_3b_intencion_moneda_discrepante_rechaza_captura(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """P0-3b: Si la intención devuelta por Stripe tiene moneda distinta de USD (ej. EUR),

    rechaza con HTTP 400 y NO transiciona a CAPTURADO.
    """
    http.usar(escenario.usuario_admin_a)
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    init_data = resp_init.json()
    ord_id = uuid.UUID(init_data["orden_pago_id"])
    pi_ref = init_data["stripe_payment_intent_id"]

    fake_stripe.intenciones[pi_ref].moneda = "eur"
    fake_stripe.intenciones[pi_ref].estado = "SUCCEEDED"

    resp = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp.status_code == 400, resp.text
    assert "moneda no coincide" in resp.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, ord_id)
        assert op.estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_p0_3c_intencion_centavos_discrepantes_rechaza_captura(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """P0-3c: Si la intención devuelta por Stripe tiene centavos discrepantes,

    rechaza con HTTP 400 y NO transiciona a CAPTURADO.
    """
    http.usar(escenario.usuario_admin_a)
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    init_data = resp_init.json()
    ord_id = uuid.UUID(init_data["orden_pago_id"])
    pi_ref = init_data["stripe_payment_intent_id"]

    # Modificar centavos en pasarela: monto real alterado (ej. 1 centavo menos)
    fake_stripe.intenciones[pi_ref].monto_centavos += 100
    fake_stripe.intenciones[pi_ref].estado = "SUCCEEDED"

    resp = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp.status_code == 400, resp.text
    assert "monto en centavos" in resp.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, ord_id)
        assert op.estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_p0_3d_intencion_metadata_empresa_faltante_o_ajena_rechaza_captura(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """P0-3d: Si la intención devuelta por Stripe no tiene metadata empresa_id

    o pertenece a otra empresa, rechaza con HTTP 400 y NO marca CAPTURADO.
    """
    http.usar(escenario.usuario_admin_a)
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    init_data = resp_init.json()
    ord_id = uuid.UUID(init_data["orden_pago_id"])
    pi_ref = init_data["stripe_payment_intent_id"]

    # 1. Subcaso: Metadata con empresa de otro tenant
    fake_stripe.intenciones[pi_ref].metadata["empresa_id"] = str(uuid.uuid4())
    fake_stripe.intenciones[pi_ref].empresa_id = str(uuid.uuid4())
    fake_stripe.intenciones[pi_ref].estado = "SUCCEEDED"

    resp_ajena = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_ajena.status_code == 400, resp_ajena.text
    assert "empresa_id" in resp_ajena.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, ord_id)
        assert op.estado == "PENDIENTE"

    # 2. Subcaso: Metadata empresa_id completamente faltante
    fake_stripe.intenciones[pi_ref].metadata.pop("empresa_id", None)
    fake_stripe.intenciones[pi_ref].empresa_id = None

    resp_faltante = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_faltante.status_code == 400, resp_faltante.text
    assert "empresa_id" in resp_faltante.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, ord_id)
        assert op.estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_p0_3e_intencion_metadata_venta_faltante_o_ajena_rechaza_captura(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """P0-3e: Si la intención devuelta por Stripe tiene metadata venta_id faltante

    o correspondiente a otra venta, rechaza con HTTP 400 y NO marca CAPTURADO.
    """
    http.usar(escenario.usuario_admin_a)
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    init_data = resp_init.json()
    ord_id = uuid.UUID(init_data["orden_pago_id"])
    pi_ref = init_data["stripe_payment_intent_id"]

    # 1. Subcaso: Metadata con venta ajena
    fake_stripe.intenciones[pi_ref].metadata["venta_id"] = str(uuid.uuid4())
    fake_stripe.intenciones[pi_ref].venta_id = str(uuid.uuid4())
    fake_stripe.intenciones[pi_ref].estado = "SUCCEEDED"

    resp_ajena = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_ajena.status_code == 400, resp_ajena.text
    assert "venta_id" in resp_ajena.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, ord_id)
        assert op.estado == "PENDIENTE"

    # 2. Subcaso: Metadata venta_id completamente faltante
    fake_stripe.intenciones[pi_ref].metadata.pop("venta_id", None)
    fake_stripe.intenciones[pi_ref].venta_id = None

    resp_faltante = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp_faltante.status_code == 400, resp_faltante.text
    assert "venta_id" in resp_faltante.json()["detail"].lower()

    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, ord_id)
        assert op.estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_p0_3f_gateway_timeout_o_error_conexion_no_silencia_y_reporta_no_verificado(
    http, escenario, fabrica_sesiones, fake_stripe
):
    """P0-3f: Si consultar_intencion arroja timeout o error de red:

    - NO se captura silenciosamente con pass asumiendo éxito.
    - Responde HTTP 200 con estado_verificacion = 'NO_VERIFICADO_ERROR_PASARELA'.
    - La orden permanece en su estado local (PENDIENTE) sin mutar a CAPTURADO.
    - La venta permanece en PENDIENTE_PAGO.
    """
    http.usar(escenario.usuario_admin_a)
    resp_init = await http.cliente.post(
        "/api/v1/ventas/presenciales/iniciar-stripe",
        json={
            "sucursal_id": str(escenario.sucursal_a_id),
            "cliente_id": str(escenario.usuario_a.id),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    init_data = resp_init.json()
    ord_id = uuid.UUID(init_data["orden_pago_id"])
    venta_id = uuid.UUID(init_data["venta_id"])

    # Simular fallo de red / timeout en Stripe al consultar la intención
    class GatewayConFalloConsulta(FakeStripeGateway):
        async def consultar_intencion(self, payment_intent_id: str) -> IntencionPago:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "STRIPE_TIMEOUT", "mensaje": "Timeout de pasarela simulado"},
            )

    fijar_gateway(GatewayConFalloConsulta())

    resp = await http.cliente.get(
        f"/api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={escenario.sucursal_a_id}"
    )
    assert resp.status_code == 200, resp.text
    dto = resp.json()
    assert dto is not None
    assert dto["estado_verificacion"] == "NO_VERIFICADO_ERROR_PASARELA"
    assert dto["estado_orden"] == "PENDIENTE"

    async with fabrica_sesiones() as db:
        op = await db.get(OrdenPago, ord_id)
        assert op.estado == "PENDIENTE"
        v = await db.get(Venta, venta_id)
        assert v.estado == "PENDIENTE_PAGO"
