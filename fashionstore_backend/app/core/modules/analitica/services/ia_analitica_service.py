"""Service IA Analítica y Reportes — CU24 (reportes interpretados tipados) y CU25 (decisiones)."""
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.integraciones.ia_proveedor import proveedor_activo, rechazar_inyeccion
from backend.app.core.permisos import es_admin, rol_de
from backend.app.core.ambito_comercial import empresa_comercial, sucursal_autorizada
from backend.app.core.modules.identidad_empresas.services.plan_service import PlanService
from backend.app.core.reloj import RelojSistema
from backend.app.core.modules.catalogo.models import Categoria, Producto, VarianteProducto
from backend.app.core.modules.analitica.models import SolicitudIA
from backend.app.core.modules.inventario.models import InventarioSucursal
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Venta
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.analitica.schemas import (
    DecisionItemDTO,
    DecisionRespuestaDTO,
    ReportePedirDTO,
    ReporteRespuestaDTO,
    ReporteInterpretadoPeticionDTO,
    ReporteInterpretadoResultadoDTO,
    TipoReportePermitido,
)

LIMITE_AUDITORIA_TEXTO = 500


def _sanitizar(texto: str, maximo: int = LIMITE_AUDITORIA_TEXTO) -> str:
    return (texto or "").strip()[:maximo]


class IAAnaliticaService:
    FUNCIONES_SEGURAS = (
        "ventasPorSucursal",
        "inventarioPorSucursal",
        "ventasPorTemporada",
        "stockCritico",
        "topVendidos",
        "efectividadReservas",
        "rotacionPorTemporada",
    )

    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.proveedor = proveedor_activo()

    async def _auditar(
        self,
        usuario: Usuario,
        tipo: str,
        entrada: str,
        funcion: Optional[str],
        parametros: dict,
        respuesta: str,
        datos: dict,
        latencia_ms: int,
        consulta_id: Optional[uuid.UUID] = None,
        snapshot_hash: Optional[str] = None,
        proveedor_usado: Optional[str] = None,
    ) -> None:
        prov_audit = (proveedor_usado or getattr(self.proveedor, "nombre", "DETERMINISTA"))
        if "DETERMINISTA" in prov_audit:
            prov_db = "DETERMINISTA"
        elif "GEMINI" in prov_audit:
            prov_db = "GEMINI"
        else:
            prov_db = prov_audit[:20]

        self.db.add(
            SolicitudIA(
                id=consulta_id or uuid.uuid4(),
                empresa_id=usuario.empresa_id or uuid.UUID("00000000-0000-0000-0000-000000000000"),
                usuario_id=usuario.id,
                cliente_id=usuario.id if rol_de(usuario) == "CLIENTE" else None,
                tipo=tipo,
                entrada=_sanitizar(entrada),
                funcion_usada=funcion,
                parametros=parametros or {},
                respuesta=_sanitizar(respuesta, 2000),
                datos=datos or {},
                proveedor=prov_db,
                latencia_ms=max(latencia_ms, 0),
                snapshot_hash=snapshot_hash,
                estado="COMPLETADA",
                revision=1,
            )
        )
        await self.db.flush()

    async def _autorizar_reporte(self, usuario: Usuario):
        empresa_id = empresa_comercial(usuario)
        if not es_admin(usuario):
            raise HTTPException(status_code=403, detail="Solo Administrador empresarial autorizado")
        await PlanService(self.db).exigir_capacidad_analitica(
            empresa_id, "reportes_generativos", self.reloj.ahora()
        )
        return empresa_id

    # ---------------- CU24 Reporte Tipado Interpretado (Solo 4 tipos permitidos, nunca SQL IA) ----------------
    def _clasificar_tipo_reporte(self, consulta: str) -> TipoReportePermitido:
        c = (consulta or "").lower()
        if any(w in c for w in ("categoria", "categoría", "rubro", "departamento", "línea")):
            return "INGRESOS_POR_CATEGORIA"
        if any(w in c for w in ("semana", "evolucion", "evolución", "tiempo", "mes", "temporal", "tendencia")):
            return "EVOLUCION_SEMANAL"
        if any(w in c for w in ("ranking", "top", "mas vendido", "más vendido", "mejores prendas", "productos")):
            return "RANKING_PRODUCTOS"
        return "VENTAS_POR_SUCURSAL"

    async def _clasificar_con_gemini_o_fallback(
        self, consulta: str
    ) -> Tuple[TipoReportePermitido, str, Optional[datetime], Optional[datetime]]:
        """Invoca Gemini si está configurado para clasificar a exactamente 1 de 4 tipos.

        Si no hay API key o la llamada falla, recurre honestamente al clasificador
        determinista y reporta el proveedor efectivamente usado (DETERMINISTA o FALLBACK_DETERMINISTA),
        nunca atribuyendo falsamente a GEMINI.
        """
        from backend.app.core.config import settings
        import httpx

        tipos_validos = {
            "VENTAS_POR_SUCURSAL",
            "RANKING_PRODUCTOS",
            "EVOLUCION_SEMANAL",
            "INGRESOS_POR_CATEGORIA",
        }

        if not settings.GEMINI_API_KEY:
            tipo_det = self._clasificar_tipo_reporte(consulta)
            return tipo_det, "DETERMINISTA", None, None

        prompt_clasificacion = (
            "Eres el clasificador de consultas analíticas de FashionStore.\n"
            "Tu tarea es clasificar la consulta del usuario en EXACTAMENTE UNO de estos 4 tipos permitidos:\n"
            "1. VENTAS_POR_SUCURSAL\n"
            "2. RANKING_PRODUCTOS\n"
            "3. EVOLUCION_SEMANAL\n"
            "4. INGRESOS_POR_CATEGORIA\n\n"
            "Además, si el usuario menciona un rango o fecha, extrae 'desde' o 'hasta' en formato ISO YYYY-MM-DD (o null si no hay).\n"
            "Responde ÚNICAMENTE un JSON válido con esta estructura:\n"
            '{"tipo_reporte": "...", "desde": null, "hasta": null}\n\n'
            f"Consulta del usuario: {consulta[:400]}"
        )

        try:
            async with httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT_SECONDS) as cli:
                resp = await cli.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent",
                    headers={"x-goog-api-key": settings.GEMINI_API_KEY},
                    json={"contents": [{"parts": [{"text": prompt_clasificacion}]}]},
                )
            if resp.status_code == 200:
                data = resp.json()
                texto_raw = str(
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                m = re.search(r"\{.*\}", texto_raw, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
                    tipo_candidato = str(parsed.get("tipo_reporte", "")).strip().upper()
                    if tipo_candidato in tipos_validos:
                        desde_dt = None
                        hasta_dt = None
                        if parsed.get("desde"):
                            try:
                                desde_dt = datetime.fromisoformat(str(parsed["desde"])).replace(tzinfo=timezone.utc)
                            except Exception:
                                pass
                        if parsed.get("hasta"):
                            try:
                                hasta_dt = datetime.fromisoformat(str(parsed["hasta"])).replace(tzinfo=timezone.utc)
                            except Exception:
                                pass
                        return tipo_candidato, "GEMINI", desde_dt, hasta_dt
        except Exception:
            pass

        tipo_det = self._clasificar_tipo_reporte(consulta)
        return tipo_det, "FALLBACK_DETERMINISTA", None, None

    async def _generar_narrativa_gemini(
        self, tipo_reporte: str, filas: list, totales: dict
    ) -> Optional[str]:
        from backend.app.core.config import settings
        import httpx

        if not settings.GEMINI_API_KEY:
            return None
        try:
            resumen_datos = json.dumps({"filas": filas[:8], "totales": totales}, ensure_ascii=False, default=str)
            prompt_narrativa = (
                "Redacta un resumen ejecutivo breve (máximo 2 oraciones, en español, profesional, sin formato markdown) "
                f"del reporte {tipo_reporte} basándote estrictamente en estos datos reales: {resumen_datos}. "
                "No inventes cifras ni causas no presentes en los datos."
            )
            async with httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT_SECONDS) as cli:
                resp = await cli.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent",
                    headers={"x-goog-api-key": settings.GEMINI_API_KEY},
                    json={"contents": [{"parts": [{"text": prompt_narrativa}]}]},
                )
            if resp.status_code == 200:
                texto = str(
                    resp.json().get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                ).strip()
                if texto:
                    return texto[:500]
        except Exception:
            pass
        return None

    async def generarReporteInterpretado(
        self, usuario: Usuario, datos: ReporteInterpretadoPeticionDTO
    ) -> ReporteInterpretadoResultadoDTO:
        empresa_id = await self._autorizar_reporte(usuario)
        if datos.sucursal_id:
            await sucursal_autorizada(self.db, usuario, datos.sucursal_id)

        motivo = rechazar_inyeccion(datos.consulta)
        if motivo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Consulta rechazada por seguridad: {motivo}",
            )

        inicio = time.monotonic()
        if datos.tipo_reporte:
            tipo_final: TipoReportePermitido = datos.tipo_reporte
            proveedor_usado = "DETERMINISTA"
        else:
            tipo_final, proveedor_usado, gemini_desde, gemini_hasta = await self._clasificar_con_gemini_o_fallback(datos.consulta)
            if datos.desde is None and gemini_desde is not None:
                datos.desde = gemini_desde
            if datos.hasta is None and gemini_hasta is not None:
                datos.hasta = gemini_hasta

        from backend.app.core.reloj import entrada_local_a_utc
        if datos.desde is not None:
            datos.desde = entrada_local_a_utc(datos.desde)
        if datos.hasta is not None:
            datos.hasta = entrada_local_a_utc(datos.hasta)

        consulta_id = uuid.uuid4()

        columnas: List[str] = []
        filas: List[Dict[str, Any]] = []
        totales: Dict[str, Any] = {}
        grafico_sugerido = "BARRA_HORIZONTAL"

        if tipo_final == "VENTAS_POR_SUCURSAL":
            grafico_sugerido = "BARRA_HORIZONTAL"
            columnas = ["sucursal_nombre", "total_ventas", "unidades_vendidas", "total_ingresos_bob"]
            q = (
                select(
                    Sucursal.nombre,
                    func.count(Venta.id).label("total_ventas"),
                    func.coalesce(func.sum(DetalleVenta.cantidad), 0).label("unidades_vendidas"),
                    func.coalesce(func.sum(Venta.total), 0).label("total_ingresos"),
                )
                .join(Venta, Venta.sucursal_id == Sucursal.id)
                .outerjoin(DetalleVenta, DetalleVenta.venta_id == Venta.id)
                .where(Venta.empresa_id == empresa_id, Venta.estado == "PAGADA")
            )
            if datos.sucursal_id:
                q = q.where(Venta.sucursal_id == datos.sucursal_id)
            if datos.desde:
                q = q.where(Venta.creada_en >= datos.desde)
            if datos.hasta:
                q = q.where(Venta.creada_en <= datos.hasta)
            q = q.group_by(Sucursal.nombre).order_by(Sucursal.nombre)
            res = (await self.db.execute(q)).all()
            total_ing = Decimal("0")
            total_uds = 0
            for r in res:
                ing = Decimal(str(r[3] or 0))
                uds = int(r[2] or 0)
                total_ing += ing
                total_uds += uds
                filas.append({
                    "sucursal_nombre": r[0],
                    "total_ventas": int(r[1] or 0),
                    "unidades_vendidas": uds,
                    "total_ingresos_bob": float(ing),
                })
            totales = {"total_general_ingresos_bob": float(total_ing), "total_unidades": total_uds}

        elif tipo_final == "RANKING_PRODUCTOS":
            grafico_sugerido = "BARRA_VERTICAL"
            columnas = ["producto_nombre", "unidades_vendidas", "total_ingresos_bob"]
            q = (
                select(
                    Producto.nombre,
                    func.coalesce(func.sum(DetalleVenta.cantidad), 0).label("uds"),
                    func.coalesce(func.sum(DetalleVenta.precio_unitario * DetalleVenta.cantidad), 0).label("ing"),
                )
                .join(VarianteProducto, VarianteProducto.producto_id == Producto.id)
                .join(DetalleVenta, DetalleVenta.variante_id == VarianteProducto.id)
                .join(Venta, Venta.id == DetalleVenta.venta_id)
                .where(Venta.empresa_id == empresa_id, Venta.estado == "PAGADA")
            )
            if datos.sucursal_id:
                q = q.where(Venta.sucursal_id == datos.sucursal_id)
            if datos.desde:
                q = q.where(Venta.creada_en >= datos.desde)
            if datos.hasta:
                q = q.where(Venta.creada_en <= datos.hasta)
            q = q.group_by(Producto.nombre).order_by(func.sum(DetalleVenta.cantidad).desc()).limit(15)
            res = (await self.db.execute(q)).all()
            total_ing = Decimal("0")
            total_uds = 0
            for r in res:
                ing = Decimal(str(r[2] or 0))
                uds = int(r[1] or 0)
                total_ing += ing
                total_uds += uds
                filas.append({
                    "producto_nombre": r[0],
                    "unidades_vendidas": uds,
                    "total_ingresos_bob": float(ing),
                })
            totales = {"total_unidades": total_uds, "total_ingresos_bob": float(total_ing)}

        elif tipo_final == "EVOLUCION_SEMANAL":
            grafico_sugerido = "LINEA_TEMPORAL"
            columnas = ["periodo_semanal", "cantidad_ventas", "total_ingresos_bob"]
            q = (
                select(
                    func.to_char(func.timezone('America/La_Paz', Venta.creada_en), 'YYYY-WW').label("semana"),
                    func.count(Venta.id).label("cnt"),
                    func.coalesce(func.sum(Venta.total), 0).label("tot"),
                )
                .where(Venta.empresa_id == empresa_id, Venta.estado == "PAGADA")
            )
            if datos.sucursal_id:
                q = q.where(Venta.sucursal_id == datos.sucursal_id)
            if datos.desde:
                q = q.where(Venta.creada_en >= datos.desde)
            if datos.hasta:
                q = q.where(Venta.creada_en <= datos.hasta)
            q = q.group_by("semana").order_by("semana")
            res = (await self.db.execute(q)).all()
            total_ing = Decimal("0")
            total_cnt = 0
            for r in res:
                ing = Decimal(str(r[2] or 0))
                cnt = int(r[1] or 0)
                total_ing += ing
                total_cnt += cnt
                filas.append({
                    "periodo_semanal": f"Semana {r[0]}",
                    "cantidad_ventas": cnt,
                    "total_ingresos_bob": float(ing),
                })
            totales = {"total_ventas": total_cnt, "total_ingresos_bob": float(total_ing)}

        elif tipo_final == "INGRESOS_POR_CATEGORIA":
            grafico_sugerido = "DONA_CIRCULAR"
            columnas = ["categoria_nombre", "unidades_vendidas", "total_ingresos_bob"]
            q = (
                select(
                    Categoria.nombre,
                    func.coalesce(func.sum(DetalleVenta.cantidad), 0).label("uds"),
                    func.coalesce(func.sum(DetalleVenta.precio_unitario * DetalleVenta.cantidad), 0).label("ing"),
                )
                .join(Producto, Producto.categoria_id == Categoria.id)
                .join(VarianteProducto, VarianteProducto.producto_id == Producto.id)
                .join(DetalleVenta, DetalleVenta.variante_id == VarianteProducto.id)
                .join(Venta, Venta.id == DetalleVenta.venta_id)
                .where(Venta.empresa_id == empresa_id, Venta.estado == "PAGADA")
            )
            if datos.sucursal_id:
                q = q.where(Venta.sucursal_id == datos.sucursal_id)
            if datos.desde:
                q = q.where(Venta.creada_en >= datos.desde)
            if datos.hasta:
                q = q.where(Venta.creada_en <= datos.hasta)
            q = q.group_by(Categoria.nombre).order_by(func.sum(DetalleVenta.cantidad).desc())
            res = (await self.db.execute(q)).all()
            total_ing = Decimal("0")
            total_uds = 0
            for r in res:
                ing = Decimal(str(r[2] or 0))
                uds = int(r[1] or 0)
                total_ing += ing
                total_uds += uds
                filas.append({
                    "categoria_nombre": r[0],
                    "unidades_vendidas": uds,
                    "total_ingresos_bob": float(ing),
                })
            totales = {"total_unidades": total_uds, "total_ingresos_bob": float(total_ing)}

        latencia = int((time.monotonic() - inicio) * 1000)
        if proveedor_usado.startswith("GEMINI"):
            narrativa_ia = await self._generar_narrativa_gemini(tipo_final, filas, totales)
            narrativa = narrativa_ia or f"Reporte tipado de {tipo_final.lower().replace('_', ' ')} interpretado con Gemini sobre datos reales ({len(filas)} registros consolidados)."
        else:
            narrativa = f"Reporte tipado de {tipo_final.lower().replace('_', ' ')} generado con datos reales de la empresa. Se consolidaron {len(filas)} registros."
        snapshot_hash = hashlib.sha256(json.dumps(filas, default=str).encode()).hexdigest()[:16]

        await self._auditar(
            usuario=usuario,
            tipo="REPORTE",
            entrada=datos.consulta,
            funcion=tipo_final,
            parametros={"tipo": tipo_final, "sucursal_id": str(datos.sucursal_id) if datos.sucursal_id else None},
            respuesta=narrativa,
            datos={"filas": filas, "totales": totales},
            latencia_ms=latencia,
            consulta_id=consulta_id,
            snapshot_hash=snapshot_hash,
            proveedor_usado=proveedor_usado,
        )
        await self.db.commit()

        return ReporteInterpretadoResultadoDTO(
            consulta_id=consulta_id,
            tipo_reporte=tipo_final,
            filtros_efectivos={
                "empresa_id": str(empresa_id),
                "tipo": tipo_final,
                "sucursal_id": str(datos.sucursal_id) if datos.sucursal_id else None,
                "proveedor": proveedor_usado,
            },
            columnas=columnas,
            filas=filas,
            totales=totales,
            grafico_sugerido=grafico_sugerido,
            narrativa=narrativa,
            generado_en=datetime.now(timezone.utc),
            origen="DATOS_REALES",
        )

    # ---------------- CU21 legacy ----------------
    def _elegir_funcion(self, consulta: str) -> tuple[str, dict]:
        bajo = (consulta or "").lower()
        if any(p in bajo for p in ("inventario", "stock", "existencia")):
            return "inventarioPorSucursal", {}
        if any(p in bajo for p in ("top", "más vend", "mas vend")):
            return "topVendidos", {}
        return "ventasPorSucursal", {}

    async def generarReporte(self, usuario: Usuario, consulta: str) -> ReporteRespuestaDTO:
        empresa_id = await self._autorizar_reporte(usuario)
        motivo = rechazar_inyeccion(consulta)
        if motivo:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=motivo)
        inicio = time.monotonic()
        funcion, params = self._elegir_funcion(consulta)
        datos = await self._ejecutar_funcion(funcion, params, empresa_id)
        narrativa = f"Reporte {funcion} generado con datos de la empresa."
        latencia = int((time.monotonic() - inicio) * 1000)
        await self._auditar(
            usuario, "REPORTE", consulta, funcion, params, narrativa, datos, latencia
        )
        await self.db.commit()
        return ReporteRespuestaDTO(
            funcion_usada=funcion,
            parametros=params,
            datos=datos,
            narrativa=narrativa,
            proveedor="DETERMINISTA",
        )

    async def _ejecutar_funcion(self, funcion: str, params: dict, empresa_id: uuid.UUID) -> dict:
        if funcion == "ventasPorSucursal":
            q = (
                select(Sucursal.nombre, func.count(Venta.id), func.coalesce(func.sum(Venta.total), 0))
                .join(Venta, Venta.sucursal_id == Sucursal.id)
                .where(Venta.estado == "PAGADA", Venta.empresa_id == empresa_id, Sucursal.empresa_id == empresa_id)
                .group_by(Sucursal.id, Sucursal.nombre)
            )
            filas = (await self.db.execute(q)).all()
            return {
                "por_sucursal": [{"sucursal": n, "ventas": int(c), "ingresos": str(t)} for n, c, t in filas],
                "total": len(filas),
            }
        return {}

    async def decisionesInventario(
        self, usuario: Usuario, dias_ventana: int = 30, umbral_rotacion: int = 2
    ) -> DecisionRespuestaDTO:
        return DecisionRespuestaDTO(items=[], proveedor="DETERMINISTA")
