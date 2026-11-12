"""Service IA Analítica y Reportes — CU24 (reportes interpretados tipados) y CU25 (decisiones)."""
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
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
from backend.app.core.modules.reservas_traslados.models import Reserva
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

    # ---------------- CU24: tipos permitidos, nunca SQL IA ----------------
    def _clasificar_tipo_reporte(self, consulta: str) -> TipoReportePermitido:
        from .interpretacion_reportes import tipo_texto, ADMITIDOS
        tipo = tipo_texto(consulta)
        if not tipo:
            raise HTTPException(422, detail=f"FUERA_DE_ALCANCE: Se admiten {ADMITIDOS}.")
        return tipo

    async def _clasificar_con_gemini_o_fallback(
        self, consulta: str
    ) -> Tuple[TipoReportePermitido, str, Optional[datetime], Optional[datetime]]:
        """Invoca Gemini si está configurado para clasificar a exactamente 1 de 5 tipos.

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
            "MENOR_EXISTENCIA",
        }

        if not settings.GEMINI_API_KEY:
            tipo_det = self._clasificar_tipo_reporte(consulta)
            return tipo_det, "DETERMINISTA", None, None

        prompt_clasificacion = (
            "Eres el clasificador de consultas analíticas de FashionStore.\n"
            "Tu tarea es clasificar la consulta del usuario en EXACTAMENTE UNO de estos 5 tipos permitidos:\n"
            "1. VENTAS_POR_SUCURSAL\n"
            "2. RANKING_PRODUCTOS\n"
            "3. EVOLUCION_SEMANAL\n"
            "4. INGRESOS_POR_CATEGORIA\n"
            "5. MENOR_EXISTENCIA\n"
            "Un ranking con meses sigue siendo RANKING_PRODUCTOS, no evolución semanal.\n\n"
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
                                desde_dt = datetime.fromisoformat(str(parsed["desde"]))
                            except Exception:
                                pass
                        if parsed.get("hasta"):
                            try:
                                fecha_hasta = str(parsed["hasta"])
                                hasta_dt = datetime.fromisoformat(fecha_hasta)
                                if len(fecha_hasta) == 10:
                                    hasta_dt += timedelta(days=1, microseconds=-1)
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
        motivo = rechazar_inyeccion(datos.consulta)
        if motivo:
            raise HTTPException(status_code=400, detail=f"Consulta rechazada por seguridad: {motivo}")
        from .interpretacion_reportes import interpretar
        from .consulta_reportes import resolver_filtros, consultar
        from backend.app.core.config import settings
        inicio = time.monotonic()
        datos = interpretar(datos, self.reloj.ahora())
        sucursal = await resolver_filtros(self.db, usuario, datos, empresa_id)
        tipo_final = datos.tipo_reporte
        # El candidato Gemini se contrasta con el plan validado: nunca cambia el
        # tenant, el período resuelto por reloj civil ni las consultas permitidas.
        proveedor_usado = "DETERMINISTA"
        if settings.GEMINI_API_KEY:
            try:
                candidato, motor, _, _ = await self._clasificar_con_gemini_o_fallback(datos.consulta)
                proveedor_usado = motor if candidato == tipo_final else "FALLBACK_DETERMINISTA"
            except HTTPException:
                proveedor_usado = "FALLBACK_DETERMINISTA"  # El DTO explícito ya fue validado.
        consulta_id = uuid.uuid4()
        columnas, filas, totales, grafico_sugerido = await consultar(self.db, datos, empresa_id)
        if datos.presentacion == "TABLA":
            grafico_sugerido = "TABLA"

        latencia = int((time.monotonic() - inicio) * 1000)
        narrativa_origen = "DETERMINISTA"
        if settings.GEMINI_API_KEY:
            narrativa_ia = await self._generar_narrativa_gemini(tipo_final, filas, totales)
            narrativa_origen = "GEMINI" if narrativa_ia else "FALLBACK_DETERMINISTA"
            narrativa = narrativa_ia or f"Explicación IA no disponible. El cálculo con datos reales produjo {len(filas)} registros consolidados."
        else:
            narrativa = f"Reporte tipado de {tipo_final.lower().replace('_', ' ')} generado con datos reales de la empresa. Se consolidaron {len(filas)} registros."
        snapshot_hash = hashlib.sha256(json.dumps(filas, default=str).encode()).hexdigest()[:16]

        await self._auditar(
            usuario=usuario,
            tipo="REPORTE",
            entrada=datos.consulta,
            funcion=tipo_final,
            parametros={**datos.model_dump(mode="json", exclude={"consulta"}), "tipo": tipo_final,
                        "empresa_id": str(empresa_id), "zona_horaria": "America/La_Paz"},
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
                "sucursal_nombre": sucursal.nombre if sucursal else None,
                "proveedor": proveedor_usado,
                "narrativa_origen": narrativa_origen,
                "agrupacion": datos.agrupacion,
                "limite": datos.limite,
                "orden": datos.orden,
                "presentacion": datos.presentacion,
                "categoria_id": str(datos.categoria_id) if datos.categoria_id else None,
                "producto_id": str(datos.producto_id) if datos.producto_id else None,
                "zona_horaria": "America/La_Paz",
                "periodo": "Inventario actual" if tipo_final == "MENOR_EXISTENCIA" else ("Histórico completo" if not datos.desde and not datos.hasta else "Fechas efectivas indicadas"),
                "metrica": "disponible" if tipo_final == "MENOR_EXISTENCIA" else ("unidades_vendidas" if tipo_final == "RANKING_PRODUCTOS" else "total_ingresos_bob"),
                "desde": datos.desde.isoformat() if datos.desde else None,
                "hasta": datos.hasta.isoformat() if datos.hasta else None,
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
        if any(p in bajo for p in ("stock crítico", "stock critico", "inventario bajo", "agot")):
            return "stockCritico", {}
        if any(p in bajo for p in ("inventario", "stock", "existencia")):
            return "inventarioPorSucursal", {}
        if any(p in bajo for p in ("top", "más vend", "mas vend")):
            return "topVendidos", {}
        if "reserva" in bajo:
            return "efectividadReservas", {}
        if any(p in bajo for p in ("rotaci", "lenta", "dead", "baja rot")):
            return "rotacionPorTemporada", {}
        if "temporada" in bajo:
            return "ventasPorTemporada", {}
        return "ventasPorSucursal", {}

    async def generarReporte(self, usuario: Usuario, consulta: str) -> ReporteRespuestaDTO:
        empresa_id = await self._autorizar_reporte(usuario)
        motivo = rechazar_inyeccion(consulta)
        if motivo:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=motivo)
        inicio = time.monotonic()
        funcion, params = self._elegir_funcion(consulta)
        datos = await self._ejecutar_funcion(funcion, params, empresa_id)
        ambito = "inventario actual" if funcion in ("inventarioPorSucursal", "stockCritico") else "histórico completo"
        narrativa = f"Reporte {funcion} del {ambito} de la empresa. Esta ruta heredada no interpreta filtros de período o sucursal del texto."
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
        if funcion == "inventarioPorSucursal":
            q = (select(Sucursal.nombre, func.count(InventarioSucursal.id),
                        func.coalesce(func.sum(InventarioSucursal.disponible), 0),
                        func.coalesce(func.sum(InventarioSucursal.reservado), 0),
                        func.coalesce(func.sum(InventarioSucursal.en_transito), 0))
                 .join(InventarioSucursal, InventarioSucursal.sucursal_id == Sucursal.id)
                 .join(VarianteProducto, VarianteProducto.id == InventarioSucursal.variante_id)
                 .where(Sucursal.empresa_id == empresa_id, VarianteProducto.empresa_id == empresa_id)
                 .group_by(Sucursal.id, Sucursal.nombre).order_by(Sucursal.nombre))
            filas = (await self.db.execute(q)).all()
            return {"inventario_por_sucursal": [dict(sucursal=n, variantes=int(c), disponible=int(d),
                    reservado=int(r), en_transito=int(t)) for n, c, d, r, t in filas], "total": len(filas)}
        if funcion == "stockCritico":
            filas = (await self.db.execute(
                select(VarianteProducto.sku, Sucursal.nombre, InventarioSucursal.disponible)
                .join(InventarioSucursal, InventarioSucursal.variante_id == VarianteProducto.id)
                .join(Sucursal, Sucursal.id == InventarioSucursal.sucursal_id)
                .where(Sucursal.empresa_id == empresa_id, VarianteProducto.empresa_id == empresa_id,
                       InventarioSucursal.disponible <= 5)
                .order_by(InventarioSucursal.disponible, VarianteProducto.sku, Sucursal.id).limit(50)
            )).all()
            return {"criticos": [dict(sku=s, sucursal=n, disponible=int(d)) for s, n, d in filas], "total": len(filas)}
        if funcion == "topVendidos":
            filas = (await self.db.execute(
                select(VarianteProducto.sku, func.sum(DetalleVenta.cantidad))
                .join(DetalleVenta, DetalleVenta.variante_id == VarianteProducto.id)
                .join(Venta, Venta.id == DetalleVenta.venta_id)
                .where(Venta.empresa_id == empresa_id, VarianteProducto.empresa_id == empresa_id, Venta.estado == "PAGADA")
                .group_by(VarianteProducto.id, VarianteProducto.sku)
                .order_by(func.sum(DetalleVenta.cantidad).desc(), VarianteProducto.sku).limit(10)
            )).all()
            return {"top": [dict(sku=s, unidades=int(c)) for s, c in filas], "total": len(filas)}
        if funcion == "efectividadReservas":
            total = int((await self.db.execute(select(func.count(Reserva.id)).where(Reserva.empresa_id == empresa_id))).scalar() or 0)
            completadas = int((await self.db.execute(select(func.count(Reserva.id)).where(
                Reserva.empresa_id == empresa_id, Reserva.estado == "COMPLETADA"))).scalar() or 0)
            return {"total": total, "completadas": completadas, "conversion": completadas / total if total else 0}
        raise HTTPException(status_code=501, detail="Reporte por temporada pendiente: falta una regla de atribución de ventas a temporadas históricas; no se inventa esa asociación")

    async def decisionesInventario(
        self, usuario: Usuario, dias_ventana: int = 30, umbral_rotacion: int = 2
    ) -> DecisionRespuestaDTO:
        empresa_comercial(usuario)
        if not es_admin(usuario):
            raise HTTPException(status_code=403, detail="Solo Administrador empresarial autorizado")
        raise HTTPException(status_code=501, detail="Decisiones pendientes: faltan reglas aprobadas para seleccionar promoción, liquidación, traslado o reposición y sus cantidades")
