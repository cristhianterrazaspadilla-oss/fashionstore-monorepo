"""SQL/HTTP y servicios reales en SQLite aislado. No acredita bloqueos PostgreSQL."""
import uuid
from datetime import timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from test_bloque_seguridad import datos, insertar, AHORA, peticion
from backend.app.core.modules.catalogo.models import Producto, VarianteProducto, Categoria
from backend.app.core.modules.inventario.models import InventarioSucursal, CupoCaja, MovimientoInventario
from backend.app.core.modules.identidad_empresas.models import Plan, Rol, Usuario, Empleado
from backend.app.core.modules.ventas_pagos.models import Venta, DetalleVenta, Pago, TurnoCaja
from backend.app.core.modules.ventas_pagos.schemas import TurnoCrearDTO, VentaOfflineCrearDTO, TurnoCerrarDTO
from backend.app.core.modules.ventas_pagos.services.caja_service import CajaService
from backend.app.core.modules.ventas_pagos.services.venta_presencial_service import VentaPresencialService, VentaPresencialLiquidarDTO
from backend.app.core.modules.ventas_pagos.services.pedido_service import Comprobante


@pytest.mark.asyncio
async def test_selector_cajero_incluye_etiquetas_sin_costos(caja):
    from backend.app.core.dependencias import get_usuario_opcional
    from backend.app.core.modules.catalogo.models import Talla, Color
    e = caja
    for vid, sku, talla, color in ((e.variante, "FS-001-1", "M", "Negro"), (e.variante2, "FS-001-2", "L", "Azul")):
        v = e.session.get(VarianteProducto, vid)
        v.sku = sku
        v.talla_id = insertar(e, Talla, empresa_id=e.a, nombre=talla)
        v.color_id = insertar(e, Color, empresa_id=e.a, nombre=color)
    e.session.commit()
    async def actor(): return e.cajero
    e.app.dependency_overrides[get_usuario_opcional] = actor
    r = await peticion(e, "GET", "/variantes")
    assert r.status_code == 200, r.text
    filas = {f["sku"]: f for f in r.json()}
    for sku, talla, color in (("FS-001-1", "M", "Negro"), ("FS-001-2", "L", "Azul")):
        assert filas[sku]["producto_nombre"] == "Producto A"
        assert filas[sku]["talla_nombre"] == talla and filas[sku]["color_nombre"] == color
        assert "costo_promedio" not in filas[sku] and "costo_ultimo" not in filas[sku]


@pytest.fixture
def reportes(datos):
    e = datos
    for empresa, sucursales in ((e.a, (e.s1, e.s2)), (e.b, (e.sb,))):
        categoria = insertar(e, Categoria, empresa_id=empresa, nombre="Ropa")
        for n in range(12):
            p = insertar(e, Producto, empresa_id=empresa, nombre=f"Prenda {n:02}", categoria_id=categoria)
            v = insertar(e, VarianteProducto, empresa_id=empresa, producto_id=p, sku=f"{empresa}-{n}")
            for s in sucursales:
                cantidad = (12 - n) if s != e.s2 else (n + 1)
                for fecha, uds in ((AHORA, cantidad), (AHORA - timedelta(days=200), 500)):
                    venta = insertar(e, Venta, empresa_id=empresa, sucursal_id=s, estado="PAGADA", total=Decimal(uds * 10), creada_en=fecha)
                    insertar(e, DetalleVenta, venta_id=venta, variante_id=v, cantidad=uds, precio_unitario=Decimal("10"))
                insertar(e, InventarioSucursal, variante_id=v, sucursal_id=s, disponible=n, reservado=50)
    e.session.commit()
    return e


@pytest.mark.asyncio
async def test_pregunta6_diez_por_sucursal_periodo_empresa_y_ventas_nuevas(reportes):
    e = reportes
    cuerpo = {"consulta": "Mostrá los 10 productos más vendidos durante los últimos tres meses, agrupados por sucursal"}
    r = await peticion(e, "POST", "/analitica/reportes-interpretados", json=cuerpo)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tipo_reporte"] == "RANKING_PRODUCTOS"
    assert d["filtros_efectivos"]["desde"].startswith("2026-08-08T04:00")
    assert d["filtros_efectivos"]["limite"] == 10
    filas = d["filas"]
    assert len(filas) == 20
    for s, primero in ((e.s1, "Prenda 00"), (e.s2, "Prenda 11")):
        grupo = [f for f in filas if f["sucursal_id"] == str(s)]
        assert len(grupo) == 10 and grupo[0]["producto_nombre"] == primero
        assert [f["unidades_vendidas"] for f in grupo] == list(range(12, 2, -1))
    assert any("row_number() OVER (PARTITION BY" in sql for sql in e.sql)
    assert all(f["sucursal_id"] != str(e.sb) for f in filas)
    v = insertar(e, Venta, empresa_id=e.a, sucursal_id=e.s1, estado="PAGADA", total=Decimal("900"), creada_en=AHORA)
    insertar(e, DetalleVenta, venta_id=v, variante_id=e.variante, cantidad=90, precio_unitario=Decimal("10"))
    e.session.commit()
    nuevo = await peticion(e, "POST", "/ia/reportes-interpretados", json=cuerpo)
    assert nuevo.status_code == 200, nuevo.text
    assert nuevo.json()["filas"][0]["unidades_vendidas"] == 90


@pytest.mark.asyncio
@pytest.mark.parametrize("consulta,tipo,extra", [
    ("Mostrame las ventas de septiembre de 2026 agrupadas por sucursal", "VENTAS_POR_SUCURSAL", {}),
    ("¿Cuáles fueron los diez productos más vendidos este mes?", "RANKING_PRODUCTOS", {}),
    ("Generá un gráfico de ventas por semana", "EVOLUCION_SEMANAL", {}),
    ("Compará las ventas de las sucursales durante los últimos tres meses", "VENTAS_POR_SUCURSAL", {}),
    ("Mostrame los productos con menor existencia", "MENOR_EXISTENCIA", {}),
    ("¿Qué categorías generaron mayores ingresos durante este período?", "INGRESOS_POR_CATEGORIA", {"desde": "2026-11-01", "hasta": "2026-11-09"}),
])
async def test_ejemplos_examen_datos_reales_sin_gemini(reportes, consulta, tipo, extra):
    r = await peticion(reportes, "POST", "/analitica/reportes-interpretados", json={"consulta": consulta, **extra})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tipo_reporte"] == tipo and d["filtros_efectivos"]["proveedor"] == "DETERMINISTA"
    if "septiembre" in consulta:
        assert d["filas"] == []
    elif tipo == "MENOR_EXISTENCIA":
        assert len(d["filas"]) == 24 and d["filas"][0]["disponible"] == 0
        assert max(f["disponible"] for f in d["filas"]) == 11
    elif tipo == "RANKING_PRODUCTOS":
        assert len(d["filas"]) == 10 and all(f["unidades_vendidas"] == 13 for f in d["filas"])
    elif tipo == "INGRESOS_POR_CATEGORIA":
        assert d["filas"][0]["total_ingresos_bob"] == 1560
    else:
        assert d["filas"]


@pytest.mark.asyncio
@pytest.mark.parametrize("consulta", ["Ventas de septiembre por sucursal", "Ingresos por categorías durante este período", "Pronostica el clima", "Ventas de sucursal Desconocida"])
async def test_aclaracion_no_inventa_periodos_o_ambitos(reportes, consulta):
    r = await peticion(reportes, "POST", "/analitica/reportes-interpretados", json={"consulta": consulta})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("respuesta", ["RANKING_PRODUCTOS", "EVOLUCION_SEMANAL", "ERROR"])
async def test_gemini_simulado_no_cambia_ranking_fechas_ni_tenant(reportes, monkeypatch, respuesta):
    import httpx
    from backend.app.core.config import settings
    original = httpx.AsyncClient
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "ficticia-prueba-sin-red")
    class GeminiSimulado:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            if respuesta == "ERROR":
                return httpx.Response(503)
            contenido = '{"tipo_reporte":"' + respuesta + '","desde":"1900-01-01","empresa_id":"ajena"}'
            if "resumen ejecutivo" in kwargs["json"]["contents"][0]["parts"][0]["text"]:
                contenido = "Explicación simulada de los datos calculados."
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": contenido}]}}]})
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: original(*a, **k) if "transport" in k else GeminiSimulado())
    r = await peticion(reportes, "POST", "/analitica/reportes-interpretados", json={
        "consulta": "Mostrá los 10 productos más vendidos durante los últimos tres meses, agrupados por sucursal"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tipo_reporte"] == "RANKING_PRODUCTOS" and len(d["filas"]) == 20
    assert d["filtros_efectivos"]["desde"].startswith("2026-08-08")
    assert d["filtros_efectivos"]["empresa_id"] == str(reportes.a)
    assert d["filtros_efectivos"]["proveedor"] == ("GEMINI" if respuesta == "RANKING_PRODUCTOS" else "FALLBACK_DETERMINISTA")


@pytest.mark.asyncio
async def test_filtros_nombrados_orden_ingresos_y_stock_por_sucursal(reportes):
    e = reportes
    r = await peticion(e, "POST", "/analitica/reportes-interpretados", json={
        "consulta": 'Los 2 productos más vendidos de sucursal "Sucursal A2", producto "Prenda 11", categoría "Ropa" este mes'})
    assert r.status_code == 200, r.text
    assert len(r.json()["filas"]) == 1 and r.json()["filas"][0]["unidades_vendidas"] == 12
    r = await peticion(e, "POST", "/analitica/reportes-interpretados", json={
        "consulta": "Menor existencia por sucursal", "limite": 2})
    assert r.status_code == 200, r.text
    assert len(r.json()["filas"]) == 4 and sorted(f["disponible"] for f in r.json()["filas"]) == [0, 0, 1, 1]
    categoria = insertar(e, Categoria, empresa_id=e.a, nombre="Accesorios caros")
    producto = insertar(e, Producto, empresa_id=e.a, nombre="Accesorio", categoria_id=categoria)
    variante = insertar(e, VarianteProducto, empresa_id=e.a, producto_id=producto)
    venta = insertar(e, Venta, empresa_id=e.a, sucursal_id=e.s1, estado="PAGADA", creada_en=AHORA, total=Decimal("2000"))
    insertar(e, DetalleVenta, venta_id=venta, variante_id=variante, cantidad=1, precio_unitario=Decimal("2000"))
    e.session.commit()
    r = await peticion(e, "POST", "/analitica/reportes-interpretados", json={"consulta": "Qué categorías generaron mayores ingresos este mes"})
    assert r.status_code == 200, r.text
    assert r.json()["filas"][0]["categoria_nombre"] == "Accesorios caros"


@pytest.fixture
def caja(datos, monkeypatch):
    e = datos
    import backend.app.core.modules.ventas_pagos.services.caja_service as modulo
    monkeypatch.setattr(modulo, "utcnow", lambda: AHORA)
    # Adaptador de savepoint SQLite, no sustituye reglas del servicio.
    class Savepoint:
        async def __aenter__(self): self.tx = e.session.begin_nested(); return self
        async def __aexit__(self, tipo, valor, tb): self.tx.rollback() if tipo else self.tx.commit()
    e.db.begin_nested = Savepoint
    e.session.get(Plan, e.pro).permite_operacion_offline = True
    rol = insertar(e, Rol, nombre="CAJERO")
    uid = insertar(e, Usuario, empresa_id=e.a, rol_id=rol, estado="ACTIVO")
    insertar(e, Empleado, usuario_id=uid, sucursal_id=e.s1)
    e.cajero = e.session.execute(select(Usuario).where(Usuario.id == uid).options(selectinload(Usuario.rol), selectinload(Usuario.empleado))).scalar_one()
    e.session.get(VarianteProducto, e.variante).precio = Decimal("10")
    e.variante2 = insertar(e, VarianteProducto, empresa_id=e.a, producto_id=e.producto, precio=Decimal("20"), costo_promedio=Decimal("4"))
    e.inv1 = insertar(e, InventarioSucursal, variante_id=e.variante, sucursal_id=e.s1, disponible=3, reservado=0, comprometido_caja=0)
    e.inv2 = insertar(e, InventarioSucursal, variante_id=e.variante2, sucursal_id=e.s1, disponible=2, reservado=0, comprometido_caja=0)
    e.session.commit()
    e.dto = TurnoCrearDTO(caja_id="CAJA-01", dispositivo_id=uuid.uuid4(), sucursal_id=e.s1, cajero_id=uid,
                         cupos=[{"variante_id": e.variante, "cantidad": 3}, {"variante_id": e.variante2, "cantidad": 2}])
    return e


@pytest.mark.asyncio
async def test_cu06_cu07_asignacion_multilinea_consulta_venta_y_reenvio(caja):
    e = caja
    srv = CajaService(e.db)
    t = await srv.habilitar_turno(e.dto, e.admin, uuid.uuid4())
    assert t.cajero_id == e.cajero.id and [c.otorgado for c in t.cupos] == [3, 2]
    fresh = await srv.obtener_turno_activo(e.cajero, e.dto.dispositivo_id)
    assert fresh.turno_id == t.turno_id and len(fresh.cupos) == 2
    body = VentaOfflineCrearDTO(operacion_id=uuid.uuid4(), vendida_local_en=AHORA, entregada_local_en=AHORA,
        version_precios=t.version_precios, lineas=[{"variante_id": e.variante, "cantidad": 2, "precio_autorizado_bob": 10},
        {"variante_id": e.variante2, "cantidad": 1, "precio_autorizado_bob": 20}], total_bob=40, efectivo_recibido_bob=50, cambio_entregado_bob=10)
    uno = await srv.registrar_venta_offline(t.turno_id, body, e.cajero)
    dos = await srv.registrar_venta_offline(t.turno_id, body, e.cajero)
    assert uno.venta_id == dos.venta_id == body.operacion_id and uno.total_bob == 40
    assert sorted(c["disponible_cupo"] for c in dos.cupos_restantes) == [1, 1]
    assert e.session.scalar(select(func.count(Pago.id)).where(Pago.venta_id == uno.venta_id)) == 1
    assert e.session.scalar(select(func.count(DetalleVenta.id)).where(DetalleVenta.venta_id == uno.venta_id)) == 2
    assert e.session.scalar(select(func.count(MovimientoInventario.id)).where(MovimientoInventario.referencia_id == uno.venta_id)) == 2
    with pytest.raises(HTTPException):
        await srv.registrar_venta_offline(t.turno_id, body.model_copy(update={"operacion_id": uuid.uuid4()}), e.cajero)
    assert e.session.scalar(select(func.count(Pago.id)).where(Pago.venta_id == uno.venta_id)) == 1


@pytest.mark.asyncio
async def test_supervision_http_libera_una_vez_y_reabre_misma_caja(caja):
    e = caja
    srv = CajaService(e.db)
    t = await srv.habilitar_turno(e.dto, e.admin, uuid.uuid4())
    body = VentaOfflineCrearDTO(operacion_id=uuid.uuid4(), vendida_local_en=AHORA, entregada_local_en=AHORA,
        version_precios=t.version_precios, lineas=[{"variante_id": e.variante, "cantidad": 2, "precio_autorizado_bob": 10},
        {"variante_id": e.variante2, "cantidad": 1, "precio_autorizado_bob": 20}], total_bob=40, efectivo_recibido_bob=40)
    await srv.registrar_venta_offline(t.turno_id, body, e.cajero)
    await srv.registrar_venta_offline(t.turno_id, body, e.cajero)
    cierre = await srv.cerrar_turno(t.turno_id, TurnoCerrarDTO(revision=1,
        ultima_secuencia_local=1, total_operaciones_locales=1, operaciones_pendientes=[], arqueo_efectivo_bob=40), e.cajero)
    assert cierre.estado == "CONCILIACION"
    e.usuario = e.cajero
    assert (await peticion(e, "GET", "/cajas/turnos/conciliacion")).status_code == 403
    e.usuario = e.admin_b
    assert (await peticion(e, "GET", "/cajas/turnos/conciliacion")).json() == []
    e.usuario = e.admin
    lista = await peticion(e, "GET", "/cajas/turnos/conciliacion")
    assert lista.status_code == 200 and lista.json()[0]["turno_id"] == str(t.turno_id)
    dto = {"revision": cierre.revision, "supervision_forzada": True,
        "arqueo_declarado_bob": 40,
        "motivo_supervision": "Conteo físico confirmado en prueba aislada",
        "evidencia_cierre": {"referencia_acta": "ACTA-AISLADA", "conteo_fisico_por_variante": [
            {"variante_id": str(e.variante), "cantidad_encontrada": 1},
            {"variante_id": str(e.variante2), "cantidad_encontrada": 1}]}}
    ruta = f"/cajas/turnos/{t.turno_id}/cerrar"
    r = await peticion(e, "POST", ruta, json=dto)
    assert r.status_code == 200 and r.json()["estado"] == "CERRADO", r.text
    assert (await peticion(e, "GET", f"/cajas/turnos/{t.turno_id}")).json()["estado"] == "CERRADO"
    assert (await peticion(e, "POST", ruta, json=dto)).status_code == 409
    assert e.session.get(InventarioSucursal, e.inv1).disponible == 1
    assert e.session.get(InventarioSucursal, e.inv2).disponible == 1
    assert e.session.scalar(select(func.count(Pago.id)).where(Pago.venta_id == body.operacion_id)) == 1
    assert e.session.scalar(select(func.count(MovimientoInventario.id)).where(MovimientoInventario.referencia_id == body.operacion_id)) == 2
    assert e.session.scalar(select(func.count(MovimientoInventario.id)).where(MovimientoInventario.tipo == "LIBERACION_CUPO_CAJA")) == 2
    nuevo = e.dto.model_copy(deep=True)
    nuevo.cajero_id = None
    for cupo in nuevo.cupos: cupo.cantidad = 1
    otro = await srv.habilitar_turno(nuevo, e.cajero, uuid.uuid4())
    assert otro.turno_id != t.turno_id and otro.caja_codigo == "CAJA-01" and len(otro.cupos) == 2


@pytest.mark.asyncio
async def test_lista_supervisor_encargado_solo_su_sucursal(caja):
    e = caja
    for sucursal in (e.s1, e.s2):
        insertar(e, TurnoCaja, empresa_id=e.a, sucursal_id=sucursal, cajero_id=e.cajero.id, estado="CONCILIACION")
    e.session.commit()
    e.usuario = e.personal
    r = await peticion(e, "GET", "/cajas/turnos/conciliacion")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1 and r.json()[0]["sucursal_id"] == str(e.s1)


@pytest.mark.asyncio
async def test_http_caja_habilita_y_consulta_todas_las_lineas_para_el_cajero(caja):
    e = caja
    r = await peticion(e, "POST", "/cajas/turnos", json=e.dto.model_dump(mode="json"), headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["empresa_id"] == str(e.a) and t["cajero_id"] == str(e.cajero.id)
    assert t["hora_central_en"] and len(t["cupos"]) == 2
    e.usuario = e.cajero
    r = await peticion(e, "GET", "/cajas/turnos/activo", params={"dispositivo_id": str(e.dto.dispositivo_id)})
    assert r.status_code == 200 and r.json()["turno_id"] == t["turno_id"], r.text
    assert sorted(c["otorgado"] for c in r.json()["cupos"]) == [2, 3]
    e.usuario = e.admin_b
    assert (await peticion(e, "GET", "/cajas/turnos/"+t["turno_id"])).status_code == 404


@pytest.mark.asyncio
async def test_habilitacion_sin_cajero_conserva_hash_anterior(caja):
    from backend.app.core.idempotencia_ciclo3 import hash_payload
    from backend.app.core.modules.ventas_pagos.models import RegistroIdempotencia
    e = caja
    dto = e.dto.model_copy(update={"cajero_id": None})
    payload = dto.model_dump(mode="json"); payload.pop("cajero_id")
    clave = uuid.uuid4()
    await CajaService(e.db).habilitar_turno(dto, e.cajero, clave)
    registro = e.session.execute(select(RegistroIdempotencia).where(RegistroIdempotencia.clave == clave)).scalar_one()
    assert registro.hash_solicitud == hash_payload(payload)
    assert (await CajaService(e.db).habilitar_turno(dto, e.cajero, clave)).cajero_id == e.cajero.id


@pytest.mark.asyncio
async def test_cu06_exceso_rechaza_todas_las_lineas_y_titular_ajeno(caja):
    e = caja
    e.dto.cupos[1].cantidad = 3
    with pytest.raises(HTTPException) as error:
        await CajaService(e.db).habilitar_turno(e.dto, e.admin, uuid.uuid4())
    assert error.value.status_code == 409
    assert e.session.get(InventarioSucursal, e.inv1).disponible == 3
    assert e.session.get(InventarioSucursal, e.inv2).disponible == 2
    assert not e.session.scalar(select(func.count(TurnoCaja.id)))
    e.dto.cajero_id = e.cliente_b.id
    with pytest.raises(HTTPException) as error:
        await CajaService(e.db).habilitar_turno(e.dto, e.admin, uuid.uuid4())
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_cierre_con_pendientes_retiene_cada_variante(caja):
    e = caja
    srv = CajaService(e.db)
    t = await srv.habilitar_turno(e.dto, e.admin, uuid.uuid4())
    r = await srv.cerrar_turno(t.turno_id, TurnoCerrarDTO(revision=1,
        ultima_secuencia_local=1, total_operaciones_locales=1, operaciones_pendientes=[uuid.uuid4()]), e.cajero)
    assert r.estado == "CONCILIACION" and not r.cupos_devueltos
    cupos = e.session.execute(select(CupoCaja).where(CupoCaja.turno_id == t.turno_id)).scalars().all()
    assert len(cupos) == 2 and all(c.liberado == 0 for c in cupos)
    assert e.session.get(InventarioSucursal, e.inv1).comprometido_caja == 3
    assert e.session.get(InventarioSucursal, e.inv2).comprometido_caja == 2


@pytest.mark.asyncio
async def test_cu06_no_asigna_otro_cajero_sucursal_ajena_ni_lineas_duplicadas(caja):
    e = caja
    e.dto.cajero_id = e.otro.id
    with pytest.raises(HTTPException) as error:
        await CajaService(e.db).habilitar_turno(e.dto, e.cajero, uuid.uuid4())
    assert error.value.status_code == 403
    e.dto.cajero_id = e.cajero.id
    e.dto.sucursal_id = e.s2
    with pytest.raises(HTTPException) as error:
        await CajaService(e.db).habilitar_turno(e.dto, e.admin, uuid.uuid4())
    assert error.value.status_code == 403
    e.dto.sucursal_id = e.s1
    e.dto.cupos.append(e.dto.cupos[0])
    with pytest.raises(HTTPException) as error:
        await CajaService(e.db).habilitar_turno(e.dto, e.admin, uuid.uuid4())
    assert error.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("multilinea", [False, True])
async def test_cu19_efectivo_lineas_total_inventario_y_comprobante(caja, multilinea):
    e = caja
    lineas = [{"variante_id": e.variante, "cantidad": 2, "precio_unitario_bob": 10}]
    if multilinea:
        lineas.append({"variante_id": e.variante2, "cantidad": 1, "precio_unitario_bob": 20})
    dto = VentaPresencialLiquidarDTO(sucursal_id=e.s1, lineas=lineas, medio_pago="EFECTIVO", efectivo_recibido_bob=50)
    r = await VentaPresencialService(e.db).liquidar(e.admin, dto, uuid.uuid4())
    assert r.total_bob == (40 if multilinea else 20)
    assert e.session.get(InventarioSucursal, e.inv1).disponible == 1
    assert e.session.get(InventarioSucursal, e.inv2).disponible == (1 if multilinea else 2)
    doc = e.session.get(Comprobante, r.comprobante_id).documento
    assert len(doc["lineas"]) == len(lineas)
    assert [int(l["cantidad"]) for l in doc["lineas"]] == ([2, 1] if multilinea else [2])
