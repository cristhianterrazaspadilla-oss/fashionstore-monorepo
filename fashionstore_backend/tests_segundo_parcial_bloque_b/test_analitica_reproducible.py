"""Pruebas de reproducibilidad analítica y consistencia — E2 / C4 (CU10, CU11, CU23, CU24, CU25).

Verifica:
1) Recomputabilidad determinista de métricas ML (MAE, RMSE, R2, Silhouette, Baseline).
2) Comportamiento honesto ante datos insuficientes (estado DATOS_INSUFICIENTES sin error 500).
3) Consistencia estricta de neto comercial = ventas_brutas - descuentos - devoluciones.
4) Fallback honesto de IA cuando GEMINI_API_KEY está ausente o falla la llamada externa.
5) Adaptación al huso horario Bolivia (America/La_Paz, UTC-4) en reportes y dashboard.
"""
import hashlib
import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

URL_PRUEBAS = os.getenv("FASHIONSTORE_TEST_DATABASE_URL", "")
if not URL_PRUEBAS:
    pytest.skip("FASHIONSTORE_TEST_DATABASE_URL no configurada", allow_module_level=True)

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.main import app
from backend.app.core.reloj import a_hora_bolivia, entrada_local_a_utc, ZONA_NEGOCIO
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.catalogo.models import Producto, VarianteProducto, Color, Talla
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Venta, Pago
from backend.app.core.modules.posventa.services.devolucion_service import Devolucion, DetalleDevolucion
from backend.app.core.modules.analitica.models import ModeloML, SolicitudIA
from backend.app.core.modules.analitica.services.ml_service import (
    entrenar_regresor_supervisado_temporal,
    entrenar_kmeans_clustering,
    generar_dataset_sintetico_ventas,
    generar_dataset_sintetico_clustering,
)


# ============================================================================
# 1. Recomputabilidad de métricas ML (MAE, RMSE, R2, Silhouette, Baseline)
# ============================================================================

def test_ml_pronostico_recomputabilidad_metricas():
    """Verifica que MAE, RMSE, R2 y Baseline MAE se recomputan matemáticamente de forma exacta."""
    valores = [10.0, 14.0, 18.0, 22.0, 26.0, 30.0]
    metricas, ests, confs, params = entrenar_regresor_supervisado_temporal(
        valores, semanas_adelante=4, semilla=42
    )

    assert metricas["estado"] == "ENTRENADO"
    T = len(valores)
    val_size = 2
    train_size = T - val_size
    t_train = np.arange(train_size, dtype=float)
    y_train = np.array(valores[:train_size], dtype=float)
    t_val = np.arange(train_size, T, dtype=float)
    y_val = np.array(valores[train_size:], dtype=float)

    # 1. Recomputar baseline
    k_baseline = min(2, len(y_train))
    baseline_pred = float(np.mean(y_train[-k_baseline:]))
    manual_baseline_mae = float(np.mean(np.abs(y_val - baseline_pred)))
    assert math.isclose(metricas["baseline_mae"], round(manual_baseline_mae, 4), abs_tol=1e-4)

    # 2. Recomputar OLS y = m*t + b
    coefs = np.polyfit(t_train, y_train, 1)
    m, b = float(coefs[0]), float(coefs[1])
    y_val_pred = m * t_val + b

    # 3. Recomputar MAE y RMSE
    manual_mae = float(np.mean(np.abs(y_val - y_val_pred)))
    manual_rmse = float(np.sqrt(np.mean((y_val - y_val_pred) ** 2)))
    assert math.isclose(metricas["mae"], round(manual_mae, 4), abs_tol=1e-4)
    assert math.isclose(metricas["rmse"], round(manual_rmse, 4), abs_tol=1e-4)

    # 4. Recomputar R²
    ss_tot = float(np.sum((y_val - np.mean(y_val)) ** 2))
    ss_res = float(np.sum((y_val - y_val_pred) ** 2))
    manual_r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 1e-6 else 1.0
    manual_r2 = max(-1.0, min(1.0, manual_r2))
    assert math.isclose(metricas["r2"], round(manual_r2, 4), abs_tol=1e-4)


def test_ml_clustering_recomputabilidad_inercia_y_silhouette():
    """Verifica que la inercia y el Silhouette Score de K-Means sean reales y recomputables."""
    datos = generar_dataset_sintetico_clustering(semilla=42, num_productos=12)
    metricas, labels, centroides_norm, centroides_raw, X, pipeline = entrenar_kmeans_clustering(
        datos, k=3, semilla=42
    )

    assert metricas["estado"] == "ENTRENADO"
    assert metricas["num_clusters"] == 3
    assert -1.0 <= metricas["silhouette_score"] <= 1.0
    assert metricas["inercia"] > 0

    # Recomputar inercia sobre matriz estandarizada
    N = len(datos)
    mu = np.mean(X, axis=0)
    sigma = np.std(X, axis=0)
    sigma_segura = np.where(sigma == 0.0, 1.0, sigma)
    X_scaled = (X - mu) / sigma_segura

    inercia_manual = sum(np.sum((X_scaled[i] - centroides_norm[labels[i]]) ** 2) for i in range(N))
    assert math.isclose(metricas["inercia"], round(float(inercia_manual), 4), abs_tol=1e-4)

    # Recomputar Silhouette Score de Rousseeuw
    s_vals = []
    for i in range(N):
        c_i = labels[i]
        mismo = (labels == c_i)
        if np.sum(mismo) > 1:
            a_i = float(np.mean([np.linalg.norm(X_scaled[i] - X_scaled[j]) for j in range(N) if labels[j] == c_i and j != i]))
        else:
            a_i = 0.0

        b_vals = []
        for c_otro in range(3):
            if c_otro != c_i:
                otro_mask = (labels == c_otro)
                if np.sum(otro_mask) > 0:
                    b_c = float(np.mean([np.linalg.norm(X_scaled[i] - X_scaled[j]) for j in range(N) if labels[j] == c_otro]))
                    b_vals.append(b_c)
        b_i = min(b_vals) if b_vals else 0.0
        denom = max(a_i, b_i)
        s_i = (b_i - a_i) / denom if denom > 1e-8 else 0.0
        s_vals.append(s_i)

    sil_manual = float(np.mean(s_vals))
    assert math.isclose(metricas["silhouette_score"], round(sil_manual, 4), abs_tol=1e-4)


# ============================================================================
# 2. Comportamiento ante datos insuficientes (DATOS_INSUFICIENTES sin error 500)
# ============================================================================

def test_ml_datos_insuficientes_unidad():
    """Unit test: series con < 3 observaciones o catálogo < k devuelven DATOS_INSUFICIENTES."""
    # Pronóstico con 2 observaciones
    met_p, ests, confs, _ = entrenar_regresor_supervisado_temporal([5.0, 8.0])
    assert met_p["estado"] == "DATOS_INSUFICIENTES"
    assert len(ests) == 0

    # Clustering con 2 productos y k=4
    met_c, _, _, _, _, _ = entrenar_kmeans_clustering([{"unidades": 1}, {"unidades": 2}], k=4)
    assert met_c["estado"] == "DATOS_INSUFICIENTES"


@pytest.mark.asyncio
async def test_ml_pronostico_y_clustering_datos_insuficientes_api(fabrica_sesiones, escenario):
    """Integración API: responde HTTP 200 con estado DATOS_INSUFICIENTES (no falla 500)."""
    usuario_vacio = Usuario(
        id=uuid.uuid4(),
        empresa_id=escenario.empresa_b_id,
        rol_id=escenario.usuario_admin_a.rol_id,
        rol=escenario.usuario_admin_a.rol,
        nombres="Admin",
        apellidos="Insuficiente",
        correo_electronico=f"admin_insuf_{uuid.uuid4().hex[:6]}@test.local",
        contrasenia_hash="hash",
        estado="ACTIVO",
    )
    async with fabrica_sesiones() as db:
        db.add(usuario_vacio)
        await db.commit()

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_vacio
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # 1. Pronóstico sobre empresa sin ventas
            r_pron = await c.get("/api/v1/analitica/pronosticos?origen_datos=REAL&semanas=4")
            assert r_pron.status_code == 200
            d_pron = r_pron.json()
            assert d_pron["metricas"]["estado"] == "DATOS_INSUFICIENTES"
            assert len(d_pron["predicciones"]) == 0

            # 2. Segmentación sobre empresa con catálogo insuficiente
            r_seg = await c.get("/api/v1/analitica/grupos-productos?num_grupos=4&origen_datos=REAL")
            assert r_seg.status_code == 200
            d_seg = r_seg.json()
            assert d_seg["metricas"]["estado"] == "DATOS_INSUFICIENTES"
            assert len(d_seg["grupos"]) == 0
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# 3. Consistencia de neto comercial = brutas - descuentos - devoluciones
# ============================================================================

@pytest.mark.asyncio
async def test_consistencia_neto_comercial_con_devolucion(fabrica_sesiones, escenario):
    """Verifica que neto_comercial == ventas_brutas - descuentos - devoluciones en ventas-sucursal y dashboard."""
    ahora = datetime.now(timezone.utc)
    v_id = uuid.uuid4()
    det_id = uuid.uuid4()
    dev_id = uuid.uuid4()

    # Venta: subtotal 600, descuento 60, total 540
    # 3 unidades a 200 c/u, descuento 60 (precio neto unitario = 200 - 20 = 180)
    async with fabrica_sesiones() as db:
        v = Venta(
            id=v_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"V-NETO-{v_id.hex[:6]}",
            sucursal_id=escenario.sucursal_a_id,
            canal="PRESENCIAL",
            estado="PARCIALMENTE_DEVUELTA",
            subtotal=Decimal("600.00"),
            descuento=Decimal("60.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("540.00"),
            creada_en=ahora,
            vendida_local_en=ahora,
            recibida_central_en=ahora,
        )
        db.add(v)
        await db.flush()

        det = DetalleVenta(
            id=det_id,
            venta_id=v_id,
            variante_id=escenario.variante_a_id,
            cantidad=3,
            precio_unitario=Decimal("200.00"),
            descuento=Decimal("60.00"),
            costo_promedio=Decimal("90.00"),
        )
        db.add(det)

        pago = Pago(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            contexto="VENTA",
            venta_id=v_id,
            metodo="EFECTIVO",
            monto=Decimal("540.00"),
            estado="APROBADO",
            pagado_en=ahora,
        )
        db.add(pago)

        # Devolución aceptada de 1 unidad: monto devuelto = 1 * (200 - 60/3) = 180.00
        devolucion = Devolucion(
            id=dev_id,
            empresa_id=escenario.empresa_a_id,
            venta_id=v_id,
            cliente_id=escenario.usuario_admin_a.id,
            sucursal_id=escenario.sucursal_a_id,
            estado="RESUELTA",
            motivo_codigo="CAMBIO_TALLA",
            solicitada_en=ahora,
        )
        db.add(devolucion)
        await db.flush()

        det_dev = DetalleDevolucion(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            devolucion_id=dev_id,
            venta_id=v_id,
            detalle_venta_id=det_id,
            cantidad_solicitada=1,
            cantidad_recibida=1,
            cantidad_aceptada=1,
            cantidad_rechazada=0,
        )
        db.add(det_dev)
        await db.commit()

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            desde_iso = (ahora - timedelta(minutes=5)).isoformat()
            hasta_iso = (ahora + timedelta(minutes=5)).isoformat()

            params_filtro = {
                "sucursal": str(escenario.sucursal_a_id),
                "desde": desde_iso,
                "hasta": hasta_iso,
            }

            # 1. Ventas por sucursal (CU25)
            r_suc = await c.get(
                "/api/v1/analitica/ventas-sucursal",
                params=params_filtro,
            )
            assert r_suc.status_code == 200, r_suc.text
            res = r_suc.json()["resumen"]
            brutas = Decimal(str(res["ventas_brutas"]))
            dto = Decimal(str(res["total_descuentos"]))
            devs = Decimal(str(res["total_devoluciones"]))
            neto = Decimal(str(res["neto_comercial"]))

            assert devs >= Decimal("180.00")
            assert neto == brutas - dto - devs

            # 2. Dashboard (CU23)
            r_dash = await c.get(
                "/api/v1/analitica/dashboard",
                params=params_filtro,
            )
            assert r_dash.status_code == 200, r_dash.text
            d = r_dash.json()
            d_brutas = Decimal(str(d["ventas_brutas"]))
            d_dto = Decimal(str(d["descuentos"]))
            d_devs = Decimal(str(d["devoluciones"]))
            d_neto = Decimal(str(d["neto_comercial"]))

            assert d_devs >= Decimal("180.00")
            assert d_neto == d_brutas - d_dto - d_devs
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# 4. Fallback honesto de IA cuando GEMINI_API_KEY no está o falla la llamada
# ============================================================================

@pytest.mark.asyncio
async def test_ia_fallback_honesto_sin_api_key_y_ante_falla_red(fabrica_sesiones, escenario):
    """Verifica que la IA registre honestamente DETERMINISTA o FALLBACK_DETERMINISTA sin falsedad."""
    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # Caso 1: GEMINI_API_KEY vacía -> DETERMINISTA
            with patch("backend.app.core.config.settings.GEMINI_API_KEY", ""):
                r1 = await c.post(
                    "/api/v1/analitica/reportes-interpretados",
                    json={"consulta": "Distribución e ingresos por categoría de prendas"},
                )
                assert r1.status_code == 200
                d1 = r1.json()
                assert d1["tipo_reporte"] == "INGRESOS_POR_CATEGORIA"
                assert d1["filtros_efectivos"]["proveedor"] == "DETERMINISTA"
                assert "Gemini" not in d1["narrativa"]

                # Verificar auditoría honesta en BD
                async with fabrica_sesiones() as s:
                    sol1 = (
                        await s.execute(
                            select(SolicitudIA).where(SolicitudIA.id == uuid.UUID(d1["consulta_id"]))
                        )
                    ).scalars().first()
                    assert sol1 is not None
                    assert sol1.proveedor == "DETERMINISTA"

            # Caso 2: GEMINI_API_KEY configurada pero falla de conexión externa -> FALLBACK_DETERMINISTA
            class _MockFailingClient:
                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

                async def post(self, *args, **kwargs):
                    raise httpx.ConnectError("Simulated network outage to Generative Language API")

            with patch("backend.app.core.config.settings.GEMINI_API_KEY", "key-valida-test"), \
                 patch("backend.app.core.modules.analitica.services.ia_analitica_service.httpx.AsyncClient", _MockFailingClient):
                r2 = await c.post(
                    "/api/v1/analitica/reportes-interpretados",
                    json={"consulta": "Evolución semanal del volumen de ventas"},
                )
                assert r2.status_code == 200  # Degradación elegante sin 500
                d2 = r2.json()
                assert d2["tipo_reporte"] == "EVOLUCION_SEMANAL"
                assert d2["filtros_efectivos"]["proveedor"] == "FALLBACK_DETERMINISTA"

                async with fabrica_sesiones() as s:
                    sol2 = (
                        await s.execute(
                            select(SolicitudIA).where(SolicitudIA.id == uuid.UUID(d2["consulta_id"]))
                        )
                    ).scalars().first()
                    assert sol2 is not None
                    assert sol2.proveedor == "DETERMINISTA"
                    assert "GEMINI" not in sol2.proveedor
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# 5. Huso horario Bolivia (America/La_Paz, UTC-4) en reportes y dashboard
# ============================================================================

def test_huso_horario_bolivia_politica_temporal():
    """Verifica que entrada_local_a_utc y a_hora_bolivia usen UTC-4 sin depender del SO."""
    # Instante naive (sin timezone) se asume hora civil de Bolivia: 14:00 Bolivia -> 18:00 UTC
    dt_local = datetime(2026, 11, 5, 14, 0, 0)
    dt_utc = entrada_local_a_utc(dt_local)
    assert dt_utc.tzinfo == timezone.utc
    assert dt_utc.hour == 18
    assert dt_utc.day == 5

    # Instante UTC convertido a hora boliviana: 18:00 UTC -> 14:00 Bolivia (-04:00)
    dt_bolivia = a_hora_bolivia(dt_utc)
    assert dt_bolivia.tzinfo == ZONA_NEGOCIO
    assert dt_bolivia.hour == 14
    assert dt_bolivia.utcoffset() == timedelta(hours=-4)


@pytest.mark.asyncio
async def test_huso_horario_bolivia_en_ventas_sucursal_item(fabrica_sesiones, escenario):
    """Verifica que fecha_fisica_local en VentasSucursalItemDTO tenga offset -04:00 (America/La_Paz)."""
    ahora_utc = datetime.now(timezone.utc)
    v_id = uuid.uuid4()

    async with fabrica_sesiones() as db:
        v = Venta(
            id=v_id,
            empresa_id=escenario.empresa_a_id,
            numero=f"V-TZ-{v_id.hex[:6]}",
            sucursal_id=escenario.sucursal_a_id,
            canal="PRESENCIAL",
            estado="PAGADA",
            subtotal=Decimal("100.00"),
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=Decimal("100.00"),
            creada_en=ahora_utc,
            vendida_local_en=ahora_utc,
            recibida_central_en=ahora_utc,
        )
        db.add(v)
        await db.commit()

    async def _db():
        async with fabrica_sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_usuario_actual] = lambda: escenario.usuario_admin_a
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get(
                f"/api/v1/analitica/ventas-sucursal?sucursal={escenario.sucursal_a_id}&limit=5"
            )
            assert r.status_code == 200
            data = r.json()
            assert len(data["items"]) > 0
            item = next(it for it in data["items"] if str(it["id"]) == str(v_id))

            # fecha_fisica_local debe ser hora Bolivia con offset -04:00
            fecha_local_str = str(item["fecha_fisica_local"])
            assert "-04:00" in fecha_local_str

            dt_parsed = datetime.fromisoformat(fecha_local_str)
            assert dt_parsed.utcoffset() == timedelta(hours=-4)
    finally:
        app.dependency_overrides.clear()
