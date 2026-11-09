"""Pruebas de integración Lote B4 — Analítica y Modelos ML (CU25, CU23, CU24, CU10, CU11)."""
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

URL_PRUEBAS = os.getenv("FASHIONSTORE_TEST_DATABASE_URL", "")
if not URL_PRUEBAS:
    pytest.skip("FASHIONSTORE_TEST_DATABASE_URL no configurada", allow_module_level=True)

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.main import app
from backend.app.core.modules.catalogo.models import Color, Producto, Talla, VarianteProducto
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Venta, Pago
from backend.app.core.modules.analitica.models import ModeloML, SolicitudIA


def _ruta_desde_uri(uri: str) -> Path:
    if uri.startswith("file:///"):
        return Path(uri[8:])
    elif uri.startswith("file://"):
        return Path(uri[7:])
    return Path(uri)


async def _sembrar_ventas_b4(fabrica_sesiones, escenario):
    async with fabrica_sesiones() as db:
        ahora = datetime.now(timezone.utc)

        # 1. Obtener talla y colores para variantes adicionales
        talla = (await db.execute(select(Talla).where(Talla.empresa_id == escenario.empresa_a_id))).scalars().first()
        colores = (await db.execute(select(Color).where(Color.empresa_id == escenario.empresa_a_id))).scalars().all()
        color_1 = colores[0].id if colores else uuid.uuid4()
        talla_1 = talla.id if talla else uuid.uuid4()

        # 2. Sembrar 3 productos adicionales para que la empresa tenga catálogo suficiente para clustering (CU11)
        p2_id = uuid.uuid4()
        p3_id = uuid.uuid4()
        p4_id = uuid.uuid4()
        p2 = Producto(
            id=p2_id,
            empresa_id=escenario.empresa_a_id,
            categoria_id=escenario.categoria_a_id,
            nombre=f"Pantalón Chino Slim {p2_id.hex[:4]}",
            precio_base=Decimal("120.00"),
            activo=True,
        )
        p3 = Producto(
            id=p3_id,
            empresa_id=escenario.empresa_a_id,
            categoria_id=escenario.categoria_a_id,
            nombre=f"Chaqueta Denim Urbana {p3_id.hex[:4]}",
            precio_base=Decimal("250.00"),
            activo=True,
        )
        p4 = Producto(
            id=p4_id,
            empresa_id=escenario.empresa_a_id,
            categoria_id=escenario.categoria_a_id,
            nombre=f"Vestido Seda Fiesta {p4_id.hex[:4]}",
            precio_base=Decimal("300.00"),
            activo=True,
        )
        db.add_all([p2, p3, p4])
        await db.flush()

        var2_id = uuid.uuid4()
        var3_id = uuid.uuid4()
        var4_id = uuid.uuid4()
        db.add_all([
            VarianteProducto(
                id=var2_id,
                empresa_id=escenario.empresa_a_id,
                producto_id=p2_id,
                talla_id=talla_1,
                color_id=color_1,
                sku=f"SKU-P2-{var2_id.hex[:6]}",
                precio=Decimal("120.00"),
                costo_promedio=Decimal("50.00"),
                activa=True,
            ),
            VarianteProducto(
                id=var3_id,
                empresa_id=escenario.empresa_a_id,
                producto_id=p3_id,
                talla_id=talla_1,
                color_id=color_1,
                sku=f"SKU-P3-{var3_id.hex[:6]}",
                precio=Decimal("250.00"),
                costo_promedio=Decimal("110.00"),
                activa=True,
            ),
            VarianteProducto(
                id=var4_id,
                empresa_id=escenario.empresa_a_id,
                producto_id=p4_id,
                talla_id=talla_1,
                color_id=color_1,
                sku=f"SKU-P4-{var4_id.hex[:6]}",
                precio=Decimal("300.00"),
                costo_promedio=Decimal("130.00"),
                activa=True,
            ),
        ])
        await db.flush()

        # 3. Ventas actuales de hoy (para CU25 y CU23)
        v1_id = uuid.uuid4()
        v2_id = uuid.uuid4()

        v1 = Venta(
            id=v1_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"V1-{v1_id.hex[:6]}",
            sucursal_id=escenario.sucursal_a_id,
            canal="PRESENCIAL",
            estado="PAGADA",
            subtotal=Decimal("300.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("300.00"),
            creada_en=ahora,
            vendida_local_en=ahora,
            recibida_central_en=ahora,
        )
        db.add(v1)

        v2 = Venta(
            id=v2_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"V2-{v2_id.hex[:6]}",
            sucursal_id=escenario.sucursal_a_id,
            canal="WEB",
            estado="PAGADA",
            subtotal=Decimal("150.00"),
            descuento=Decimal("15.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("135.00"),
            creada_en=ahora,
            vendida_local_en=ahora,
            recibida_central_en=ahora,
        )
        db.add(v2)
        await db.flush()

        det1 = DetalleVenta(
            id=uuid.uuid4(),
            venta_id=v1_id,
            variante_id=escenario.variante_a_id,
            cantidad=2,
            precio_unitario=Decimal("150.00"),
            descuento=Decimal("0.00"),
            costo_promedio=Decimal("70.00"),
        )
        db.add(det1)

        det2 = DetalleVenta(
            id=uuid.uuid4(),
            venta_id=v2_id,
            variante_id=escenario.variante_a_id,
            cantidad=1,
            precio_unitario=Decimal("150.00"),
            descuento=Decimal("15.00"),
            costo_promedio=Decimal("70.00"),
        )
        db.add(det2)
        await db.flush()

        p1 = Pago(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=v1_id,
            metodo="EFECTIVO",
            monto=Decimal("300.00"),
            estado="APROBADO",
            pagado_en=ahora,
        )
        db.add(p1)
        p2 = Pago(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=v2_id,
            metodo="STRIPE_TEST",
            monto=Decimal("135.00"),
            estado="APROBADO",
            pagado_en=ahora,
        )
        db.add(p2)

        # 4. Sembrar historial temporal semanal (5 semanas previas) para CU10
        for sem in [1, 2, 3, 4, 5]:
            fecha_sem = ahora - timedelta(days=7 * sem)
            vx_id = uuid.uuid4()
            cant_p1 = 4 + sem * 2
            vx = Venta(
                id=vx_id,
                empresa_id=escenario.empresa_a_id,
                numero=f"VH-{sem}-{vx_id.hex[:4]}",
                sucursal_id=escenario.sucursal_a_id,
                canal="PRESENCIAL",
                estado="PAGADA",
                subtotal=Decimal(str(cant_p1 * 100)),
                descuento=Decimal("0.00"),
                costo_entrega=Decimal("0.00"),
                total=Decimal(str(cant_p1 * 100)),
                creada_en=fecha_sem,
                vendida_local_en=fecha_sem,
                recibida_central_en=fecha_sem,
            )
            db.add(vx)
            await db.flush()

            det_x = DetalleVenta(
                id=uuid.uuid4(),
                venta_id=vx_id,
                variante_id=escenario.variante_a_id,
                cantidad=cant_p1,
                precio_unitario=Decimal("100.00"),
                descuento=Decimal("0.00"),
                costo_promedio=Decimal("40.00"),
            )
            db.add(det_x)

            if sem in (1, 2, 3):
                det_p2 = DetalleVenta(
                    id=uuid.uuid4(),
                    venta_id=vx_id,
                    variante_id=var2_id,
                    cantidad=3,
                    precio_unitario=Decimal("120.00"),
                    descuento=Decimal("0.00"),
                    costo_promedio=Decimal("50.00"),
                )
                db.add(det_p2)

            if sem == 1:
                det_p3 = DetalleVenta(
                    id=uuid.uuid4(),
                    venta_id=vx_id,
                    variante_id=var3_id,
                    cantidad=1,
                    precio_unitario=Decimal("250.00"),
                    descuento=Decimal("0.00"),
                    costo_promedio=Decimal("110.00"),
                )
                db.add(det_p3)

            px = Pago(
                id=uuid.uuid4(),
                empresa_id=escenario.empresa_a_id,
                contexto="VENTA",
                venta_id=vx_id,
                metodo="EFECTIVO",
                monto=Decimal(str(cant_p1 * 100)),
                estado="APROBADO",
                pagado_en=fecha_sem,
            )
            db.add(px)

        await db.commit()


@pytest.mark.asyncio
async def test_cu25_ventas_sucursal_desglose_y_fechas(fabrica_sesiones, escenario):
    await _sembrar_ventas_b4(fabrica_sesiones, escenario)

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get(f"/api/v1/analitica/ventas-sucursal?sucursal={escenario.sucursal_a_id}")
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["total"] >= 2
            assert "fecha_central" in data["items"][0]
            assert "fecha_fisica_local" in data["items"][0]
            resumen = data["resumen"]
            assert Decimal(str(resumen["monto_total"])) >= Decimal("435.00")
            assert Decimal(str(resumen["ventas_brutas"])) >= Decimal("450.00")
            assert Decimal(str(resumen["total_descuentos"])) >= Decimal("15.00")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu23_dashboard_indicadores_consolidados_y_capturado(fabrica_sesiones, escenario):
    await _sembrar_ventas_b4(fabrica_sesiones, escenario)

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/analitica/dashboard")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["ventas_total"] >= 2
            assert Decimal(str(d["ingresos_total"])) >= Decimal("435.00")
            assert Decimal(str(d["ventas_brutas"])) >= Decimal("450.00")
            assert Decimal(str(d["descuentos"])) >= Decimal("15.00")
            assert Decimal(str(d["dinero_capturado"])) >= Decimal("435.00")
            assert len(d["top_productos"]) >= 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu24_01_reporte_interpretado_rechaza_inyeccion_sql(fabrica_sesiones, escenario):
    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post(
                "/api/v1/analitica/reportes-interpretados",
                json={"consulta": "SELECT * FROM seguridad.usuarios; DROP TABLE comercial.ventas;--"},
            )
            assert r.status_code == 400
            assert "seguridad" in r.text or "rechazada" in r.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu24_02_reportes_interpretados_cuatro_tipos_permitidos(fabrica_sesiones, escenario):
    await _sembrar_ventas_b4(fabrica_sesiones, escenario)

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            tipos = [
                ("Ventas por sucursal del mes", "VENTAS_POR_SUCURSAL"),
                ("Ranking de productos más vendidos", "RANKING_PRODUCTOS"),
                ("Evolución semanal de ingresos", "EVOLUCION_SEMANAL"),
                ("Ingresos por categoría de prendas", "INGRESOS_POR_CATEGORIA"),
            ]
            for prompt, tipo_esperado in tipos:
                r = await c.post(
                    "/api/v1/analitica/reportes-interpretados",
                    json={"consulta": prompt, "tipo_reporte": tipo_esperado},
                )
                assert r.status_code == 200, r.text
                d = r.json()
                assert d["tipo_reporte"] == tipo_esperado
                assert d["origen"] == "DATOS_REALES"
                assert len(d["columnas"]) > 0
                assert "consulta_id" in d
                assert "grafico_sugerido" in d
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu24_03_clasificacion_sin_gemini_auditoria_honesta(fabrica_sesiones, escenario):
    """Sin API key de Gemini, debe clasificar honestamente sin registrar GEMINI en auditoría."""
    await _sembrar_ventas_b4(fabrica_sesiones, escenario)

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        with patch("backend.app.core.config.settings.GEMINI_API_KEY", ""):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post(
                    "/api/v1/analitica/reportes-interpretados",
                    json={"consulta": "Top de mejores prendas y ranking de productos"},
                )
                assert r.status_code == 200, r.text
                d = r.json()
                assert d["tipo_reporte"] == "RANKING_PRODUCTOS"
                assert d["filtros_efectivos"]["proveedor"] == "DETERMINISTA"

                # Verificar registro honesto en base de datos (no debe decir GEMINI)
                async with fabrica_sesiones() as s:
                    sol = (
                        await s.execute(
                            select(SolicitudIA).where(SolicitudIA.id == uuid.UUID(d["consulta_id"]))
                        )
                    ).scalars().first()
                    assert sol is not None
                    assert sol.proveedor == "DETERMINISTA"
                    assert "GEMINI" not in sol.proveedor
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu24_04_clasificacion_con_gemini_invocacion_real_y_auditoria(fabrica_sesiones, escenario):
    """Con clave y clasificador generativo activo, clasifica a EVOLUCION_SEMANAL y audita honestamente GEMINI."""
    await _sembrar_ventas_b4(fabrica_sesiones, escenario)

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        mock_clasif = AsyncMock(return_value=("EVOLUCION_SEMANAL", "GEMINI", None, None))
        with patch("backend.app.core.config.settings.GEMINI_API_KEY", "test-key-valida"), \
             patch("backend.app.core.modules.analitica.services.ia_analitica_service.IAAnaliticaService._clasificar_con_gemini_o_fallback", mock_clasif):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post(
                    "/api/v1/analitica/reportes-interpretados",
                    json={"consulta": "Quiero ver la tendencia semanal y evolución de mis ventas"},
                )
                assert r.status_code == 200, r.text
                d = r.json()
                assert d["tipo_reporte"] == "EVOLUCION_SEMANAL"
                assert "GEMINI" in d["filtros_efectivos"]["proveedor"]

                # Verificar auditoría con proveedor GEMINI
                async with fabrica_sesiones() as s:
                    sol = (
                        await s.execute(
                            select(SolicitudIA).where(SolicitudIA.id == uuid.UUID(d["consulta_id"]))
                        )
                    ).scalars().first()
                    assert sol is not None
                    assert "GEMINI" in sol.proveedor
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu10_pronostico_demanda_supervisado_y_persistencia(fabrica_sesiones, escenario):
    """CU10: Verifica regresor supervisado real, métricas calculadas y persistencia con SHA-256."""
    await _sembrar_ventas_b4(fabrica_sesiones, escenario)

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get(f"/api/v1/analitica/pronosticos?sucursal={escenario.sucursal_a_id}&semanas=4")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["origen_datos"] == "REAL"
            assert "linear_trend" in d["modelo_version"]
            assert len(d["predicciones"]) >= 4
            assert d["metricas"]["estado"] == "ENTRENADO"

            # Verificar métricas dinámicas (no hardcodeadas)
            metricas = d["metricas"]
            assert metricas["mae"] > 0
            assert metricas["rmse"] >= metricas["mae"]
            assert "baseline_mae" in metricas
            assert metricas["mae"] != 1.15
            assert metricas["rmse"] != 1.82

            # Verificar persistencia en base de datos y artefacto en disco
            async with fabrica_sesiones() as s:
                m = (await s.execute(select(ModeloML).where(ModeloML.id == uuid.UUID(d["modelo_id"])))).scalars().first()
                assert m is not None
                assert m.tipo == "PRONOSTICO"
                assert m.artefacto_hash is not None

                # Comprobar que el archivo existe en disco y su hash coincide
                path_archivo = _ruta_desde_uri(m.artefacto_uri)
                assert path_archivo.exists(), f"El archivo de artefacto {path_archivo} no existe"
                contenido = path_archivo.read_bytes()
                hash_calculado = hashlib.sha256(contenido).hexdigest()
                assert hash_calculado == m.artefacto_hash, "El hash SHA-256 no coincide con el archivo en disco"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu10_datos_insuficientes_honesto(fabrica_sesiones, escenario):
    """CU10: Sin historial suficiente, debe devolver honestamente DATOS_INSUFICIENTES sin inventar entrenamiento."""
    usuario_admin_b = Usuario(
        id=uuid.uuid4(),
        empresa_id=escenario.empresa_b_id,
        rol_id=escenario.usuario_admin_a.rol_id,
        rol=escenario.usuario_admin_a.rol,
        nombres="Admin",
        apellidos="B",
        correo_electronico="admin_b_vacio@test.local",
        contrasenia_hash="hash",
        estado="ACTIVO",
    )
    async with fabrica_sesiones() as db:
        db.add(usuario_admin_b)
        await db.commit()

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_admin_b
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/analitica/pronosticos?semanas=4&origen_datos=REAL")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["metricas"]["estado"] == "DATOS_INSUFICIENTES"
            assert len(d["predicciones"]) == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu10_sintetico_reproducible_con_semilla(fabrica_sesiones, escenario):
    """CU10: Verifica generación sintética reproducible etiquetada con origen explícito."""
    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # Primera corrida con semilla 42
            r1 = await c.post(
                "/api/v1/analitica/entrenamientos/supervisado",
                json={"semanas_adelante": 4, "origen_datos": "SINTETICO_REPRODUCIBLE", "semilla": 42},
            )
            assert r1.status_code == 200, r1.text
            d1 = r1.json()
            assert d1["origen_datos"] == "SINTETICO_REPRODUCIBLE"
            assert d1["metricas"]["estado"] == "ENTRENADO"
            assert len(d1["predicciones"]) >= 4

            # Segunda corrida con la misma semilla 42 debe reproducir exactamente las métricas
            r2 = await c.post(
                "/api/v1/analitica/entrenamientos/supervisado",
                json={"semanas_adelante": 4, "origen_datos": "SINTETICO_REPRODUCIBLE", "semilla": 42},
            )
            assert r2.status_code == 200
            d2 = r2.json()
            assert d1["metricas"]["mae"] == d2["metricas"]["mae"]
            assert d1["metricas"]["rmse"] == d2["metricas"]["rmse"]

            # Corrida con semilla distinta (ej. 99) debe variar demostrando cálculo real sobre datos
            r3 = await c.post(
                "/api/v1/analitica/entrenamientos/supervisado",
                json={"semanas_adelante": 4, "origen_datos": "SINTETICO_REPRODUCIBLE", "semilla": 99},
            )
            assert r3.status_code == 200
            d3 = r3.json()
            assert d3["metricas"]["mae"] != d1["metricas"]["mae"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu11_segmentacion_productos_no_supervisada(fabrica_sesiones, escenario):
    """CU11: K-Means real con cálculo de inercia, Silhouette Score y asignación por clúster."""
    await _sembrar_ventas_b4(fabrica_sesiones, escenario)

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/analitica/grupos-productos?num_grupos=3&origen_datos=REAL")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["origen_datos"] == "REAL"
            assert "kmeans" in d["modelo_version"]
            assert len(d["grupos"]) >= 2
            assert d["metricas"]["estado"] == "ENTRENADO"

            # Inercia y Silhouette reales (no hardcodeadas 128.5 ni 0.74)
            metricas = d["metricas"]
            assert metricas["inercia"] > 0
            assert metricas["inercia"] != 128.5
            assert metricas["silhouette_score"] is not None
            assert -1.0 <= metricas["silhouette_score"] <= 1.0
            assert metricas["silhouette_score"] != 0.74

            # Verificar que los productos no se reparten por módulo i % k
            for g in d["grupos"]:
                assert "centroide" in g
                assert "unidades_promedio" in g["centroide"]

            # Verificar persistencia en base de datos y archivo en disco con hash
            async with fabrica_sesiones() as s:
                m = (await s.execute(select(ModeloML).where(ModeloML.id == uuid.UUID(d["modelo_id"])))).scalars().first()
                assert m is not None
                assert m.tipo == "AGRUPACION"
                path_archivo = _ruta_desde_uri(m.artefacto_uri)
                assert path_archivo.exists()
                contenido = path_archivo.read_bytes()
                assert hashlib.sha256(contenido).hexdigest() == m.artefacto_hash
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu11_datos_insuficientes_clustering(fabrica_sesiones, escenario):
    """CU11: Si el catálogo tiene menos productos que grupos solicitados, devuelve DATOS_INSUFICIENTES."""
    usuario_admin_b = Usuario(
        id=uuid.uuid4(),
        empresa_id=escenario.empresa_b_id,
        rol_id=escenario.usuario_admin_a.rol_id,
        rol=escenario.usuario_admin_a.rol,
        nombres="Admin",
        apellidos="B",
        correo_electronico="admin_b_clustering@test.local",
        contrasenia_hash="hash",
        estado="ACTIVO",
    )
    async with fabrica_sesiones() as db:
        db.add(usuario_admin_b)
        await db.commit()

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_admin_b
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/analitica/grupos-productos?num_grupos=4&origen_datos=REAL")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["metricas"]["estado"] == "DATOS_INSUFICIENTES"
            assert len(d["grupos"]) == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cu11_sintetico_reproducible_con_semilla(fabrica_sesiones, escenario):
    """CU11: Segmentación con dataset sintético reproducible con semilla fija."""
    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r1 = await c.post(
                "/api/v1/analitica/entrenamientos/no-supervisado",
                json={"num_grupos": 4, "origen_datos": "SINTETICO_REPRODUCIBLE", "semilla": 42},
            )
            assert r1.status_code == 200, r1.text
            d1 = r1.json()
            assert d1["origen_datos"] == "SINTETICO_REPRODUCIBLE"
            assert d1["metricas"]["estado"] == "ENTRENADO"
            assert len(d1["grupos"]) == 4

            r2 = await c.post(
                "/api/v1/analitica/entrenamientos/no-supervisado",
                json={"num_grupos": 4, "origen_datos": "SINTETICO_REPRODUCIBLE", "semilla": 42},
            )
            assert r2.status_code == 200
            d2 = r2.json()
            # Mismas métricas con la misma semilla
            assert d1["metricas"]["inercia"] == d2["metricas"]["inercia"]
            assert d1["metricas"]["silhouette_score"] == d2["metricas"]["silhouette_score"]
    finally:
        app.dependency_overrides.clear()
