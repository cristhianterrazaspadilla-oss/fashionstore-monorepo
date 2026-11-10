"""Solo SQLite en memoria y Stripe simulado; usar el conftest aislado.

Los xfail son regresiones pendientes del servicio cuya modificacion rechazo
la revision automatica. No constituyen correcciones aprobadas ni pruebas verdes.
"""
import uuid
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.app.core.modules.posventa.services.reembolso_monetario import (
    centavos_acumulados, distribuir, dinero,
)
from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw
from backend.app.core.modules.ventas_pagos.services.stripe_service import StripeService
from backend.app.core.modules.ventas_pagos.models import Venta, Pago
from backend.app.core.modules.ventas_pagos.models_ordenes import OrdenPago
from backend.app.core.modules.organizacion.models import TasaCambio
from backend.app.core.modules.posventa.models import ObligacionReembolso, ComponenteReembolso
from backend.app.core.modules.posventa.services.reembolso_service import ReembolsoService
from backend.app.core.modules.posventa.schemas import ReembolsoSolicitudDTO
from types import SimpleNamespace


def test_reembolso_total_en_unidades_originales():
    assert centavos_acumulados('210.00', 3000, '0', 0, '210.00') == 3000


def test_parciales_redondeo_acumulado_y_ultimo_restante():
    usados = 0
    partes = []
    for bob in range(3):
        n = centavos_acumulados('3.00', 1000, bob, usados, '1.00')
        partes.append(n)
        usados += n
    assert partes == [333, 334, 333]
    assert sum(partes) == 1000


def test_varios_componentes_no_convierten_saldo_o_efectivo_en_stripe():
    stripe, saldo, efectivo = distribuir('10.00', ['30.00', '40.00', '30.00'])
    assert (stripe, saldo, efectivo) == (Decimal(3), Decimal(4), Decimal(3))
    assert centavos_acumulados('30.00', 429, 0, 0, stripe) == 43
    assert stripe + saldo + efectivo == Decimal(10)


@pytest.mark.parametrize('usado,cents,importe', [('2.00', 667, '1.01'), ('3.00', 1000, '.01'), ('1.00', 1, '1.00')])
def test_limite_acumulado_y_cotizacion_previa_contradictoria(usado, cents, importe):
    with pytest.raises(HTTPException) as exc:
        centavos_acumulados('3.00', 1000, usado, cents, importe)
    assert exc.value.status_code == 409


def test_importe_subcentavo_no_se_inventa_y_distribucion_no_supera_disponible():
    with pytest.raises(HTTPException):
        centavos_acumulados('100', 1, 0, 0, '.01')
    with pytest.raises(HTTPException):
        distribuir('10.01', ['3', '7'])
    with pytest.raises(HTTPException):
        dinero('1.001')
    with pytest.raises(HTTPException):
        dinero(None)
    with pytest.raises(HTTPException):
        centavos_acumulados('3', 1000.0, 0, 0, '1')


@pytest.mark.asyncio
async def test_fake_proveedor_reintento_tras_respuesta_perdida_un_solo_reintegro():
    gateway = gw.FakeStripeGateway()
    gateway.intenciones['pi_original'] = gw.IntencionPago('pi_original', 'venta', 3000, 'usd', 'SUCCEEDED')
    clave = str(uuid.uuid4())
    primero = await gateway.crear_reembolso('pi_original', 1000, clave)
    # El cliente no recibe primero; vuelve a enviar la misma operacion.
    repetido = await gateway.crear_reembolso('pi_original', 1000, clave)
    assert primero.id == repetido.id
    assert len(gateway.reembolsos) == 1
    await gateway.crear_reembolso('pi_original', 2000, str(uuid.uuid4()))
    with pytest.raises(ValueError):
        await gateway.crear_reembolso('pi_original', 1, str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_adaptador_consulta_captura_real_y_disponible_sin_red(monkeypatch):
    original_client = httpx.AsyncClient

    def responder(req):
        assert req.url.params.get('expand[]') == 'latest_charge'
        return httpx.Response(200, json={'id': 'pi_original', 'amount': 3000, 'amount_received': 3000,
            'currency': 'usd', 'status': 'succeeded', 'latest_charge': {'amount_refunded': 1100},
            'metadata': {'venta_id': 'venta', 'empresa_id': 'empresa'}})

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original_client(transport=httpx.MockTransport(responder)))
    monkeypatch.setattr(gw.settings, 'STRIPE_SECRET_KEY', '')
    cargo = await gw.RealStripeGateway().consultar_intencion('pi_original')
    assert cargo.capturado_centavos == 3000
    assert cargo.reembolsado_centavos == 1100
    assert cargo.moneda == 'usd'


@pytest.mark.asyncio
@pytest.mark.parametrize('estado', ['pending', 'failed', 'canceled', 'requires_action'])
async def test_adaptador_no_inventa_succeeded_ni_importes(monkeypatch, estado):
    original_client = httpx.AsyncClient
    clave = str(uuid.uuid4())

    def responder(req):
        assert req.headers['Idempotency-Key'] == clave
        assert ('metadata%5Bejecucion_id%5D=' + clave).encode() in req.content
        return httpx.Response(200, json={'id': 're_original', 'payment_intent': 'pi_original',
            'amount': 1000, 'currency': 'usd', 'status': estado})

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original_client(transport=httpx.MockTransport(responder)))
    monkeypatch.setattr(gw.settings, 'STRIPE_SECRET_KEY', '')
    r = await gw.RealStripeGateway().crear_reembolso('pi_original', 1000, clave)
    assert r.estado == estado
    vacio = gw.RealStripeGateway._reembolso({})
    assert vacio.estado == 'unknown' and vacio.centavos_usd is None and vacio.moneda is None


@pytest.mark.asyncio
async def test_busqueda_reembolso_por_clave_recorre_paginas_y_consulta_id(monkeypatch):
    original_client = httpx.AsyncClient
    peticiones = []
    registro = {'id': 're_original', 'payment_intent': 'pi_original', 'amount': 1000,
                'currency': 'usd', 'status': 'pending', 'metadata': {'ejecucion_id': 'clave'}}

    def responder(req):
        peticiones.append(req)
        if req.url.path.endswith('/re_original'):
            return httpx.Response(200, json=registro)
        if req.url.params.get('starting_after'):
            return httpx.Response(200, json={'data': [registro], 'has_more': False})
        return httpx.Response(200, json={'data': [{'id': 're_otro', 'metadata': {}}], 'has_more': True})

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original_client(transport=httpx.MockTransport(responder)))
    monkeypatch.setattr(gw.settings, 'STRIPE_SECRET_KEY', '')
    gateway = gw.RealStripeGateway()
    r = await gateway.buscar_reembolso('pi_original', 'clave')
    assert r.id == 're_original'
    assert (await gateway.consultar_reembolso(r.id)).estado == 'pending'
    assert len(peticiones) == 3


@pytest.mark.asyncio
async def test_cu15_guarda_cotizacion_en_orden_existente_y_no_usa_tasa_actual(entorno, monkeypatch):
    e = entorno
    # La consulta SQL textual de produccion usa UUID nativo de PostgreSQL.
    # Adaptacion del driver solo para esta prueba SQLite en memoria.
    monkeypatch.setitem(sqlite3.adapters, (uuid.UUID, sqlite3.PrepareProtocol), lambda v: v.hex)
    tasa = TasaCambio(id=uuid.uuid4(), version=1, tasa_bob_por_usd=Decimal('7'),
                      vigente_desde=datetime(2026, 1, 1, tzinfo=timezone.utc), motivo='sintetico')
    e.db.add(tasa)
    e.db.add(TasaCambio(id=uuid.uuid4(), version=2, tasa_bob_por_usd=Decimal('9'),
        vigente_desde=datetime(2026, 11, 1, tzinfo=timezone.utc), motivo='otra cotizacion sintetica'))
    await e.db.flush()
    venta = Venta(id=uuid.uuid4(), empresa_id=uuid.uuid4(), total=Decimal('210'))
    pi = gw.IntencionPago('pi_original', str(venta.id), 3000, 'usd', 'REQUIRES_PAYMENT',
        metadata={'tasa_id': str(tasa.id), 'monto_bob': '210.00',
                  'centavos_usd': '3000', 'empresa_id': str(venta.empresa_id)})
    servicio = StripeService(e.db)
    assert await servicio._validar_intencion_venta(venta, pi) == Decimal('30')
    pi.estado = 'SUCCEEDED'
    pi.capturado_centavos = 3000
    await servicio._validar_intencion_venta(venta, pi)
    ordenes = e.session.execute(select(OrdenPago).where(OrdenPago.referencia_externa == pi.id)).scalars().all()
    assert len(ordenes) == 1
    assert ordenes[0].estado == 'CAPTURADO' and ordenes[0].centavos_usd == 3000
    assert ordenes[0].tasa_id == tasa.id
    pi.metadata = {}
    with pytest.raises(HTTPException, match='') as error:
        await servicio._validar_intencion_venta(venta, pi)
    assert 'CONCILIACION_REQUERIDA' in error.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize('proveedor,esperado', [('pending', 'EN_PROCESO'), ('failed', 'FALLIDO'),
    ('canceled', 'FALLIDO'), ('succeeded', 'COMPLETADO')])
async def test_servicio_respeta_estado_y_concilia_consultando_sin_otro_desembolso(entorno, monkeypatch, proveedor, esperado):
    e = entorno
    empresa, cliente, venta_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    pago = Pago(id=uuid.uuid4(), empresa_id=empresa, contexto='VENTA', venta_id=venta_id,
                metodo='STRIPE_TEST', monto=Decimal(210), estado='APROBADO', referencia_externa='pi_original')
    obl = ObligacionReembolso(id=uuid.uuid4(), empresa_id=empresa, cliente_id=cliente,
        origen_tipo='VENTA', origen_id=venta_id, motivo_codigo='OTRO', estado='AUTORIZADO', monto_bob=Decimal(210))
    comp = ComponenteReembolso(id=uuid.uuid4(), empresa_id=empresa, obligacion_id=obl.id, pago_id=pago.id,
        medio='STRIPE', monto_bob=Decimal(210), monto_usd=Decimal(30), centavos_usd=3000,
        tasa_bob_por_usd=Decimal(7), estado='PENDIENTE')
    e.session.add_all([pago, obl, comp])
    await e.db.commit()

    class Pendiente:
        estado = 'pending'
        llamadas = 0

        async def crear_reembolso(self, **kw):
            self.llamadas += 1
            return gw.ReembolsoInfo('re_pendiente', 'pi_original', 3000, 'pending', 'usd')

        async def consultar_reembolso(self, referencia):
            assert referencia == 're_pendiente'
            return gw.ReembolsoInfo('re_pendiente', 'pi_original', 3000, self.estado, 'usd')

    gateway = Pendiente()
    monkeypatch.setattr(gw, 'obtener_gateway', lambda: gateway)
    usuario = SimpleNamespace(id=cliente, empresa_id=empresa, rol=SimpleNamespace(nombre='ADMINISTRADOR'))
    resultado = await ReembolsoService(e.db).ejecutar_reembolso(usuario, obl.id, uuid.uuid4(), uuid.uuid4())
    assert resultado.estado == 'EN_PROCESO' and resultado.completada_en is None
    gateway.estado = proveedor
    conciliado = await ReembolsoService(e.db).conciliar_reembolso(usuario, obl.id, uuid.uuid4())
    assert conciliado.estado == esperado
    assert (conciliado.completada_en is not None) == (esperado == 'COMPLETADO')
    assert gateway.llamadas == 1


@pytest.mark.xfail(strict=True, reason='BLOQUEADO: revision automatica rechazo modificar derivacion/distribucion del servicio')
@pytest.mark.asyncio
async def test_regresion_solicitud_debe_usar_centavos_originales_no_tasa_fija(entorno):
    e = entorno
    empresa, cliente = uuid.uuid4(), uuid.uuid4()
    venta = Venta(id=uuid.uuid4(), empresa_id=empresa, cliente_id=cliente,
        numero='venta-sintetica', sucursal_id=uuid.uuid4(), estado='PAGADA', total=Decimal(210))
    pago = Pago(id=uuid.uuid4(), empresa_id=empresa, contexto='VENTA', venta_id=venta.id,
        metodo='STRIPE_TEST', monto=Decimal(210), estado='APROBADO', referencia_externa='pi_original')
    tasa = TasaCambio(id=uuid.uuid4(), version=1, tasa_bob_por_usd=Decimal(7),
        vigente_desde=datetime(2026, 1, 1, tzinfo=timezone.utc), motivo='sintetica')
    orden = OrdenPago(id=uuid.uuid4(), empresa_id=empresa, contexto='VENTA', venta_id=venta.id,
        proveedor='STRIPE', clave_externa='captura-original', referencia_externa='pi_original',
        estado='CAPTURADO', monto_bob=Decimal(210), tasa_id=tasa.id, monto_usd=Decimal(30), centavos_usd=3000)
    e.session.add_all([venta, pago, tasa, orden])
    await e.db.commit()
    actor = SimpleNamespace(id=cliente, empresa_id=empresa, rol=SimpleNamespace(nombre='ADMINISTRADOR'))
    dto = ReembolsoSolicitudDTO(origen_tipo='VENTA', origen_id=venta.id, motivo_codigo='OTRO')
    resultado = await ReembolsoService(e.db).solicitar_reembolso(actor, dto, uuid.uuid4())
    assert resultado.componentes[0].centavos_usd == 3000
