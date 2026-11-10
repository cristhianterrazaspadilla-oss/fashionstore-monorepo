"""SQLite en memoria y Stripe simulado; no valida concurrencia PostgreSQL."""
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
from test_bloque_seguridad import datos


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


@pytest.fixture
def reembolso(datos, monkeypatch):
    e = datos
    from sqlalchemy.orm import Session
    from backend.app.core.modules.posventa.models import EjecucionReembolso
    e.venta = e.session.get(Venta, e.v1)
    e.venta.total = e.venta.subtotal = Decimal("210.00")
    tasa = TasaCambio(id=uuid.uuid4(), version=1, tasa_bob_por_usd=Decimal("7"),
                     vigente_desde=datetime(2026, 1, 1, tzinfo=timezone.utc), motivo="sintetica")
    e.pago = Pago(id=uuid.uuid4(), empresa_id=e.a, contexto="VENTA", venta_id=e.v1,
        metodo="STRIPE_TEST", monto=Decimal("210"), estado="APROBADO", referencia_externa="pi_original")
    e.orden = OrdenPago(id=uuid.uuid4(), empresa_id=e.a, contexto="VENTA", venta_id=e.v1,
        proveedor="STRIPE", clave_externa="captura-original", referencia_externa="pi_original",
        estado="CAPTURADO", monto_bob=Decimal("210"), tasa_id=tasa.id,
        monto_usd=Decimal("30"), centavos_usd=3000)
    e.obl = ObligacionReembolso(id=uuid.uuid4(), empresa_id=e.a, cliente_id=e.cliente.id,
        origen_tipo="VENTA", origen_id=e.v1, motivo_codigo="OTRO", estado="AUTORIZADO",
        autorizada_en=datetime(2026, 11, 8, tzinfo=timezone.utc), monto_bob=Decimal("210"))
    e.comp = ComponenteReembolso(id=uuid.uuid4(), empresa_id=e.a, obligacion_id=e.obl.id, pago_id=e.pago.id,
        medio="STRIPE", monto_bob=Decimal("210"), monto_usd=Decimal("30"), centavos_usd=3000,
        tasa_bob_por_usd=Decimal("7"), estado="PENDIENTE")
    e.session.add_all([tasa, e.pago, e.orden, e.obl, e.comp])
    e.session.commit()

    class ProveedorControlado(gw.FakeStripeGateway):
        def __init__(self):
            super().__init__()
            self.llamadas = 0
            self.estado_inicial = "pending"
            self.perder_respuesta = False
            self.fallar_antes = False
            self.intenciones["pi_original"] = gw.IntencionPago(
                "pi_original", str(e.v1), 3000, "usd", "SUCCEEDED",
                empresa_id=str(e.a), cliente_id=str(e.cliente.id),
                metadata={"empresa_id": str(e.a), "venta_id": str(e.v1)})

        async def crear_reembolso(self, **kw):
            # Verificación antes de entregar nada al proveedor, mediante otra
            # sesión ORM. SQLite NO reproduce aislamiento/bloqueos PostgreSQL.
            assert not e.session.in_transaction()
            with Session(e.session.bind) as lectura:
                ejec = lectura.execute(select(EjecucionReembolso).where(
                    EjecucionReembolso.componente_id == e.comp.id)).scalars().one()
                assert ejec.estado == "EN_PROCESO"
                assert str(ejec.clave_ejecucion) == kw["idempotency_key"]
                assert lectura.get(ComponenteReembolso, e.comp.id).estado == "EN_PROCESO"
                assert lectura.get(ObligacionReembolso, e.obl.id).estado == "EN_PROCESO"
            assert kw["payment_intent_id"] == "pi_original" and kw["centavos_usd"] == 3000
            self.llamadas += 1
            if self.fallar_antes:
                raise TimeoutError("Sin prueba de recepción")
            respuesta = await super().crear_reembolso(**kw)
            respuesta.estado = self.estado_inicial
            if self.perder_respuesta:
                self.perder_respuesta = False
                raise TimeoutError("Respuesta perdida después de aceptar")
            return respuesta

    e.gateway = ProveedorControlado()
    monkeypatch.setattr(gw, "obtener_gateway", lambda: e.gateway)
    return e


@pytest.mark.asyncio
@pytest.mark.parametrize("proveedor,esperado", [("pending", "EN_PROCESO"), ("failed", "FALLIDO"),
    ("canceled", "FALLIDO"), ("succeeded", "COMPLETADO")])
async def test_servicio_respeta_estado_y_concilia_consultando_sin_otro_desembolso(reembolso, proveedor, esperado):
    e = reembolso
    resultado = await ReembolsoService(e.db).ejecutar_reembolso(e.admin, e.obl.id, uuid.uuid4(), uuid.uuid4())
    assert resultado.estado == "EN_PROCESO" and resultado.completada_en is None
    next(iter(e.gateway.reembolsos.values())).estado = proveedor
    conciliado = await ReembolsoService(e.db).conciliar_reembolso(e.admin, e.obl.id, uuid.uuid4())
    assert conciliado.estado == esperado
    assert (conciliado.completada_en is not None) == (esperado == "COMPLETADO")
    repetido = await ReembolsoService(e.db).ejecutar_reembolso(e.admin, e.obl.id, uuid.uuid4(), uuid.uuid4())
    assert repetido.estado == esperado
    assert e.gateway.llamadas == 1


@pytest.mark.asyncio
async def test_respuesta_perdida_recupera_en_sesion_nueva_con_clave_guardada(reembolso):
    from sqlalchemy.orm import Session
    from backend.app.core.modules.posventa.models import EjecucionReembolso
    e = reembolso
    e.gateway.estado_inicial = "succeeded"
    e.gateway.perder_respuesta = True
    with pytest.raises(HTTPException) as error:
        await ReembolsoService(e.db).ejecutar_reembolso(e.admin, e.obl.id, uuid.uuid4(), uuid.uuid4())
    assert error.value.status_code == 409
    with Session(e.session.bind, expire_on_commit=False) as nueva:
        ejec = nueva.execute(select(EjecucionReembolso)).scalars().one()
        clave = ejec.clave_ejecucion
        assert ejec.estado == "EN_PROCESO" and ejec.referencia_externa is None
        servicio = ReembolsoService(type(e.db)(nueva))
        salida = await servicio.ejecutar_reembolso(e.admin, e.obl.id, uuid.uuid4(), uuid.uuid4())
        assert salida.estado == "COMPLETADO"
        ejec = nueva.execute(select(EjecucionReembolso)).scalars().one()
        assert ejec.clave_ejecucion == clave and ejec.referencia_externa
    assert e.gateway.llamadas == 1 and len(e.gateway.reembolsos) == 1


@pytest.mark.asyncio
async def test_preparada_persistida_se_retoma_sin_crear_otra_ejecucion(reembolso, monkeypatch):
    from backend.app.core.modules.posventa.models import EjecucionReembolso
    e = reembolso
    servicio = ReembolsoService(e.db)
    async def interrupcion(*args, **kwargs):
        raise TimeoutError("Interrupción después del commit, antes de reclamar envío")
    monkeypatch.setattr(servicio, "_procesar_planes", interrupcion)
    with pytest.raises(TimeoutError):
        await servicio.ejecutar_reembolso(e.admin, e.obl.id, uuid.uuid4(), uuid.uuid4())
    assert not e.session.in_transaction() and e.gateway.llamadas == 0
    ejec = e.session.execute(select(EjecucionReembolso)).scalars().one()
    clave = ejec.clave_ejecucion
    assert ejec.estado == "PREPARADA"
    e.session.commit()
    await ReembolsoService(e.db).ejecutar_reembolso(e.admin, e.obl.id, uuid.uuid4(), uuid.uuid4())
    assert e.gateway.llamadas == 1
    assert e.session.execute(select(EjecucionReembolso)).scalars().one().clave_ejecucion == clave


@pytest.mark.asyncio
async def test_envio_incierto_sin_coincidencia_no_se_repite_ni_libera_reserva(reembolso):
    from backend.app.core.modules.posventa.models import EjecucionReembolso
    e = reembolso
    e.gateway.fallar_antes = True
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            await ReembolsoService(e.db).ejecutar_reembolso(e.admin, e.obl.id, uuid.uuid4(), uuid.uuid4())
        assert error.value.status_code == 409
    assert e.gateway.llamadas == 1 and not e.gateway.reembolsos
    ejec = e.session.execute(select(EjecucionReembolso)).scalars().one()
    assert ejec.estado == "EN_PROCESO" and ejec.referencia_externa is None
    with pytest.raises(HTTPException):
        await ReembolsoService(e.db).solicitar_reembolso(e.cliente,
            ReembolsoSolicitudDTO(origen_tipo="VENTA", origen_id=e.v1, motivo_codigo="OTRO_MOTIVO"), uuid.uuid4())
    assert e.session.execute(select(ObligacionReembolso)).scalars().one().id == e.obl.id


@pytest.mark.asyncio
@pytest.mark.parametrize("actor,codigo", [("admin_b", 404), ("cliente", 403), ("otro", 403), ("plataforma", 403)])
async def test_ejecucion_rechaza_otra_empresa_cliente_y_plataforma(reembolso, actor, codigo):
    e = reembolso
    with pytest.raises(HTTPException) as error:
        await ReembolsoService(e.db).ejecutar_reembolso(getattr(e, actor), e.obl.id, uuid.uuid4(), uuid.uuid4())
    assert error.value.status_code == codigo and e.gateway.llamadas == 0


@pytest.mark.asyncio
async def test_sucursal_autorizada_y_otro_titular_no_son_intercambiables(reembolso):
    e = reembolso
    assert (await ReembolsoService(e.db).obtener_reembolso(e.cliente, e.obl.id)).cliente_id == e.cliente.id
    with pytest.raises(HTTPException) as error:
        await ReembolsoService(e.db).obtener_reembolso(e.otro, e.obl.id)
    assert error.value.status_code == 403
    e.venta.sucursal_id = e.s2
    e.session.commit()
    with pytest.raises(HTTPException) as error:
        await ReembolsoService(e.db).ejecutar_reembolso(e.personal, e.obl.id, uuid.uuid4(), uuid.uuid4())
    assert error.value.status_code == 403 and e.gateway.llamadas == 0
    e.venta.sucursal_id = e.s1
    e.session.commit()
    assert (await ReembolsoService(e.db).ejecutar_reembolso(
        e.personal, e.obl.id, uuid.uuid4(), uuid.uuid4())).estado == "EN_PROCESO"


@pytest.mark.asyncio
async def test_parcial_b_no_habilitado_no_crea_ejecucion(reembolso):
    from backend.app.core.modules.posventa.models import EjecucionReembolso
    e = reembolso
    e.obl.monto_bob = e.comp.monto_bob = Decimal("100")
    e.comp.centavos_usd, e.comp.monto_usd = 1429, Decimal("14.29")
    e.session.commit()
    with pytest.raises(HTTPException) as error:
        await ReembolsoService(e.db).ejecutar_reembolso(e.admin, e.obl.id, uuid.uuid4(), uuid.uuid4())
    assert error.value.status_code == 409 and e.gateway.llamadas == 0
    assert not e.session.execute(select(EjecucionReembolso)).scalars().all()


@pytest.mark.asyncio
async def test_regresion_solicitud_debe_usar_centavos_originales_no_tasa_fija(reembolso):
    e = reembolso
    # Crear por la ruta de solicitud real; no colocar el administrador como titular.
    e.session.delete(e.comp)
    e.session.delete(e.obl)
    e.session.commit()
    dto = ReembolsoSolicitudDTO(origen_tipo="VENTA", origen_id=e.v1, motivo_codigo="OTRO")
    resultado = await ReembolsoService(e.db).solicitar_reembolso(e.admin, dto, uuid.uuid4())
    assert resultado.cliente_id == e.cliente.id
    assert resultado.componentes[0].centavos_usd == 3000
    assert resultado.componentes[0].pago_id == e.pago.id
