import logging
import uuid
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, LargeBinary, select
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import selectinload

from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.modules.identidad_empresas.models import Empresa, Plan, Suscripcion, Rol, Usuario, Cliente, Empleado
from backend.app.core.modules.organizacion.models import Ciudad, Sucursal
from backend.app.core.modules.ventas_pagos.models import Venta, PedidoEntrega
from backend.app.core.modules.catalogo.models import Producto, VarianteProducto
from backend.app.core.modules.identidad_empresas.services.plan_service import PlanService
from backend.app.core.modules.ventas_pagos.repositories.venta_repository import VentaRepository
from backend.app.core.modules.analitica.services import ml_service

AHORA = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
BASE = "/api/v1"


def insertar(e, modelo, **datos):
    """Datos sintéticos, columnas ORM reales; no seed ni DDL de producción."""
    for c in modelo.__table__.columns:
        if c.name in datos or c.nullable:
            continue
        if c.default is not None:
            d = c.default.arg
            datos[c.name] = d(None) if callable(d) else d
        elif isinstance(c.type, UUID):
            datos[c.name] = uuid.uuid4()
        elif isinstance(c.type, Boolean):
            datos[c.name] = True
        elif isinstance(c.type, DateTime):
            datos[c.name] = AHORA
        elif isinstance(c.type, Date):
            datos[c.name] = date(2026, 11, 8)
        elif isinstance(c.type, Numeric):
            datos[c.name] = Decimal("0")
        elif isinstance(c.type, Integer):
            datos[c.name] = 1
        elif isinstance(c.type, JSONB):
            datos[c.name] = {}
        elif isinstance(c.type, LargeBinary):
            datos[c.name] = b"dato-sintetico"
        else:
            datos[c.name] = "sintetico-" + uuid.uuid4().hex[:8]
    e.session.execute(modelo.__table__.insert().values(**datos))
    return datos.get("id", datos.get("usuario_id"))


@pytest.fixture
def datos(entorno, monkeypatch, tmp_path):
    e = entorno
    import backend.app.core.reloj as reloj
    import backend.app.core.modules.identidad_empresas.services.plan_service as planes
    monkeypatch.setattr(reloj, "utcnow", lambda: AHORA)
    monkeypatch.setattr(reloj.RelojSistema, "ahora", lambda self: AHORA)
    monkeypatch.setattr(planes, "utcnow", lambda: AHORA)
    monkeypatch.setenv("FASHIONSTORE_ARTEFACTOS_DIR", str(tmp_path))
    monkeypatch.setattr(ml_service, "_obtener_directorio_artefactos", lambda: tmp_path)
    e.a = insertar(e, Empresa, estado="ACTIVA", codigo="EMPRESA-A")
    e.b = insertar(e, Empresa, estado="ACTIVA", codigo="EMPRESA-B")
    e.pro = insertar(e, Plan, codigo="PROFESIONAL", reportes_generativos=True, modelos_ml=True)
    e.basico = insertar(e, Plan, codigo="BASICO", reportes_generativos=False, modelos_ml=False)
    for empresa in (e.a, e.b):
        insertar(e, Suscripcion, empresa_id=empresa, plan_id=e.pro, version=1,
                 inicia_en=AHORA-timedelta(days=30), vence_en=AHORA+timedelta(days=1))
    ciudad = insertar(e, Ciudad, nombre="Ciudad de prueba")
    e.s1 = insertar(e, Sucursal, empresa_id=e.a, ciudad_id=ciudad, nombre="Sucursal A1")
    e.s2 = insertar(e, Sucursal, empresa_id=e.a, ciudad_id=ciudad, nombre="Sucursal A2")
    e.sb = insertar(e, Sucursal, empresa_id=e.b, ciudad_id=ciudad, nombre="Sucursal B")
    roles = {r: insertar(e, Rol, nombre=r) for r in ("ADMINISTRADOR", "ENCARGADO", "CLIENTE", "SUPERADMIN")}

    def usuario(empresa, rol, sucursal=None):
        uid = insertar(e, Usuario, empresa_id=empresa, rol_id=roles[rol], estado="ACTIVO")
        if rol == "CLIENTE":
            insertar(e, Cliente, usuario_id=uid)
        if sucursal:
            insertar(e, Empleado, usuario_id=uid, sucursal_id=sucursal)
        return e.session.execute(select(Usuario).where(Usuario.id == uid).options(
            selectinload(Usuario.rol), selectinload(Usuario.empleado), selectinload(Usuario.cliente)
        )).scalars().one()

    e.admin = usuario(e.a, "ADMINISTRADOR")
    e.admin_b = usuario(e.b, "ADMINISTRADOR")
    e.personal = usuario(e.a, "ENCARGADO", e.s1)
    e.cliente = usuario(e.a, "CLIENTE")
    e.otro = usuario(e.a, "CLIENTE")
    e.cliente_b = usuario(e.b, "CLIENTE")
    e.plataforma = usuario(None, "SUPERADMIN")

    def venta(empresa, sucursal, cliente, total, numero):
        vid = insertar(e, Venta, empresa_id=empresa, sucursal_id=sucursal, cliente_id=cliente.id,
                       estado="PAGADA", canal="WEB", numero=numero, total=Decimal(total),
                       subtotal=Decimal(total), creada_en=AHORA, confirmada_en=AHORA)
        pid = insertar(e, PedidoEntrega, empresa_id=empresa, sucursal_id=sucursal,
                       cliente_id=cliente.id, venta_id=vid, modalidad="RECOJO", estado="SOLICITADO")
        return vid, pid

    e.v1, e.p1 = venta(e.a, e.s1, e.cliente, "111", "A-111")
    e.v2, e.p2 = venta(e.a, e.s2, e.cliente, "222", "A-222")
    e.vb, e.pb = venta(e.b, e.sb, e.cliente_b, "999", "B-999")
    e.producto = insertar(e, Producto, empresa_id=e.a, nombre="Producto A")
    e.variante = insertar(e, VarianteProducto, empresa_id=e.a, producto_id=e.producto)
    e.session.commit()
    e.usuario = e.admin
    e.sql.clear()
    return e


async def peticion(e, metodo, ruta, **kwargs):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=e.app, raise_app_exceptions=False),
                                base_url="http://aislado") as client:
        return await client.request(metodo, BASE+ruta, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("recurso", ["venta", "comprobante", "entrega", "transicion", "cancelar", "reporte"])
async def test_admin_no_accede_a_empresa_b(datos, recurso):
    e = datos
    rutas = {
        "venta": ("GET", f"/ventas/{e.vb}", {}),
        "comprobante": ("GET", f"/ventas/{e.vb}/comprobante", {}),
        "entrega": ("GET", f"/entregas/{e.pb}", {}),
        "transicion": ("PATCH", f"/entregas/{e.pb}/estado", {"json": {"estado": "PREPARADO"}}),
        "cancelar": ("POST", f"/entregas/{e.pb}/cancelar", {}),
        "reporte": ("GET", "/analitica/ventas-sucursal", {"params": {"sucursal": str(e.sb)}}),
    }
    metodo, ruta, kw = rutas[recurso]
    r = await peticion(e, metodo, ruta, **kw)
    assert r.status_code in (403, 404), r.text
    assert e.session.get(PedidoEntrega, e.pb).estado == "SOLICITADO"
    assert any("empresa_id" in sql and "WHERE" in sql for sql in e.sql)


@pytest.mark.asyncio
async def test_cola_filtra_empresa_y_conteo(datos):
    e = datos
    r = await peticion(e, "GET", "/entregas/cola")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 2
    assert {x["id"] for x in r.json()["items"]} == {str(e.p1), str(e.p2)}
    consultas = [s for s in e.sql if "FROM comercial.pedidos_entrega" in s]
    assert len(consultas) >= 2
    assert all("WHERE comercial.pedidos_entrega.empresa_id =" in s for s in consultas)
    assert (await peticion(e, "GET", "/entregas/cola", params={"sucursal_id": str(e.sb)})).status_code == 404


@pytest.mark.asyncio
async def test_personal_limitado_y_acceso_legitimo(datos):
    e = datos
    e.usuario = e.personal
    for ruta in (f"/ventas/{e.v2}/comprobante", f"/entregas/{e.p2}",
                 f"/analitica/ventas-sucursal?sucursal={e.s2}"):
        assert (await peticion(e, "GET", ruta)).status_code == 403
    assert (await peticion(e, "PATCH", f"/entregas/{e.p2}/estado", json={"estado": "PREPARADO"})).status_code == 403
    for ruta in (f"/ventas/{e.v1}/comprobante", f"/entregas/{e.p1}",
                 f"/analitica/ventas-sucursal?sucursal={e.s1}"):
        r = await peticion(e, "GET", ruta)
        assert r.status_code == 200, r.text
    r = await peticion(e, "PATCH", f"/entregas/{e.p1}/estado", json={"estado": "PREPARADO"})
    assert r.status_code == 200, r.text
    assert e.session.get(PedidoEntrega, e.p1).estado == "PREPARADO"


@pytest.mark.asyncio
async def test_cliente_propietario_y_plataforma(datos):
    e = datos
    e.usuario = e.otro
    assert (await peticion(e, "GET", f"/ventas/{e.v1}/comprobante")).status_code == 403
    assert (await peticion(e, "GET", f"/entregas/{e.p1}")).status_code == 403
    e.usuario = e.cliente
    assert (await peticion(e, "GET", f"/ventas/{e.v1}/comprobante")).status_code == 200
    r = await peticion(e, "GET", "/entregas/mis-pedidos")
    assert r.status_code == 200 and r.json()["total"] == 2
    e.usuario = e.plataforma
    assert (await peticion(e, "GET", "/entregas/cola")).status_code == 403
    assert (await peticion(e, "GET", f"/ventas/{e.v1}")).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("prefijo", ["/analitica", "/ia"])
async def test_alias_reporte_aislado_y_autorizado(datos, prefijo):
    e = datos
    for actor in (e.cliente, e.personal, e.plataforma):
        e.usuario = actor
        assert (await peticion(e, "POST", prefijo+"/reportes", json={"consulta": "ventas por sucursal"})).status_code == 403
    for actor, esperados in ((e.admin, {"111.00", "222.00"}), (e.admin_b, {"999.00"})):
        e.usuario = actor
        r = await peticion(e, "POST", prefijo+"/reportes", json={"consulta": "ventas por sucursal"})
        assert r.status_code == 200, r.text
        filas = r.json()["datos"]["por_sucursal"]
        assert {f["ingresos"] for f in filas} == esperados
    consultas = [s for s in e.sql if "sum(comercial.ventas.total)" in s]
    assert consultas and all("comercial.ventas.empresa_id =" in s and "organizacion.sucursales.empresa_id =" in s for s in consultas)


@pytest.mark.asyncio
@pytest.mark.parametrize("prefijo", ["/analitica", "/ia"])
async def test_reporte_tipado_valida_empresa_y_rol(datos, prefijo):
    e = datos
    cuerpo = {"consulta": "ventas", "tipo_reporte": "VENTAS_POR_SUCURSAL"}
    e.usuario = e.cliente
    assert (await peticion(e, "POST", prefijo+"/reportes-interpretados", json=cuerpo)).status_code == 403
    e.usuario = e.admin
    assert (await peticion(e, "POST", prefijo+"/reportes-interpretados", json={**cuerpo, "sucursal_id": str(e.sb)})).status_code == 404
    r = await peticion(e, "POST", prefijo+"/reportes-interpretados", json=cuerpo)
    assert r.status_code == 200, r.text
    assert r.json()["totales"]["total_general_ingresos_bob"] == 333


@pytest.mark.asyncio
@pytest.mark.parametrize("estado,plan,permitido", [
    ("vigente", "basico", False), ("vigente", "pro", True),
    ("gracia", "pro", True), ("limite_gracia", "pro", False),
    ("vencida", "pro", False), ("futura", "pro", False),
])
async def test_capacidad_con_suscripcion_real(datos, estado, plan, permitido):
    e = datos
    sus = e.session.execute(select(Suscripcion).where(Suscripcion.empresa_id == e.a)).scalars().one()
    sus.plan_id = getattr(e, plan)
    if estado == "gracia": sus.vence_en = AHORA-timedelta(hours=71, minutes=59)
    if estado == "limite_gracia": sus.vence_en = AHORA-timedelta(hours=72)
    if estado == "vencida": sus.vence_en = AHORA-timedelta(hours=73)
    if estado == "futura": sus.inicia_en, sus.vence_en = AHORA+timedelta(days=1), AHORA+timedelta(days=2)
    e.session.commit()
    r = await peticion(e, "POST", "/analitica/reportes", json={"consulta": "ventas"})
    assert r.status_code == (200 if permitido else 403), r.text
    ml = await peticion(e, "GET", "/analitica/pronosticos",
                        params={"origen_datos": "SINTETICO_REPRODUCIBLE"})
    assert ml.status_code == (200 if permitido else 403), ml.text
    for capacidad in ("reportes_generativos", "modelos_ml"):
        if permitido:
            assert (await PlanService(e.db).exigir_capacidad_analitica(e.a, capacidad, AHORA)).habilitado
        else:
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as ex:
                await PlanService(e.db).exigir_capacidad_analitica(e.a, capacidad, AHORA)
            assert ex.value.status_code == 403
    # Las consultas convencionales no heredan el bloqueo de nueva analítica.
    r = await peticion(e, "GET", "/analitica/ventas-sucursal", params={"sucursal": str(e.s1)})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_renovacion_futura_no_desplaza_plan_actual(datos):
    e = datos
    insertar(e, Suscripcion, empresa_id=e.a, plan_id=e.basico, version=2,
             inicia_en=AHORA+timedelta(days=2), vence_en=AHORA+timedelta(days=30))
    e.session.commit()
    assert (await PlanService(e.db).exigir_capacidad_analitica(e.a, "modelos_ml", AHORA)).plan_codigo == "PROFESIONAL"


@pytest.mark.asyncio
async def test_ml_restringido_antes_de_consultar_o_entrenar(datos):
    e = datos
    sus = e.session.execute(select(Suscripcion).where(Suscripcion.empresa_id == e.a)).scalars().one()
    sus.plan_id = e.basico
    e.session.commit()
    for metodo, ruta, cuerpo in (("GET", "/analitica/pronosticos", None),
                                 ("GET", "/analitica/grupos-productos", None),
                                 ("POST", "/analitica/entrenamientos/supervisado", {}),
                                 ("POST", "/analitica/entrenamientos/no-supervisado", {})):
        r = await peticion(e, metodo, ruta, **({"json": cuerpo} if cuerpo is not None else {}))
        assert r.status_code == 403, r.text
    assert not any("FROM catalogo.productos" in sql for sql in e.sql)


@pytest.mark.asyncio
@pytest.mark.parametrize("metodo,ruta", [
    ("GET", "/analitica/pronosticos"), ("GET", "/analitica/grupos-productos"),
    ("POST", "/analitica/entrenamientos/supervisado"),
    ("POST", "/analitica/entrenamientos/no-supervisado"),
])
async def test_ml_profesional_ejecuta_consultas_tenant(datos, metodo, ruta):
    e = datos
    kw = {"params" if metodo == "GET" else "json": {"origen_datos": "SINTETICO_REPRODUCIBLE"}}
    r = await peticion(e, metodo, ruta, **kw)
    assert r.status_code == 200, r.text
    consultas = [s for s in e.sql if "FROM catalogo.productos" in s]
    assert consultas and all("empresa_id =" in s for s in consultas)
    assert (await peticion(e, "GET", "/analitica/pronosticos", params={"sucursal": str(e.sb)})).status_code == 404


@pytest.mark.asyncio
async def test_historial_y_numero_de_venta_no_cruzan_empresa(datos):
    e = datos
    assert (await peticion(e, "GET", f"/clientes/{e.cliente_b.id}/compras")).status_code == 404
    r = await peticion(e, "GET", f"/clientes/{e.cliente.id}/compras")
    assert r.status_code == 200 and r.json()["total"] == 2, r.text
    assert (await peticion(e, "GET", "/ventas/B-999/comprobante")).status_code == 404
    assert (await peticion(e, "GET", "/ventas/A-111/comprobante")).status_code == 200


@pytest.mark.asyncio
async def test_repositorio_filtra_empresa_aun_con_sucursal_repetida(datos):
    e = datos
    insertar(e, Venta, empresa_id=e.b, sucursal_id=e.s1, cliente_id=e.cliente.id,
             estado="PAGADA", numero="B-INCONSISTENTE", canal="WEB", total=Decimal("9999"))
    e.session.commit()
    ventas, total = await VentaRepository(e.db).porSucursal(e.s1, empresa_id=e.a)
    assert total == 1 and [v.id for v in ventas] == [e.v1]
    ventas, total = await VentaRepository(e.db).porCliente(e.cliente.id, empresa_id=e.a)
    assert total == 2 and {v.id for v in ventas} == {e.v1, e.v2}


@pytest.mark.asyncio
async def test_error_publico_y_debug(datos, caplog):
    e = datos
    async def falla():
        raise RuntimeError("contenido-sensible-de-prueba")
    # La ruta se agrega una sola vez; solo existe en este proceso de pruebas.
    if not any(getattr(r, "path", None) == BASE+"/fallo-controlado" for r in e.app.routes):
        e.app.add_api_route(BASE+"/fallo-controlado", falla)
    with caplog.at_level(logging.ERROR):
        r = await peticion(e, "GET", "/fallo-controlado")
    assert r.status_code == 500
    assert r.json() == {"detail": "Error interno del servidor"}
    assert r.headers["X-Error-ID"] in caplog.text
    assert "contenido-sensible-de-prueba" not in r.text + caplog.text
    assert "RuntimeError" in caplog.text and "falla" in caplog.text
    assert (await peticion(e, "GET", "/debug-db")).status_code == 403
    e.usuario = e.plataforma
    assert (await peticion(e, "GET", "/debug-db")).status_code == 404
    e.app.dependency_overrides.pop(get_usuario_actual)
    assert (await peticion(e, "GET", "/debug-db")).status_code == 401


@pytest.mark.asyncio
async def test_http_5xx_sin_detalles_y_sin_excepcion_asgi(datos, caplog):
    from fastapi import HTTPException
    e = datos
    async def falla_http():
        raise HTTPException(status_code=503, detail="contenido-interno-de-prueba")
    if not any(getattr(r, "path", None) == BASE+"/fallo-http-controlado" for r in e.app.routes):
        e.app.add_api_route(BASE+"/fallo-http-controlado", falla_http)
    async def inesperado_controlado():
        raise RuntimeError("contenido-inesperado-de-prueba")
    if not any(getattr(r, "path", None) == BASE+"/inesperado-asgi" for r in e.app.routes):
        e.app.add_api_route(BASE+"/inesperado-asgi", inesperado_controlado)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=e.app, raise_app_exceptions=True),
                                base_url="http://aislado") as client:
        r = await client.get(BASE+"/fallo-http-controlado")
        inesperado = await client.get(BASE+"/inesperado-asgi")
    assert r.status_code == 503 and inesperado.status_code == 500
    assert r.json() == {"detail": "Error interno del servidor"}
    assert "contenido-interno-de-prueba" not in r.text + caplog.text
    assert "contenido-inesperado-de-prueba" not in inesperado.text + caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("condicion", ["empresa_suspendida", "plan_inactivo", "capacidad_desactivada"])
async def test_capacidad_configurable_y_estado(datos, condicion):
    e = datos
    if condicion == "empresa_suspendida":
        e.session.get(Empresa, e.a).estado = "SUSPENDIDA"
    elif condicion == "plan_inactivo":
        e.session.get(Plan, e.pro).activo = False
    else:
        plan = e.session.get(Plan, e.pro)
        plan.reportes_generativos = False
        plan.modelos_ml = False
    e.session.commit()
    assert (await peticion(e, "POST", "/ia/reportes", json={"consulta": "ventas"})).status_code == 403
    assert (await peticion(e, "GET", "/analitica/pronosticos")).status_code == 403


@pytest.mark.asyncio
async def test_cancelacion_solicita_solo_recurso_autorizado(datos, monkeypatch):
    from backend.app.core.modules.ventas_pagos.services.stripe_service import StripeService
    e = datos
    e.session.get(Venta, e.v1).estado = "PENDIENTE_PAGO"
    e.session.commit()

    async def worker_aislado(self, *, lote, empresa_id, venta_id):
        # Doble solo del límite con el job PostgreSQL/proveedor; el servicio,
        # autorización, recuperación y escritura de esta prueba son reales.
        assert (lote, empresa_id, venta_id) == (1, e.a, e.v1)
        pedido = e.session.execute(select(PedidoEntrega).where(
            PedidoEntrega.empresa_id == empresa_id, PedidoEntrega.venta_id == venta_id
        )).scalars().one()
        pedido.estado = "CANCELADO"
        e.session.commit()
        return {"canceladas": [str(venta_id)]}

    monkeypatch.setattr(StripeService, "cancelarVencidas", worker_aislado)
    r = await peticion(e, "POST", f"/entregas/{e.p1}/cancelar")
    assert r.status_code == 200 and r.json()["estado"] == "CANCELADO", r.text
    assert e.session.get(PedidoEntrega, e.pb).estado == "SOLICITADO"


@pytest.mark.asyncio
async def test_error_estructurado_conserva_codigo_publico_sin_datos_internos(datos, caplog):
    from fastapi import HTTPException
    e = datos
    async def falla_proveedor():
        raise HTTPException(status_code=503, detail={
            "codigo": "STRIPE_DESHABILITADO", "mensaje": "detalle-interno-sintetico",
            "dato_interno": "dato-sintetico-no-publico",
        })
    if not any(getattr(r, "path", None) == BASE+"/proveedor-controlado" for r in e.app.routes):
        e.app.add_api_route(BASE+"/proveedor-controlado", falla_proveedor)
    r = await peticion(e, "GET", "/proveedor-controlado")
    assert r.status_code == 503
    assert r.json()["detail"]["codigo"] == "STRIPE_DESHABILITADO"
    assert int(r.headers["content-length"]) == len(r.content)
    assert set(r.json()["detail"]) == {"codigo", "mensaje"}
    assert "detalle-interno-sintetico" not in r.text + caplog.text
    assert "dato-sintetico-no-publico" not in r.text + caplog.text


@pytest.fixture
def caja_offline(datos):
    from backend.app.core.modules.ventas_pagos.models import TurnoCaja
    from backend.app.core.modules.inventario.models import CupoCaja, InventarioSucursal
    e = datos
    e.turno_caja = insertar(e, TurnoCaja, empresa_id=e.a, cajero_id=e.admin.id, sucursal_id=e.s1,
        dispositivo_id=uuid.uuid4(), estado="ABIERTO", inicio_en=AHORA-timedelta(hours=1), vence_en=AHORA+timedelta(hours=7), version_precios="v1")
    e.cupo_caja = insertar(e, CupoCaja, empresa_id=e.a, turno_id=e.turno_caja, sucursal_id=e.s1,
        variante_id=e.variante, otorgado=2, consumido=0, liberado=0, mermado=0, precio_autorizado_bob=Decimal("10"))
    insertar(e, InventarioSucursal, variante_id=e.variante, sucursal_id=e.s1, comprometido_caja=2)
    e.session.commit()
    return e


@pytest.mark.asyncio
async def test_caja_reintento_inmutable_y_turno_original(caja_offline):
    from fastapi import HTTPException
    from backend.app.core.modules.ventas_pagos.services.caja_service import CajaService
    from backend.app.core.modules.ventas_pagos.schemas import VentaOfflineCrearDTO
    from backend.app.core.modules.inventario.models import CupoCaja, MovimientoInventario
    from backend.app.core.modules.ventas_pagos.models import Pago
    e = caja_offline
    cuerpo = dict(operacion_id=uuid.uuid4(), secuencia_local=1, vendida_local_en=AHORA, entregada_local_en=AHORA,
        version_precios="v1", lineas=[dict(variante_id=e.variante, cantidad=1, precio_autorizado_bob="10.00")],
        total_bob="10.00", efectivo_recibido_bob="20.00", cambio_entregado_bob="10.00")
    servicio = CajaService(e.db)
    primero = await servicio.registrar_venta_offline(e.turno_caja, VentaOfflineCrearDTO(**cuerpo), e.admin)
    repetido = await servicio.registrar_venta_offline(e.turno_caja, VentaOfflineCrearDTO(**cuerpo), e.admin)
    assert primero.venta_id == repetido.venta_id
    assert e.session.get(CupoCaja, e.cupo_caja).consumido == 1
    assert len(e.session.execute(select(Pago).where(Pago.venta_id == primero.venta_id)).scalars().all()) == 1
    assert len(e.session.execute(select(MovimientoInventario).where(MovimientoInventario.referencia_id == primero.venta_id)).scalars().all()) == 1
    with pytest.raises(HTTPException) as exc:
        await servicio.registrar_venta_offline(e.turno_caja, VentaOfflineCrearDTO(**{**cuerpo, "secuencia_local": 2}), e.admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_caja_rechaza_variantes_repetidas_y_venta_fuera_de_turno(caja_offline):
    from fastapi import HTTPException
    from backend.app.core.modules.ventas_pagos.services.caja_service import CajaService
    from backend.app.core.modules.ventas_pagos.schemas import VentaOfflineCrearDTO
    from backend.app.core.modules.inventario.models import CupoCaja
    e = caja_offline
    base = dict(operacion_id=uuid.uuid4(), secuencia_local=1, vendida_local_en=AHORA, entregada_local_en=AHORA,
        version_precios="v1", lineas=[dict(variante_id=e.variante, cantidad=1, precio_autorizado_bob="10")],
        total_bob="10", efectivo_recibido_bob="10", cambio_entregado_bob="0")
    for cambios in ({"lineas": base["lineas"] * 2, "total_bob": "20", "efectivo_recibido_bob": "20"},
                    {"vendida_local_en": AHORA+timedelta(hours=7), "entregada_local_en": AHORA+timedelta(hours=7)}):
        with pytest.raises(HTTPException) as exc:
            await CajaService(e.db).registrar_venta_offline(e.turno_caja, VentaOfflineCrearDTO(**{**base, **cambios}), e.admin)
        assert exc.value.status_code == 400
    assert e.session.get(CupoCaja, e.cupo_caja).consumido == 0


@pytest.mark.asyncio
async def test_caja_consulta_revalida_empresa_titular_y_sucursal(caja_offline):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from backend.app.core.modules.ventas_pagos.services.caja_service import CajaService
    from backend.app.core.modules.ventas_pagos.models import TurnoCaja
    e = caja_offline
    servicio = CajaService(e.db)
    turno = e.session.get(TurnoCaja, e.turno_caja)
    dto = await servicio.obtener_turno(e.turno_caja, e.admin)
    assert dto.empresa_id == e.a and dto.hora_central_en is not None
    assert dto.inicio_en.tzinfo is not None and dto.vence_en.tzinfo is not None
    assert len(dto.cupos) == 1 and dto.cupos[0].variante_id == e.variante
    assert any('inventario.cupos_caja.empresa_id' in sql for sql in e.sql)
    cajero_ajeno = SimpleNamespace(id=uuid.uuid4(), empresa_id=e.a, rol=SimpleNamespace(nombre='CAJERO'))
    for actor, codigo in ((e.admin_b, 404), (cajero_ajeno, 403)):
        with pytest.raises(HTTPException) as exc:
            await servicio.obtener_turno(e.turno_caja, actor)
        assert exc.value.status_code == codigo
    assert await servicio.obtener_turno_activo(cajero_ajeno, turno.dispositivo_id) is None
    turno.sucursal_id = e.s2
    e.session.commit()
    with pytest.raises(HTTPException) as exc:
        await servicio.obtener_turno(e.turno_caja, e.personal)
    assert exc.value.status_code == 403
