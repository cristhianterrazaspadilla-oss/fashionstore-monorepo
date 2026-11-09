"""Servicio de Modelos de Machine Learning — CU10 (Pronóstico Supervisado) y CU11 (Segmentación No Supervisada).

Implementa regresión supervisada con baseline y validación temporal para pronóstico de demanda,
clustering K-Means con estandarización, inercia y Silhouette Score reales para segmentación,
generación de dataset sintético reproducible con semilla fija, versionado y persistencia
verificable de artefactos en disco con SHA-256 real.
"""
import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.permisos import es_admin
from backend.app.core.ambito_comercial import empresa_comercial, sucursal_autorizada
from backend.app.core.modules.identidad_empresas.services.plan_service import PlanService
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.catalogo.models import Producto, VarianteProducto
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Venta
from backend.app.core.modules.analitica.models import ModeloML
from backend.app.core.modules.analitica.schemas import (
    PrediccionDemandaItemDTO,
    PronosticoDemandaPeticionDTO,
    PronosticoDemandaResultadoDTO,
    GrupoProductoDTO,
    SegmentacionProductosPeticionDTO,
    SegmentacionProductosResultadoDTO,
)


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _obtener_directorio_artefactos() -> Path:
    env_dir = os.environ.get("FASHIONSTORE_ARTEFACTOS_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if os.environ.get("PYTEST_CURRENT_TEST"):
        # En entorno de pruebas automatizadas, usar almacenamiento temporal aislado
        # para evitar generar artefactos residuales en el repositorio git.
        p = Path(tempfile.gettempdir()) / "fashionstore_test_artefactos"
        p.mkdir(parents=True, exist_ok=True)
        return p
    base = Path(__file__).resolve().parents[5] / "artefactos"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _guardar_artefacto_disco(
    empresa_id: uuid.UUID, subdirectorio: str, nombre_archivo: str, contenido: dict
) -> Tuple[str, str]:
    """Persiste artefacto JSON en disco y retorna (uri, sha256_real)."""
    dir_destino = _obtener_directorio_artefactos() / subdirectorio / str(empresa_id)
    dir_destino.mkdir(parents=True, exist_ok=True)
    archivo_path = dir_destino / nombre_archivo

    contenido_bytes = json.dumps(contenido, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    archivo_path.write_bytes(contenido_bytes)

    hash_sha256 = hashlib.sha256(contenido_bytes).hexdigest()
    uri = f"file:///{archivo_path.as_posix()}"
    return uri, hash_sha256


# ---------------- Dataset Sintético Reproducible (Semilla fija) ----------------
def generar_dataset_sintetico_ventas(
    semilla: int = 42,
    num_semanas: int = 12,
    productos_info: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Genera serie temporal sintética semanal reproducible por producto."""
    rng = np.random.default_rng(semilla)
    if not productos_info:
        productos_info = [
            {"id": uuid.UUID("11111111-1111-1111-1111-111111111111"), "nombre": "Camisa Oxford Clásica"},
            {"id": uuid.UUID("22222222-2222-2222-2222-222222222222"), "nombre": "Pantalón Chino Slim"},
            {"id": uuid.UUID("33333333-3333-3333-3333-333333333333"), "nombre": "Chaqueta Denim Urbana"},
            {"id": uuid.UUID("44444444-4444-4444-4444-444444444444"), "nombre": "Vestido Floral Verano"},
        ]
    series = []
    for p in productos_info:
        base_uds = float(rng.integers(8, 25))
        tendencia = float(rng.uniform(0.6, 2.2))
        for sem in range(num_semanas):
            estacionalidad = 2.5 * np.sin(2.0 * np.pi * sem / 4.0)
            ruido = float(rng.normal(0, 1.2))
            uds = max(1, int(round(base_uds + tendencia * sem + estacionalidad + ruido)))
            series.append({
                "producto_id": p["id"],
                "producto_nombre": p["nombre"],
                "semana_idx": sem,
                "unidades": uds,
            })
    return {"productos": productos_info, "series": series, "num_semanas": num_semanas, "semilla": semilla}


def generar_dataset_sintetico_clustering(
    semilla: int = 42,
    num_productos: int = 12,
) -> List[Dict[str, Any]]:
    """Genera perfiles de producto sintéticos reproducibles con características multivariadas."""
    rng = np.random.default_rng(semilla)
    nombres_base = [
        "Blusa Seda Premium", "Camisa Lino Verano", "Pantalón Formal Lana", "Jean Regular Fit",
        "Chaqueta Cuero Moto", "Falda Plisada Midi", "Polera Algodón Básica", "Short Deportivo",
        "Abrigo Invierno Trench", "Vestido Noche Elegante", "Cardigan Punto Fino", "Bufanda Alpaca"
    ]
    resultado = []
    for i in range(num_productos):
        nombre = nombres_base[i % len(nombres_base)]
        # Perfiles con diferentes rotaciones
        if i % 4 == 0:
            # Estrellas de alta rotación
            frecuencia = int(rng.integers(40, 80))
            unidades = int(rng.integers(120, 250))
            ingresos = float(round(unidades * float(rng.uniform(180.0, 320.0)), 2))
            rotacion = float(round(float(rng.uniform(3.5, 6.0)), 2))
        elif i % 4 == 1:
            # Productos regulares
            frecuencia = int(rng.integers(20, 39))
            unidades = int(rng.integers(50, 119))
            ingresos = float(round(unidades * float(rng.uniform(120.0, 200.0)), 2))
            rotacion = float(round(float(rng.uniform(1.8, 3.4)), 2))
        elif i % 4 == 2:
            # Baja rotación / oportunidad (margen alto)
            frecuencia = int(rng.integers(5, 19))
            unidades = int(rng.integers(10, 49))
            ingresos = float(round(unidades * float(rng.uniform(250.0, 500.0)), 2))
            rotacion = float(round(float(rng.uniform(0.8, 1.7)), 2))
        else:
            # Novedades o rezagados
            frecuencia = int(rng.integers(1, 8))
            unidades = int(rng.integers(1, 15))
            ingresos = float(round(unidades * float(rng.uniform(80.0, 150.0)), 2))
            rotacion = float(round(float(rng.uniform(0.1, 0.7)), 2))

        resultado.append({
            "id": uuid.UUID(f"{i+1:08x}-0000-0000-0000-000000000000"),
            "nombre": f"{nombre} {i+1}",
            "frecuencia": frecuencia,
            "unidades": unidades,
            "ingresos": ingresos,
            "rotacion": rotacion,
        })
    return resultado


# ---------------- Algoritmos ML Reales ----------------
def entrenar_regresor_supervisado_temporal(
    valores_historicos: List[float],
    semanas_adelante: int = 4,
    semilla: int = 42,
) -> Tuple[Dict[str, Any], List[int], List[float], Dict[str, Any]]:
    """Entrena regresor de tendencia lineal con validación temporal y baseline."""
    T = len(valores_historicos)
    if T < 3:
        return (
            {"estado": "DATOS_INSUFICIENTES", "razon": f"Observaciones temporales ({T}) insuficientes (mínimo 3)"},
            [],
            [],
            {},
        )

    val_size = 1 if T < 6 else 2
    train_size = T - val_size

    t_train = np.arange(train_size, dtype=float)
    y_train = np.array(valores_historicos[:train_size], dtype=float)

    t_val = np.arange(train_size, T, dtype=float)
    y_val = np.array(valores_historicos[train_size:], dtype=float)

    # 1. Baseline: media móvil de los últimos periodos de entrenamiento
    k_baseline = min(2, len(y_train))
    baseline_pred = float(np.mean(y_train[-k_baseline:]))
    mae_baseline = float(np.mean(np.abs(y_val - baseline_pred)))

    # 2. Regresor de tendencia supervisado: ajuste mínimos cuadrados OLS y = m*t + b
    if np.all(y_train == y_train[0]) or len(np.unique(t_train)) < 2:
        m, b = 0.0, float(y_train[0])
    else:
        coefs = np.polyfit(t_train, y_train, 1)
        m, b = float(coefs[0]), float(coefs[1])

    # 3. Evaluación sobre conjunto de validación temporal
    y_val_pred = m * t_val + b
    mae = float(np.mean(np.abs(y_val - y_val_pred)))
    rmse = float(np.sqrt(np.mean((y_val - y_val_pred) ** 2)))

    ss_tot = float(np.sum((y_val - np.mean(y_val)) ** 2))
    ss_res = float(np.sum((y_val - y_val_pred) ** 2))
    if ss_tot > 1e-6:
        r2 = float(1.0 - (ss_res / ss_tot))
    else:
        r2 = 1.0 if ss_res < 1e-6 else 0.0
    r2 = max(-1.0, min(1.0, r2))

    mejora_baseline_pct = float(round(((mae_baseline - mae) / (mae_baseline + 1e-5)) * 100.0, 2))

    metricas = {
        "estado": "ENTRENADO",
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "r2": round(r2, 4),
        "baseline_mae": round(mae_baseline, 4),
        "mejora_vs_baseline_pct": mejora_baseline_pct,
        "train_size": train_size,
        "val_size": val_size,
        "semilla": semilla,
    }

    # 4. Proyección supervisada hacia semanas futuras
    estimaciones = []
    confianzas = []
    prom_entrenamiento = max(1.0, float(np.mean(y_train)))
    err_relativo = mae / prom_entrenamiento

    for sem in range(1, semanas_adelante + 1):
        t_fut = T + sem - 1
        y_fut = max(0, int(round(m * t_fut + b)))
        estimaciones.append(y_fut)
        conf = max(0.25, min(0.98, round(1.0 - (err_relativo * 0.4) - (0.02 * sem), 4)))
        confianzas.append(conf)

    parametros_modelo = {
        "tipo_algoritmo": "LINEAR_TREND_SUPERVISED",
        "pendiente": round(m, 6),
        "intercepto": round(b, 6),
        "baseline_valor": round(baseline_pred, 4),
        "metricas": metricas,
    }

    return metricas, estimaciones, confianzas, parametros_modelo


def entrenar_kmeans_clustering(
    productos_data: List[Dict[str, Any]],
    k: int,
    semilla: int = 42,
) -> Tuple[Dict[str, Any], np.ndarray, np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    """Entrena K-Means real con estandarización, cálculo de inercia y Silhouette Score."""
    N = len(productos_data)
    if N < k or N < 2:
        return (
            {"estado": "DATOS_INSUFICIENTES", "razon": f"Catálogo ({N}) menor que grupos solicitados ({k})"},
            np.array([]),
            np.array([]),
            np.array([]),
            np.array([]),
            {},
        )

    # 1. Matriz de características X: [frecuencia, unidades, ingresos, rotacion]
    X = np.array([
        [
            float(p.get("frecuencia", 0)),
            float(p.get("unidades", 0)),
            float(p.get("ingresos", 0.0)),
            float(p.get("rotacion", 0.0)),
        ]
        for p in productos_data
    ], dtype=float)

    # 2. Estandarización Z-score
    mu = np.mean(X, axis=0)
    sigma = np.std(X, axis=0)
    sigma_segura = np.where(sigma == 0.0, 1.0, sigma)
    X_scaled = (X - mu) / sigma_segura

    # 3. Inicialización determinista reproducible con semilla
    rng = np.random.default_rng(semilla)
    indices_iniciales = rng.choice(N, size=k, replace=False)
    centroides = X_scaled[indices_iniciales].copy()

    labels = np.zeros(N, dtype=int)
    max_iter = 100

    for _ in range(max_iter):
        # Distancia euclídea cuadrada a centroides
        distancias = np.zeros((N, k))
        for j in range(k):
            distancias[:, j] = np.sum((X_scaled - centroides[j]) ** 2, axis=1)

        nuevos_labels = np.argmin(distancias, axis=1)
        if np.array_equal(labels, nuevos_labels) and _ > 0:
            break
        labels = nuevos_labels

        # Recomputar centroides
        for j in range(k):
            en_cluster = (labels == j)
            if np.sum(en_cluster) > 0:
                centroides[j] = np.mean(X_scaled[en_cluster], axis=0)
            else:
                # Reasignar punto más lejano al centroide vacío
                mas_lejano = int(np.argmax(np.min(distancias, axis=1)))
                centroides[j] = X_scaled[mas_lejano]
                labels[mas_lejano] = j

    # 4. Inercia real (suma de distancias cuadradas al centroide)
    inercia = float(sum(np.sum((X_scaled[i] - centroides[labels[i]]) ** 2) for i in range(N)))

    # 5. Silhouette Score real cuando 2 <= k < N
    silhouette_score = None
    if 2 <= k < N and len(np.unique(labels)) > 1:
        s_vals = []
        for i in range(N):
            c_i = labels[i]
            mismo_c = (labels == c_i)
            if np.sum(mismo_c) > 1:
                a_i = float(np.mean([np.linalg.norm(X_scaled[i] - X_scaled[j]) for j in range(N) if labels[j] == c_i and j != i]))
            else:
                a_i = 0.0

            b_vals = []
            for c_otro in range(k):
                if c_otro != c_i:
                    otro_mask = (labels == c_otro)
                    if np.sum(otro_mask) > 0:
                        b_c = float(np.mean([np.linalg.norm(X_scaled[i] - X_scaled[j]) for j in range(N) if labels[j] == c_otro]))
                        b_vals.append(b_c)
            b_i = min(b_vals) if b_vals else 0.0
            denom = max(a_i, b_i)
            s_i = (b_i - a_i) / denom if denom > 1e-8 else 0.0
            s_vals.append(s_i)
        silhouette_score = float(np.mean(s_vals))

    metricas = {
        "estado": "ENTRENADO",
        "num_clusters": k,
        "inercia": round(inercia, 4),
        "silhouette_score": round(silhouette_score, 4) if silhouette_score is not None else None,
        "num_productos": N,
        "semilla": semilla,
    }

    # Desestandarizar centroides para interpretación
    centroides_crudos = centroides * sigma_segura + mu

    pipeline_info = {
        "tipo_algoritmo": "KMEANS_STANDARDIZED",
        "scaler_mu": [round(float(v), 4) for v in mu],
        "scaler_sigma": [round(float(v), 4) for v in sigma_segura],
        "inercia": round(inercia, 4),
        "silhouette_score": round(silhouette_score, 4) if silhouette_score is not None else None,
        "semilla": semilla,
    }

    return metricas, labels, centroides, centroides_crudos, X, pipeline_info


class MLService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def pronosticoDemanda(
        self, usuario: Usuario, datos: PronosticoDemandaPeticionDTO
    ) -> PronosticoDemandaResultadoDTO:
        empresa_id = empresa_comercial(usuario)
        if not es_admin(usuario):
            raise HTTPException(status_code=403, detail="Solo Administrador empresarial autorizado")
        await PlanService(self.db).exigir_capacidad_analitica(empresa_id, "modelos_ml")
        if datos.sucursal_id:
            await sucursal_autorizada(self.db, usuario, datos.sucursal_id)
        if datos.producto_id:
            producto = (await self.db.execute(select(Producto.id).where(
                Producto.id == datos.producto_id, Producto.empresa_id == empresa_id
            ))).scalar()
            if producto is None:
                raise HTTPException(status_code=404, detail="Producto no encontrado")

        semilla = datos.semilla or 42
        origen_solicitado = (datos.origen_datos or "AUTO").upper()

        # 1. Obtener catálogo base de productos de la empresa
        q_prods = select(Producto.id, Producto.nombre).where(Producto.empresa_id == empresa_id)
        if datos.producto_id:
            q_prods = q_prods.where(Producto.id == datos.producto_id)
        prods_bd = (await self.db.execute(q_prods)).all()

        # 2. Consultar ventas reales ordenadas temporalmente
        q_ventas = (
            select(
                Producto.id,
                Producto.nombre,
                Venta.creada_en,
                DetalleVenta.cantidad,
            )
            .join(VarianteProducto, VarianteProducto.producto_id == Producto.id)
            .join(DetalleVenta, DetalleVenta.variante_id == VarianteProducto.id)
            .join(Venta, Venta.id == DetalleVenta.venta_id)
            .where(Venta.empresa_id == empresa_id, Venta.estado == "PAGADA")
        )
        if datos.sucursal_id:
            q_ventas = q_ventas.where(Venta.sucursal_id == datos.sucursal_id)
        if datos.producto_id:
            q_ventas = q_ventas.where(Producto.id == datos.producto_id)

        q_ventas = q_ventas.order_by(Venta.creada_en.asc())
        filas_ventas = (await self.db.execute(q_ventas)).all()

        # Determinar si hay datos suficientes reales
        agregado_semanal: Dict[Tuple[uuid.UUID, str], Dict[int, int]] = {}
        semanas_globales: set = set()

        if filas_ventas:
            fecha_min = min(f[2] for f in filas_ventas)
            for prod_id, prod_nom, fecha, cant in filas_ventas:
                dif_semanas = max(0, (fecha - fecha_min).days // 7)
                semanas_globales.add(dif_semanas)
                clave = (prod_id, prod_nom)
                if clave not in agregado_semanal:
                    agregado_semanal[clave] = {}
                agregado_semanal[clave][dif_semanas] = agregado_semanal[clave].get(dif_semanas, 0) + int(cant or 0)

        num_semanas_reales = len(semanas_globales)
        hay_datos_reales_suficientes = num_semanas_reales >= 3

        # Decidir origen efectivo de datos
        if origen_solicitado == "SINTETICO_REPRODUCIBLE":
            origen_efectivo = "SINTETICO_REPRODUCIBLE"
        elif origen_solicitado == "REAL":
            origen_efectivo = "REAL"
        else:  # AUTO
            origen_efectivo = "REAL" if hay_datos_reales_suficientes else "REAL"

        predicciones: List[PrediccionDemandaItemDTO] = []
        parametros_artefacto: Dict[str, Any] = {}
        metricas_finales: Dict[str, Any] = {}

        if origen_efectivo == "SINTETICO_REPRODUCIBLE":
            # Generar dataset sintético reproducible con semilla
            prods_base = [
                {"id": p[0], "nombre": p[1]} for p in prods_bd
            ] if prods_bd else None
            ds_sintetico = generar_dataset_sintetico_ventas(semilla=semilla, num_semanas=12, productos_info=prods_base)

            # Entrenar modelo con serie agregada
            serie_agregada = [0.0] * ds_sintetico["num_semanas"]
            for punto in ds_sintetico["series"]:
                serie_agregada[punto["semana_idx"]] += float(punto["unidades"])

            metricas_finales, ests, confs, params = entrenar_regresor_supervisado_temporal(
                serie_agregada, semanas_adelante=datos.semanas_adelante, semilla=semilla
            )
            parametros_artefacto = params

            # Repartir estimaciones proporcionales por producto
            for prod in ds_sintetico["productos"]:
                for sem_idx, (est, conf) in enumerate(zip(ests, confs), start=1):
                    predicciones.append(
                        PrediccionDemandaItemDTO(
                            sucursal_id=datos.sucursal_id,
                            producto_id=prod["id"],
                            producto_nombre=prod["nombre"],
                            semana=sem_idx,
                            unidades_estimadas=max(1, est // len(ds_sintetico["productos"])),
                            confianza=conf,
                        )
                    )

        else:
            # Caso datos reales
            if not hay_datos_reales_suficientes:
                metricas_finales = {
                    "estado": "DATOS_INSUFICIENTES",
                    "razon": f"Semanas con ventas ({num_semanas_reales}) insuficientes para validación temporal (mínimo 3 requeridas)",
                    "mae": 0.0,
                    "rmse": 0.0,
                    "r2": 0.0,
                }
                parametros_artefacto = {"estado": "DATOS_INSUFICIENTES", "razon": metricas_finales["razon"]}
            else:
                # Entrenar serie temporal agregada
                max_sem = max(semanas_globales)
                serie_agregada = [0.0] * (max_sem + 1)
                for clave, semanas_dict in agregado_semanal.items():
                    for sem_idx, uds in semanas_dict.items():
                        serie_agregada[sem_idx] += float(uds)

                metricas_finales, ests, confs, params = entrenar_regresor_supervisado_temporal(
                    serie_agregada, semanas_adelante=datos.semanas_adelante, semilla=semilla
                )
                parametros_artefacto = params

                # Repartir proporcionalmente por producto
                total_prods = len(agregado_semanal) or 1
                for (prod_id, prod_nom), semanas_dict in agregado_semanal.items():
                    peso_prod = sum(semanas_dict.values()) / max(1, sum(serie_agregada))
                    for sem_idx, (est, conf) in enumerate(zip(ests, confs), start=1):
                        pred_prod = max(1, int(round(est * peso_prod)))
                        predicciones.append(
                            PrediccionDemandaItemDTO(
                                sucursal_id=datos.sucursal_id,
                                producto_id=prod_id,
                                producto_nombre=prod_nom,
                                semana=sem_idx,
                                unidades_estimadas=pred_prod,
                                confianza=conf,
                            )
                        )

        # Registrar artefactos reales en disco con hash SHA-256
        modelo_id = uuid.uuid4()
        max_v = await self.db.scalar(
            select(func.max(ModeloML.version)).where(
                ModeloML.empresa_id == empresa_id,
                ModeloML.tipo == "PRONOSTICO",
            )
        ) or 0
        version_num = int(max_v) + 1

        artefacto_uri, artefacto_hash = _guardar_artefacto_disco(
            empresa_id=empresa_id,
            subdirectorio="modelos",
            nombre_archivo=f"pronostico_{modelo_id}.json",
            contenido={
                "modelo_id": str(modelo_id),
                "tipo": "PRONOSTICO_DEMANDA",
                "version": version_num,
                "origen_datos": origen_efectivo,
                "parametros": parametros_artefacto,
                "creado_en": _ahora_utc().isoformat(),
            },
        )

        resultado_uri, resultado_hash = _guardar_artefacto_disco(
            empresa_id=empresa_id,
            subdirectorio="resultados",
            nombre_archivo=f"pronostico_resultado_{modelo_id}.json",
            contenido={
                "modelo_id": str(modelo_id),
                "metricas": metricas_finales,
                "predicciones": [p.model_dump() for p in predicciones],
                "generado_en": _ahora_utc().isoformat(),
            },
        )

        dataset_ver = f"ds_{'sintetico' if 'SINTETICO' in origen_efectivo else 'real'}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        origen_datos_bd = "SINTETICO" if "SINTETICO" in origen_efectivo else "REAL"
        modelo = ModeloML(
            id=modelo_id,
            empresa_id=empresa_id,
            tipo="PRONOSTICO",
            version=version_num,
            origen_datos=origen_datos_bd,
            semilla=semilla,
            dataset_version=dataset_ver,
            dataset_hash=hashlib.sha256(f"{empresa_id}:{origen_efectivo}:{len(filas_ventas)}".encode()).hexdigest()[:16],
            metricas=metricas_finales,
            artefacto_uri=artefacto_uri,
            artefacto_hash=artefacto_hash,
            resultado_uri=resultado_uri,
            resultado_hash=resultado_hash,
            esquema_resultado_version=1,
        )
        self.db.add(modelo)
        await self.db.commit()

        return PronosticoDemandaResultadoDTO(
            modelo_id=modelo_id,
            modelo_version=f"linear_trend_v{version_num}",
            dataset_version=dataset_ver,
            metricas=metricas_finales,
            origen_datos=origen_efectivo,
            entrenado_en=_ahora_utc(),
            predicciones=predicciones,
        )

    async def segmentacionProductos(
        self, usuario: Usuario, datos: SegmentacionProductosPeticionDTO
    ) -> SegmentacionProductosResultadoDTO:
        empresa_id = empresa_comercial(usuario)
        if not es_admin(usuario):
            raise HTTPException(status_code=403, detail="Solo Administrador empresarial autorizado")
        await PlanService(self.db).exigir_capacidad_analitica(empresa_id, "modelos_ml")

        semilla = datos.semilla or 42
        origen_solicitado = (datos.origen_datos or "AUTO").upper()

        # 1. Obtener catálogo y métricas de ventas reales
        q = (
            select(
                Producto.id,
                Producto.nombre,
                func.coalesce(func.count(func.distinct(Venta.id)), 0).label("frecuencia"),
                func.coalesce(func.sum(DetalleVenta.cantidad), 0).label("unidades_vendidas"),
                func.coalesce(func.sum(DetalleVenta.precio_unitario * DetalleVenta.cantidad), 0).label("ingresos"),
                func.coalesce(func.count(func.distinct(VarianteProducto.id)), 1).label("variantes_count"),
            )
            .join(VarianteProducto, VarianteProducto.producto_id == Producto.id)
            .outerjoin(DetalleVenta, (DetalleVenta.variante_id == VarianteProducto.id) & (
                DetalleVenta.venta_id.in_(select(Venta.id).where(Venta.empresa_id == empresa_id))
            ))
            .outerjoin(Venta, Venta.id == DetalleVenta.venta_id)
            .where(Producto.empresa_id == empresa_id, VarianteProducto.empresa_id == empresa_id)
            .group_by(Producto.id, Producto.nombre)
        )
        filas = (await self.db.execute(q)).all()

        hay_datos_reales = len(filas) >= datos.num_grupos

        if origen_solicitado == "SINTETICO_REPRODUCIBLE":
            origen_efectivo = "SINTETICO_REPRODUCIBLE"
        elif origen_solicitado == "REAL":
            origen_efectivo = "REAL"
        else:  # AUTO
            origen_efectivo = "REAL" if hay_datos_reales else "REAL"

        grupos: List[GrupoProductoDTO] = []
        parametros_pipeline: Dict[str, Any] = {}
        metricas: Dict[str, Any] = {}

        if origen_efectivo == "SINTETICO_REPRODUCIBLE":
            productos_features = generar_dataset_sintetico_clustering(semilla=semilla, num_productos=max(12, datos.num_grupos * 3))
            k = min(datos.num_grupos, len(productos_features))
            metricas, labels, centroides_norm, centroides_raw, X, pipeline_info = entrenar_kmeans_clustering(
                productos_features, k=k, semilla=semilla
            )
            parametros_pipeline = pipeline_info

            # Armar grupos por orden de ingresos/unidades del centroide
            indices_ordenados = sorted(
                range(k),
                key=lambda j: centroides_raw[j, 1] * centroides_raw[j, 2],
                reverse=True,
            )
            nombres_perfil = [
                ("Estrellas de alta rotación", "Alta rotación y alto volumen de ingresos"),
                ("Productos regulares", "Volumen y rotación estables con ventas continuas"),
                ("Baja rotación / oportunidad", "Baja rotación con margen potencial"),
                ("Novedades o rezagados", "Bajo volumen histórico o reciente incorporación"),
            ]
            for rango, cluster_idx in enumerate(indices_ordenados):
                nombre_g, desc_g = nombres_perfil[min(rango, len(nombres_perfil) - 1)]
                prods_cluster = [productos_features[i] for i in range(len(productos_features)) if labels[i] == cluster_idx]
                muestra = [
                    {"id": str(p["id"]), "nombre": p["nombre"], "unidades": int(p["unidades"]), "ingresos": float(p["ingresos"])}
                    for p in prods_cluster[:5]
                ]
                grupos.append(
                    GrupoProductoDTO(
                        grupo_id=rango + 1,
                        nombre_grupo=nombre_g,
                        descripcion=desc_g,
                        cantidad_productos=len(prods_cluster),
                        centroide={
                            "unidades_promedio": round(float(centroides_raw[cluster_idx, 1]), 2),
                            "ingresos_promedio": round(float(centroides_raw[cluster_idx, 2]), 2),
                            "frecuencia_promedio": round(float(centroides_raw[cluster_idx, 0]), 2),
                            "rotacion_promedio": round(float(centroides_raw[cluster_idx, 3]), 2),
                        },
                        productos_muestra=muestra,
                    )
                )

        else:
            # Caso REAL
            if len(filas) < datos.num_grupos or len(filas) < 2:
                metricas = {
                    "estado": "DATOS_INSUFICIENTES",
                    "razon": f"Catálogo insuficiente ({len(filas)} productos) para formar {datos.num_grupos} grupos",
                    "silhouette_score": None,
                    "inercia": 0.0,
                }
                parametros_pipeline = {"estado": "DATOS_INSUFICIENTES", "razon": metricas["razon"]}
            else:
                productos_features = [
                    {
                        "id": r[0],
                        "nombre": r[1],
                        "frecuencia": int(r[2] or 0),
                        "unidades": int(r[3] or 0),
                        "ingresos": float(r[4] or 0.0),
                        "rotacion": float(round(float(r[3] or 0) / max(1, int(r[5] or 1)), 2)),
                    }
                    for r in filas
                ]
                k = min(datos.num_grupos, len(productos_features))
                metricas, labels, centroides_norm, centroides_raw, X, pipeline_info = entrenar_kmeans_clustering(
                    productos_features, k=k, semilla=semilla
                )
                parametros_pipeline = pipeline_info

                indices_ordenados = sorted(
                    range(k),
                    key=lambda j: centroides_raw[j, 1] * centroides_raw[j, 2],
                    reverse=True,
                )
                nombres_perfil = [
                    ("Estrellas de alta rotación", "Alta rotación y alto volumen de ingresos"),
                    ("Productos regulares", "Volumen y rotación estables con ventas continuas"),
                    ("Baja rotación / oportunidad", "Baja rotación con margen potencial"),
                    ("Novedades o rezagados", "Bajo volumen histórico o reciente incorporación"),
                ]
                for rango, cluster_idx in enumerate(indices_ordenados):
                    nombre_g, desc_g = nombres_perfil[min(rango, len(nombres_perfil) - 1)]
                    prods_cluster = [productos_features[i] for i in range(len(productos_features)) if labels[i] == cluster_idx]
                    muestra = [
                        {"id": str(p["id"]), "nombre": p["nombre"], "unidades": int(p["unidades"]), "ingresos": float(p["ingresos"])}
                        for p in prods_cluster[:5]
                    ]
                    grupos.append(
                        GrupoProductoDTO(
                            grupo_id=rango + 1,
                            nombre_grupo=nombre_g,
                            descripcion=desc_g,
                            cantidad_productos=len(prods_cluster),
                            centroide={
                                "unidades_promedio": round(float(centroides_raw[cluster_idx, 1]), 2),
                                "ingresos_promedio": round(float(centroides_raw[cluster_idx, 2]), 2),
                                "frecuencia_promedio": round(float(centroides_raw[cluster_idx, 0]), 2),
                                "rotacion_promedio": round(float(centroides_raw[cluster_idx, 3]), 2),
                            },
                            productos_muestra=muestra,
                        )
                    )

        # Registrar artefactos reales en disco con hash SHA-256
        modelo_id = uuid.uuid4()
        max_v = await self.db.scalar(
            select(func.max(ModeloML.version)).where(
                ModeloML.empresa_id == empresa_id,
                ModeloML.tipo == "AGRUPACION",
            )
        ) or 0
        version_num = int(max_v) + 1

        artefacto_uri, artefacto_hash = _guardar_artefacto_disco(
            empresa_id=empresa_id,
            subdirectorio="modelos",
            nombre_archivo=f"segmentacion_{modelo_id}.json",
            contenido={
                "modelo_id": str(modelo_id),
                "tipo": "SEGMENTACION_KMEANS",
                "version": version_num,
                "origen_datos": origen_efectivo,
                "pipeline": parametros_pipeline,
                "creado_en": _ahora_utc().isoformat(),
            },
        )

        resultado_uri, resultado_hash = _guardar_artefacto_disco(
            empresa_id=empresa_id,
            subdirectorio="resultados",
            nombre_archivo=f"segmentacion_resultado_{modelo_id}.json",
            contenido={
                "modelo_id": str(modelo_id),
                "metricas": metricas,
                "grupos": [g.model_dump() for g in grupos],
                "generado_en": _ahora_utc().isoformat(),
            },
        )

        dataset_ver = f"ds_seg_{'sintetico' if 'SINTETICO' in origen_efectivo else 'real'}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        origen_datos_bd = "SINTETICO" if "SINTETICO" in origen_efectivo else "REAL"
        modelo = ModeloML(
            id=modelo_id,
            empresa_id=empresa_id,
            tipo="AGRUPACION",
            version=version_num,
            origen_datos=origen_datos_bd,
            semilla=semilla,
            dataset_version=dataset_ver,
            dataset_hash=hashlib.sha256(f"{empresa_id}:{origen_efectivo}:{len(filas)}".encode()).hexdigest()[:16],
            metricas=metricas,
            artefacto_uri=artefacto_uri,
            artefacto_hash=artefacto_hash,
            resultado_uri=resultado_uri,
            resultado_hash=resultado_hash,
            esquema_resultado_version=1,
        )
        self.db.add(modelo)
        await self.db.commit()

        return SegmentacionProductosResultadoDTO(
            modelo_id=modelo_id,
            modelo_version=f"kmeans_v{version_num}",
            metricas=metricas,
            origen_datos=origen_efectivo,
            generado_en=_ahora_utc(),
            grupos=grupos,
        )
